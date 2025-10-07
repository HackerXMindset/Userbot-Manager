"""
DexScreener Token Monitoring Service - Completely Rewritten

Architecture:
- DexScreener API: Fast batch polling for price updates (every 30s)
- Jupiter API: Authoritative source for initialization and alert verification
- Two-phase alert system: Quick check → Jupiter verification → Fire

Data Flow:
1. Token detected → Jupiter API (first_seen_mc baseline)
2. Polling loop → DexScreener API (fast last_mc updates)
3. Alert candidate → Jupiter API verification → Queue if confirmed
"""

import asyncio
import aiohttp
import logging
import json
from typing import Dict, Any, Optional, List
from decimal import Decimal, InvalidOperation
from datetime import datetime

from app.config import settings
from app.db import db
from app.models import TokenModel, TargetModel
from app.models.call_queue import CallQueueModel
from app.models.target_alert_state import TargetAlertStateModel
from app.userbot.session_manager import SessionManager
from app.services.jupiter_api import get_jupiter_service

logger = logging.getLogger(__name__)

# Singleton instance for global access
_dex_service_instance = None


def get_dex_service():
    """Get the singleton DexScreener service instance"""
    global _dex_service_instance
    if _dex_service_instance is None:
        _dex_service_instance = DexScreenerService()
    return _dex_service_instance


class DexScreenerService:
    """
    DexScreener integration for token price monitoring

    Responsibilities:
    - Token initialization (Jupiter API only)
    - Batch price polling (DexScreener API)
    - Alert verification (Jupiter API)
    - Drop monitoring and auto-stop
    """

    BASE_URL = "https://api.dexscreener.com/tokens/v1/solana"
    MIN_MC_THRESHOLD = Decimal('8000')  # Stop monitoring below $8K

    def __init__(self):
        self.token_model = TokenModel(db)
        self.call_queue_model = CallQueueModel(db)
        self.target_model = TargetModel(db)
        self.target_alert_state_model = TargetAlertStateModel(db)
        self.jupiter_service = get_jupiter_service()

        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.userbot_manager = None

    def set_userbot_manager(self, manager):
        """Set the UserbotManager instance"""
        self.userbot_manager = manager
        logger.info("UserbotManager instance set in DexScreenerService")

    async def start(self):
        """Start the monitoring service"""
        if self.running:
            return

        # Start Jupiter service
        await self.jupiter_service.start()

        # Start DexScreener session
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.dex_timeout)
        )

        self.running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("DexScreener service started")

    async def stop(self):
        """Stop the monitoring service"""
        if not self.running:
            return

        self.running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        if self.session:
            await self.session.close()
            self.session = None

        await self.jupiter_service.stop()

        logger.info("DexScreener service stopped")

    # ==================== MONITORING LOOP ====================

    async def _monitoring_loop(self):
        """Main monitoring loop - polls DexScreener every 30s"""
        logger.info(f"Monitoring loop started (polling every {settings.dex_poll_secs}s)")

        while self.running:
            try:
                await self._update_token_prices()
                await asyncio.sleep(settings.dex_poll_secs)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Monitoring loop error: {e}", exc_info=True)
                await asyncio.sleep(30)

    async def _update_token_prices(self):
        """Update prices for all active tokens using DexScreener"""
        try:
            active_tokens_records = await self.token_model.get_active_tokens()
            active_tokens = [dict(t) for t in active_tokens_records]

            if not active_tokens:
                return

            logger.debug(f"Updating {len(active_tokens)} active tokens")

            # Process in batches of 30 (DexScreener API limit)
            await self._process_token_batch(active_tokens)

        except Exception as e:
            logger.error(f"Error updating token prices: {e}", exc_info=True)

    async def _process_token_batch(self, tokens: List[Dict[str, Any]]):
        """Process tokens in batches using DexScreener batch API"""
        batch_size = 30

        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i + batch_size]
            try:
                addresses = [token['address'] for token in batch]

                # Single batch API call for up to 30 tokens
                batch_data = await self._fetch_batch_token_data(addresses)

                if batch_data:
                    # Process each token with its data
                    for token in batch:
                        token_address = token['address']
                        token_pairs = [
                            pair for pair in batch_data
                            if pair.get('baseToken', {}).get('address') == token_address
                        ]
                        if token_pairs:
                            await self._update_token_from_data(token, token_pairs)

                # Rate limiting: 0.2s delay between batches (5 req/sec max)
                if i + batch_size < len(tokens):
                    await asyncio.sleep(0.2)

            except Exception as e:
                logger.error(f"Error processing batch: {e}")
                # Fallback: process individually
                for token in batch:
                    try:
                        token_data = await self._fetch_token_data(token['address'])
                        if token_data:
                            await self._update_token_from_data(token, token_data)
                    except Exception as token_error:
                        logger.error(f"Error processing {token['address'][:8]}...: {token_error}")

    # ==================== DEXSCREENER API CALLS ====================

    async def _fetch_token_data(self, token_address: str, retries: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Fetch token data from DexScreener API (single token)"""
        if not self.session:
            logger.error(f"[DEXSCREENER] Session not initialized for {token_address[:8]}...")
            return None

        try:
            url = f"{self.BASE_URL}/{token_address}"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json(content_type=None)

                    if isinstance(data, list):
                        if len(data) == 0:
                            logger.debug(f"[DEXSCREENER] No pairs for {token_address[:8]}...")
                            return []
                        return data
                    else:
                        logger.error(f"[DEXSCREENER] Unexpected format for {token_address[:8]}...")
                        return None

                elif response.status == 404:
                    logger.debug(f"[DEXSCREENER] Token {token_address[:8]}... not found")
                    return None

                elif response.status == 429:  # Rate limited
                    if retries < settings.dex_max_retries:
                        wait_time = 2 ** retries
                        logger.warning(f"[DEXSCREENER] Rate limited, waiting {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        return await self._fetch_token_data(token_address, retries + 1)
                    else:
                        logger.error(f"[DEXSCREENER] Max retries exceeded for {token_address[:8]}...")
                        return None

                else:
                    logger.error(f"[DEXSCREENER] Status {response.status} for {token_address[:8]}...")
                    return None

        except asyncio.TimeoutError:
            logger.error(f"[DEXSCREENER] Timeout for {token_address[:8]}...")
        except Exception as e:
            logger.error(f"[DEXSCREENER] Error for {token_address[:8]}...: {e}")

        return None

    async def _fetch_batch_token_data(self, addresses: List[str], retries: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Fetch data for multiple tokens in one call (DexScreener batch API)"""
        if not self.session or not addresses:
            return None

        try:
            # Limit to 30 addresses
            if len(addresses) > 30:
                addresses = addresses[:30]

            # Comma-separated addresses
            addresses_str = ",".join(addresses)
            url = f"{self.BASE_URL}/{addresses_str}"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list):
                        return data
                    else:
                        logger.warning(f"[DEXSCREENER] Unexpected batch format")
                        return None

                elif response.status == 429:
                    if retries < settings.dex_max_retries:
                        await asyncio.sleep(2 ** retries)
                        return await self._fetch_batch_token_data(addresses, retries + 1)

                else:
                    logger.warning(f"[DEXSCREENER] Batch API returned {response.status}")

        except asyncio.TimeoutError:
            logger.warning(f"[DEXSCREENER] Batch timeout for {len(addresses)} tokens")
        except Exception as e:
            logger.error(f"[DEXSCREENER] Batch error: {e}")

        return None

    # ==================== TOKEN UPDATE LOGIC ====================

    async def _update_token_from_data(self, token: Dict[str, Any], api_data: List[Dict[str, Any]]):
        """
        Update token with DexScreener data and check alerts

        Flow:
        1. Extract MC from DexScreener
        2. Update last_mc in database
        3. Check alerts (with Jupiter verification)
        4. Check drop conditions
        5. Auto-stop if needed
        """
        try:
            if not api_data:
                return

            # Get best trading pair
            best_pair = api_data[0]

            market_cap = best_pair.get('marketCap')
            if not market_cap:
                return

            dex_mc = Decimal(str(market_cap))
            ticker = best_pair.get('baseToken', {}).get('symbol')

            # Update token's last_mc (from DexScreener - for UI/stats)
            await self.token_model.update_market_cap(token['id'], dex_mc, ticker)

            # Check for alerts (will verify with Jupiter before firing)
            await self._check_alerts_with_verification(token, dex_mc)

            # Check for drop alerts
            if await self._check_drop_alerts(token, dex_mc):
                return  # Token was stopped

            # Stop monitoring if too small
            if dex_mc < self.MIN_MC_THRESHOLD:
                await self.token_model.set_status(token['id'], 'stopped')
                logger.info(f"Stopped {token['address'][:8]}... (MC below ${self.MIN_MC_THRESHOLD}: ${dex_mc:,.0f})")
            else:
                logger.debug(f"Updated {token['address'][:8]}... MC: ${dex_mc:,.0f}")

        except Exception as e:
            logger.error(f"Error updating token from data: {e}", exc_info=True)

    # ==================== ALERT SYSTEM (TWO-PHASE) ====================

    async def _check_alerts_with_verification(self, token: Dict[str, Any], dex_mc: Decimal):
        """
        Two-phase alert checking:
        1. Quick check with DexScreener MC (fast screening)
        2. Verify with Jupiter MC before firing (authoritative)

        This prevents false alerts from bad DexScreener data while keeping polling fast.
        """
        source_group_id = token.get('source_group_id')
        if not source_group_id:
            return

        # Get all targets monitoring this token with alerts enabled
        targets = await self.target_model.get_targets_for_source_group(source_group_id, alerts_enabled_only=True)
        if not targets:
            return

        for target in targets:
            try:
                # Get alert state for this target+token pair
                baseline_mc = token.get('first_seen_mc') or dex_mc
                state = await self.target_alert_state_model.get_or_create(
                    target_id=target['id'],
                    token_id=token['id'],
                    initial_market_cap=baseline_mc
                )

                if not state or not state['initial_market_cap'] or state['initial_market_cap'] <= 0:
                    continue

                baseline = state['initial_market_cap']
                last_multiplier = state['last_alert_multiplier']

                # PHASE 1: Quick check with DexScreener MC
                dex_multiplier = dex_mc / baseline

                alert_to_fire = self._calculate_next_alert(
                    current_multiplier=dex_multiplier,
                    last_multiplier=last_multiplier,
                    target=target
                )

                if not alert_to_fire:
                    continue  # No alert threshold met

                # PHASE 2: VERIFY WITH JUPITER
                logger.info(
                    f"[VERIFY] Alert candidate for {token['address'][:8]}... "
                    f"at {dex_multiplier:.2f}x (Dex) - verifying with Jupiter..."
                )

                # Fetch fresh Jupiter MC (NO CACHE for verification)
                jupiter_mc = await self.jupiter_service.fetch_market_cap(
                    token['address'],
                    use_cache=False  # Always fresh for alerts
                )

                # Determine verified MC and multiplier
                if not jupiter_mc or jupiter_mc <= 0:
                    # Jupiter failed - fallback to DexScreener (Option B)
                    logger.warning(
                        f"[VERIFY] Jupiter verification failed for {token['address'][:8]}... "
                        f"- using DexScreener MC ${dex_mc:,.0f}"
                    )
                    verified_mc = dex_mc
                    verified_multiplier = dex_multiplier
                else:
                    # Jupiter succeeded - use authoritative data
                    verified_mc = jupiter_mc
                    verified_multiplier = jupiter_mc / baseline
                    logger.info(
                        f"[VERIFY] Jupiter confirmed: ${jupiter_mc:,.0f} = {verified_multiplier:.2f}x "
                        f"(Dex was ${dex_mc:,.0f} = {dex_multiplier:.2f}x)"
                    )

                # Re-check alert threshold with verified multiplier
                verified_alert = self._calculate_next_alert(
                    current_multiplier=verified_multiplier,
                    last_multiplier=last_multiplier,
                    target=target
                )

                if verified_alert:
                    # FIRE ALERT with verified data
                    await self._queue_alert(
                        token=token,
                        target=target,
                        state=state,
                        multiplier=verified_alert['value'],
                        alert_type=verified_alert['type']
                    )

                    # Update state
                    await self.target_alert_state_model.update_after_alert(
                        target['id'],
                        token['id'],
                        verified_alert['value']
                    )

                    logger.info(
                        f"[ALERT] ✅ Fired {verified_alert['type']} alert for {token['address'][:8]}... "
                        f"at {verified_multiplier:.2f}x (verified)"
                    )
                else:
                    logger.info(
                        f"[ALERT] ❌ Cancelled for {token['address'][:8]}... "
                        f"- verified multiplier {verified_multiplier:.2f}x below threshold"
                    )

            except Exception as e:
                logger.error(f"Error checking alerts for target {target['id']}: {e}", exc_info=True)

    def _calculate_next_alert(
        self,
        current_multiplier: Decimal,
        last_multiplier: Decimal,
        target: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Calculate if an alert should fire based on target settings

        Returns:
            {'type': 'threshold'|'sensitivity', 'value': Decimal} or None
        """
        modes = self.target_model.parse_alert_modes(target)

        # Check threshold alerts (e.g., 2x, 7x, 25x)
        if modes.get('threshold', False):
            thresholds = self.target_model.parse_alert_thresholds(target)
            for threshold in sorted(thresholds):
                threshold_decimal = Decimal(str(threshold))
                if current_multiplier >= threshold_decimal and last_multiplier < threshold_decimal:
                    return {'type': 'threshold', 'value': threshold_decimal}

        # Check sensitivity alerts (e.g., 50% progression)
        if modes.get('sensitivity', False):
            sensitivity = self.target_model.get_alert_sensitivity_percent(target)
            next_target = last_multiplier * (Decimal('1') + Decimal(str(sensitivity)))
            if current_multiplier >= next_target:
                return {'type': 'sensitivity', 'value': current_multiplier}

        return None

    async def _queue_alert(
        self,
        token: Dict[str, Any],
        target: Dict[str, Any],
        state: Dict[str, Any],
        multiplier: Decimal,
        alert_type: str
    ):
        """Queue an alert message to the call queue"""
        try:
            # Get forwarding userbot
            userbot_assignment = await db.fetchrow(
                "SELECT userbot_id FROM userbot_assignments WHERE group_id = $1",
                token['source_group_id']
            )
            if not userbot_assignment or not userbot_assignment['userbot_id']:
                logger.warning(f"No forwarding userbot for group {token['source_group_id']}")
                return

            forwarding_userbot_id = userbot_assignment['userbot_id']

            # Format alert message
            message = self._format_alert_message(token, state, multiplier, alert_type)

            # Get first message ID for threading
            first_message_id = state.get('first_message_id')

            # Prepare additional info
            additional_info = json.dumps({
                "message_override": message,
                "reply_to_message_id": first_message_id
            })
            source_info = json.dumps({"name": f"System {alert_type.title()} Alert"})

            # Queue the job
            await self.call_queue_model.add_job(
                token_address=token['address'],
                source_message_id=None,
                source_chat_id=None,
                target_chat_id=target['dest_chat_id'],
                forwarding_userbot_id=forwarding_userbot_id,
                target_group_id=token['source_group_id'],
                source_info=source_info,
                additional_info=additional_info
            )

        except Exception as e:
            logger.error(f"Error queuing alert: {e}", exc_info=True)

    def _format_alert_message(
        self,
        token: Dict[str, Any],
        state: Dict[str, Any],
        multiplier: Decimal,
        alert_type: str
    ) -> str:
        """Format the alert message with emoji and stats"""

        def select_emoji(mult: float) -> str:
            if mult < 3:
                return "🔥"
            if mult < 5:
                return "🚀"
            if mult < 10:
                return "🌙"
            return "🌕"

        def format_time_ago(timestamp: datetime) -> str:
            if not timestamp:
                return ""
            now = datetime.utcnow()
            delta = now - timestamp.replace(tzinfo=None)

            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)

            if days > 0:
                return f"{days}d {hours}h ago"
            elif hours > 0:
                return f"{hours}h {minutes}m ago"
            else:
                return f"{minutes}m ago"

        emoji = select_emoji(float(multiplier))
        symbol = token.get('ticker', token['address'][:6])
        mc_str = f"${state['initial_market_cap']:,.0f}"
        time_str = format_time_ago(state['first_sent_at'])

        return f"{emoji} {symbol} is at {multiplier:.2f}x!\nMC: {mc_str} | {time_str}"

    # ==================== DROP ALERT MONITORING ====================

    async def _check_drop_alerts(self, token: Dict[str, Any], new_mc: Decimal) -> bool:
        """
        Check for drop from first_seen_mc and stop monitoring if threshold exceeded

        Simple logic: Stop when current MC drops below (first_seen_mc * drop_percentage)
        Example: first_seen_mc=100K, drop_percentage=0.50 → stop at 50K

        Returns:
            True if monitoring was stopped, False otherwise
        """
        try:
            first_seen_mc = token.get('first_seen_mc')
            if not first_seen_mc or first_seen_mc <= 0:
                return False

            # Get drop threshold from settings
            drop_settings = await db.fetchval("SELECT value FROM settings WHERE key = 'drop_percentage'")
            if not drop_settings:
                return False

            drop_percentage = float(json.loads(drop_settings))

            # Calculate stop threshold: first_seen_mc * drop_percentage
            # Example: 100K * 0.50 = 50K stop threshold
            stop_threshold_mc = first_seen_mc * Decimal(str(drop_percentage))

            # Stop if current MC is at or below the threshold
            if new_mc <= stop_threshold_mc:
                await self.token_model.set_status(token['id'], 'stopped')
                drop_percent = (1 - (new_mc / first_seen_mc)) * 100
                logger.info(
                    f"Stopped {token['address'][:8]}... "
                    f"(MC ${new_mc:,.0f} is {drop_percent:.1f}% below first_seen_mc ${first_seen_mc:,.0f}, "
                    f"threshold: {drop_percentage * 100:.0f}%)"
                )
                return True

        except Exception as e:
            logger.error(f"Error checking drop alerts: {e}")

        return False

    # ==================== TOKEN MANAGEMENT ====================

    async def add_token(self, token_address: str) -> Dict[str, Any]:
        """
        Add a new token for monitoring

        JUPITER API ONLY for initialization - ensures accurate baseline
        """
        try:
            # Check if already exists
            existing = await self.token_model.get_by_address(token_address)
            if existing:
                return {
                    'success': False,
                    'error': 'Token already being tracked',
                    'token': dict(existing)
                }

            # Fetch from Jupiter API (NO CACHE, NO FALLBACK)
            logger.info(f"[INIT] Fetching initial data for {token_address[:8]}... from Jupiter")
            jupiter_data = await self.jupiter_service.get_token_data(token_address, use_cache=False)

            if not jupiter_data:
                return {
                    'success': False,
                    'error': 'Could not fetch token data from Jupiter API'
                }

            # Extract market cap
            initial_mc = self.jupiter_service.get_market_cap(jupiter_data)
            if not initial_mc or initial_mc <= 0:
                return {
                    'success': False,
                    'error': 'Invalid market cap from Jupiter'
                }

            # Extract ticker
            ticker = self.jupiter_service.get_ticker(jupiter_data)

            # Create token record
            token = await self.token_model.create_or_update(token_address, initial_mc, ticker)

            logger.info(f"[INIT] ✅ Added {token_address[:8]}... with MC ${initial_mc:,.0f} from Jupiter")

            return {
                'success': True,
                'token': dict(token),
                'initial_mc': float(initial_mc)
            }

        except Exception as e:
            logger.error(f"Error adding token: {e}", exc_info=True)
            return {
                'success': False,
                'error': str(e)
            }

    async def remove_token(self, token_address: str) -> Dict[str, Any]:
        """Stop monitoring a token"""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    'success': False,
                    'error': 'Token not found'
                }

            await self.token_model.set_status(token['id'], 'stopped')
            logger.info(f"Stopped tracking {token_address[:8]}...")

            return {
                'success': True,
                'token': dict(token)
            }

        except Exception as e:
            logger.error(f"Error removing token: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """Get current token information"""
        try:
            # Get from database
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    'success': False,
                    'error': 'Token not found in database'
                }

            # Get fresh data from Jupiter
            jupiter_data = await self.jupiter_service.get_token_data(token_address, use_cache=False)

            result = {
                'success': True,
                'token': dict(token),
                'jupiter_data': jupiter_data
            }

            if token['first_seen_mc'] and token['first_seen_mc'] > 0:
                current_multiplier = token['last_mc'] / token['first_seen_mc']
                result['multiplier'] = float(current_multiplier)

            return result

        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    async def get_service_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        try:
            token_stats = await self.token_model.get_token_stats()
            jupiter_cache_stats = self.jupiter_service.get_cache_stats()

            return {
                'running': self.running,
                'poll_interval': settings.dex_poll_secs,
                'timeout': settings.dex_timeout,
                'max_retries': settings.dex_max_retries,
                'min_mc_threshold': float(self.MIN_MC_THRESHOLD),
                'tokens': token_stats,
                'jupiter_cache': jupiter_cache_stats
            }

        except Exception as e:
            logger.error(f"Error getting service stats: {e}")
            return {'error': str(e)}
