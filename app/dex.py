import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal, InvalidOperation
from datetime import datetime

from app.config import settings
from app.db import db
from app.models import TokenModel, TargetModel
from app.models.call_queue import CallQueueModel
from app.models.target_alert_state import TargetAlertStateModel
from app.userbot.session_manager import SessionManager
from app.services.rust_bridge import rust_dex_bridge

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
    """DexScreener integration for token price monitoring"""

    BASE_URL = "https://api.dexscreener.com/tokens/v1/solana"
    JUPITER_TOLERANCE = Decimal('0.20')  # Acceptable delta between Dex and Jupiter MC readings
    
    def __init__(self):
        self.token_model = TokenModel(db)
        self.call_queue_model = CallQueueModel(db)
        self.target_model = TargetModel(db)
        self.target_alert_state_model = TargetAlertStateModel(db)
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.userbot_manager = None

    def set_userbot_manager(self, manager):
        """Set the UserbotManager instance."""
        self.userbot_manager = manager
        logger.info("UserbotManager instance set in DexScreenerService")
    
    async def start(self):
        """Start the DexScreener monitoring service"""
        if self.running:
            return
        
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.dex_timeout)
        )
        
        self.running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("DexScreener service started")
    
    async def stop(self):
        """Stop the DexScreener monitoring service"""
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
        
        logger.info("DexScreener service stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self._update_token_prices()
                await asyncio.sleep(settings.dex_poll_secs)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DexScreener monitoring error: {e}")
                await asyncio.sleep(30)
    
    async def _update_token_prices(self):
        """Update prices for all active tokens"""
        try:
            active_tokens_records = await self.token_model.get_active_tokens()
            active_tokens = [dict(t) for t in active_tokens_records]
            
            if not active_tokens:
                return
            
            # Batch process tokens to avoid rate limits
            batch_size = 10
            for i in range(0, len(active_tokens), batch_size):
                batch = active_tokens[i:i + batch_size]
                await self._process_token_batch(batch)
                
                # Small delay between batches
                if i + batch_size < len(active_tokens):
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error updating token prices: {e}")
    
    async def _process_token_batch(self, tokens: List[Dict[str, Any]]):
        """Process a batch of tokens using batch API calls"""
        # Group tokens into chunks of 30 for batch API calls
        batch_size = 30
        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i + batch_size]
            try:
                # Get addresses for this batch
                addresses = [token['address'] for token in batch]
                
                # Fetch data for all tokens in this batch with single API call
                batch_data = await self._fetch_batch_token_data(addresses)
                
                if batch_data:
                    # Process each token with its corresponding data
                    for token in batch:
                        token_address = token['address']
                        # Find the data for this specific token in the batch response
                        token_pairs = [pair for pair in batch_data 
                                     if pair.get('baseToken', {}).get('address') == token_address]
                        if token_pairs:
                            await self._update_token_from_data(token, token_pairs)
                        
                # Rate limiting: 0.2s delay between batches (5 req/sec = 300 req/min)
                if i + batch_size < len(tokens):
                    await asyncio.sleep(0.2)
                    
            except Exception as e:
                logger.error(f"Error processing batch of {len(batch)} tokens: {e}")
                # Fallback to individual processing for this batch
                for token in batch:
                    try:
                        token_data = await self._fetch_token_data(token['address'])
                        if token_data:
                            await self._update_token_from_data(token, token_data)
                    except Exception as e:
                        logger.error(f"Error processing token {token['address'][:8]}...: {e}")
    
    async def _fetch_token_data(self, token_address: str, retries: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Fetch token data from DexScreener API"""
        if not self.session:
            logger.error(f"[DEXSCREENER] HTTP session not initialized for token {token_address}")
            return None
        
        try:
            url = f"{self.BASE_URL}/{token_address}"
            logger.info(f"[DEXSCREENER] Requesting: {url}")
            
            async with self.session.get(url) as response:
                # Get response body first for logging
                response_text = await response.text()
                logger.debug(f"[DEXSCREENER] Response status: {response.status}, Content-Length: {len(response_text)}")
                
                if response.status == 200:
                    try:
                        data = await response.json(content_type=None)  # Allow any content type
                        logger.debug(f"[DEXSCREENER] Raw response type: {type(data)}")
                        
                        # API documentation says it always returns an array
                        if isinstance(data, list):
                            if len(data) == 0:
                                logger.info(f"[DEXSCREENER] No trading pairs found for token {token_address}")
                                return []
                            else:
                                logger.info(f"[DEXSCREENER] Found {len(data)} trading pairs for token {token_address}")
                                # Log first pair details for debugging
                                first_pair = data[0]
                                logger.debug(f"[DEXSCREENER] First pair marketCap: {first_pair.get('marketCap', 'N/A')}, dexId: {first_pair.get('dexId', 'N/A')}")
                                return data
                        else:
                            logger.error(f"[DEXSCREENER] Unexpected response format for {token_address}. Expected list, got {type(data)}")
                            logger.error(f"[DEXSCREENER] Response content: {response_text[:1000]}...")
                            return None
                            
                    except Exception as json_error:
                        logger.error(f"[DEXSCREENER] JSON parsing failed for {token_address}: {json_error}")
                        logger.error(f"[DEXSCREENER] Raw response: {response_text[:1000]}...")
                        return None
                        
                elif response.status == 404:
                    logger.info(f"[DEXSCREENER] Token {token_address} not found (404) - likely new or unlisted token")
                    return None
                    
                elif response.status == 429:  # Rate limited
                    logger.warning(f"[DEXSCREENER] Rate limited (429) for {token_address}, retry {retries + 1}/{settings.dex_max_retries}")
                    if retries < settings.dex_max_retries:
                        wait_time = 2 ** retries
                        logger.info(f"[DEXSCREENER] Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        return await self._fetch_token_data(token_address, retries + 1)
                    else:
                        logger.error(f"[DEXSCREENER] Max retries ({settings.dex_max_retries}) exceeded for {token_address}")
                        return None
                        
                elif response.status == 400:
                    logger.error(f"[DEXSCREENER] Bad request (400) for token {token_address} - invalid token address?")
                    logger.error(f"[DEXSCREENER] Response: {response_text[:500]}...")
                    return None
                    
                elif response.status >= 500:
                    logger.error(f"[DEXSCREENER] Server error ({response.status}) for token {token_address}")
                    logger.error(f"[DEXSCREENER] Response: {response_text[:500]}...")
                    return None
                    
                else:
                    logger.error(f"[DEXSCREENER] Unexpected status {response.status} for token {token_address}")
                    logger.error(f"[DEXSCREENER] Response: {response_text[:500]}...")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"[DEXSCREENER] Timeout ({settings.dex_timeout}s) fetching data for token {token_address}")
        except aiohttp.ClientError as e:
            logger.error(f"[DEXSCREENER] HTTP client error for token {token_address}: {type(e).__name__}: {e}")
        except Exception as e:
            logger.error(f"[DEXSCREENER] Unexpected error fetching token {token_address}: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[DEXSCREENER] Traceback: {traceback.format_exc()}")
        
        return None
    
    async def _fetch_batch_token_data(self, addresses: List[str], retries: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Fetch token data for multiple addresses using batch API"""
        if not self.session or not addresses:
            return None
        
        try:
            # Limit to 30 addresses per batch (API limit)
            if len(addresses) > 30:
                addresses = addresses[:30]
                logger.warning(f"Batch size limited to 30 tokens (was {len(addresses)})")
            
            # Build batch URL with comma-separated addresses
            addresses_str = ",".join(addresses)
            url = f"{self.BASE_URL}/{addresses_str}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # API returns array of pairs for batch requests
                    if isinstance(data, list):
                        return data
                    else:
                        logger.warning(f"Unexpected batch response format: {type(data)}")
                        return None
                elif response.status == 429:  # Rate limited
                    if retries < settings.dex_max_retries:
                        await asyncio.sleep(2 ** retries)  # Exponential backoff
                        return await self._fetch_batch_token_data(addresses, retries + 1)
                else:
                    logger.warning(f"DexScreener batch API returned {response.status} for {len(addresses)} tokens")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching batch data for {len(addresses)} tokens")
        except Exception as e:
            logger.error(f"Error fetching batch token data: {e}")
        
        return None
    
    async def _update_token_from_data(self, token: Dict[str, Any], api_data: List[Dict[str, Any]]):
        """Update token with data from API"""
        try:
            if not api_data:
                return
            
            best_pair = api_data[0]
            
            market_cap = best_pair.get('marketCap')
            if not market_cap:
                return
            
            new_mc = Decimal(str(market_cap))
            ticker = best_pair.get('baseToken', {}).get('symbol')

            # Update token in database
            await self.token_model.update_market_cap(token['id'], new_mc, ticker)
            
            # Check for per-target gain alerts
            await self._check_per_target_alerts(token, new_mc)

            # Check for drop alerts after market cap update
            if await self._check_drop_alerts(token, new_mc):
                return  # Stop further processing if token monitoring was stopped

            # Stop monitoring tokens below $8K market cap
            if new_mc < 8000:
                await self.token_model.set_status(token['id'], 'stopped')
                logger.info(f"Stopped monitoring {token['address'][:8]}... (MC below $8K: ${new_mc:,.0f})")
            else:
                logger.info(f"Updated {token['address'][:8]}... MC: ${new_mc:,.0f}")
            
        except Exception as e:
            logger.error(f"Error updating token from API data: {e}")

    def _format_dynamic_alert_message(self, token: Dict[str, Any], state: Dict[str, Any], current_multiplier: Decimal, alert_type: str) -> str:
        """Formats the alert message for sensitivity and threshold alerts."""
        
        def select_gain_emoji(multiplier: float) -> str:
            if multiplier < 3: return "🔥"
            if multiplier < 5: return "🚀"
            if multiplier < 10: return "🌙"
            return "🌕"

        def format_time_delta(start_time: datetime) -> str:
            if not start_time:
                return ""
            now = datetime.utcnow()
            delta = now - start_time.replace(tzinfo=None) # Ensure timezone-naive comparison
            
            days = delta.days
            hours, remainder = divmod(delta.seconds, 3600)
            minutes, _ = divmod(remainder, 60)
            
            if days > 0:
                return f"{days}d {hours}h ago"
            elif hours > 0:
                return f"{hours}h {minutes}m ago"
            else:
                return f"{minutes}m ago"

        emoji = select_gain_emoji(float(current_multiplier))
        symbol = token.get('ticker', token['address'][:6])
        mc_str = f"${state['initial_market_cap']:,.0f}"
        time_str = format_time_delta(state['first_sent_at'])

        return f"{emoji} {symbol} is at {current_multiplier:.2f}x!\nMC: {mc_str} | {time_str}"

    async def _check_per_target_alerts(self, token: Dict[str, Any], new_mc: Decimal):
        """
        Checks for and triggers sensitivity and threshold alerts for each target
        associated with the token's source group.
        """
        import json
        source_group_id = token.get('source_group_id')
        if not source_group_id:
            return

        # 1. Fetch all targets for the group that have alerts enabled
        targets = await self.target_model.get_targets_for_source_group(source_group_id, alerts_enabled_only=True)
        if not targets:
            return

        for target in targets:
            try:
                # 2. Get the alert state for this specific token-target pair
                state = await self.target_alert_state_model.get_or_create(
                    target_id=target['id'],
                    token_id=token['id'],
                    initial_market_cap=new_mc
                )

                if not state or not state['initial_market_cap'] or state['initial_market_cap'] <= 0:
                    logger.debug(f"Skipping target {target['id']} for token {token['id']}, missing baseline MC.")
                    continue

                # 3. Calculate current multiplier
                current_multiplier = new_mc / state['initial_market_cap']
                last_alert_multiplier = state['last_alert_multiplier']

                # 4. Evaluate alert modes for this target
                modes = self.target_model.parse_alert_modes(target)
                next_alert_to_fire = None
                alert_type = None

                # Check threshold alerts
                if modes.get('threshold', False):
                    thresholds = self.target_model.parse_alert_thresholds(target)
                    for threshold in sorted(thresholds):
                        if current_multiplier >= threshold and last_alert_multiplier < threshold:
                            next_alert_to_fire = Decimal(str(threshold))
                            alert_type = "Threshold"
                            break # Fire the lowest-unfired threshold
                
                # Check sensitivity alerts
                if modes.get('sensitivity', False):
                    sensitivity = self.target_model.get_alert_sensitivity_percent(target)
                    sensitivity_target = last_alert_multiplier * Decimal(1 + sensitivity)
                    if current_multiplier >= sensitivity_target:
                        # Only fire sensitivity if it's higher than a pending threshold alert
                        if next_alert_to_fire is None or current_multiplier > next_alert_to_fire:
                            next_alert_to_fire = current_multiplier
                            alert_type = "Sensitivity"

                # 5. If an alert was triggered, queue it
                if next_alert_to_fire and alert_type:
                    logger.info(f"TRIGGER: {alert_type} alert for token {token['address']} in target {target['id']} at {next_alert_to_fire:.2f}x")

                    # Get userbot assigned for forwarding
                    userbot_assignment = await db.fetchrow("SELECT userbot_id FROM userbot_assignments WHERE group_id = $1", source_group_id)
                    if not userbot_assignment or not userbot_assignment['userbot_id']:
                        logger.warning(f"No forwarding userbot for group {source_group_id}, cannot send alert.")
                        continue
                    forwarding_userbot_id = userbot_assignment['userbot_id']

                    # Format message and queue job
                    message = self._format_dynamic_alert_message(token, state, next_alert_to_fire, alert_type)
                    additional_info = json.dumps({"message_override": message})
                    source_info = json.dumps({"name": f"System {alert_type} Alerter"})

                    await self.call_queue_model.add_job(
                        token_address=token['address'],
                        target_group_id=source_group_id,
                        target_chat_id=target['dest_chat_id'],
                        forwarding_userbot_id=forwarding_userbot_id,
                        source_info=source_info,
                        additional_info=additional_info
                    )

                    # 6. Update the state with the new multiplier
                    await self.target_alert_state_model.update_after_alert(target['id'], token['id'], next_alert_to_fire)
                    logger.info(f"SUCCESS: Queued alert and updated state for token {token['id']} in target {target['id']}.")

            except Exception as e:
                logger.error(f"Error processing alerts for target {target['id']} and token {token['id']}: {e}", exc_info=True)
    
    async def _queue_pnl_command(self, token: Dict[str, Any], threshold: Decimal) -> bool:
        """Queue a /pnl command job instead of sending directly."""
        logger.debug(f"[PNL_ALERT] Queuing /pnl command for token {token['address']} at {threshold}x.")
        import json

        success_count = 0
        try:
            source_group_id = token.get('source_group_id')
            if not source_group_id:
                logger.debug(f"[PNL_ALERT] Aborting: No source_group_id found on token {token['id']}.")
                return False

            # Get the userbot assigned to the source group for forwarding
            userbot_assignment = await db.fetchrow(
                "SELECT userbot_id FROM userbot_assignments WHERE group_id = $1", source_group_id
            )
            if not userbot_assignment or not userbot_assignment['userbot_id']:
                logger.warning(f"[PNL_ALERT] No forwarding userbot assigned to group {source_group_id}. Cannot queue PNL alert.")
                return False
            forwarding_userbot_id = userbot_assignment['userbot_id']

            # Get all targets for this source group
            targets = await db.fetch("SELECT id, dest_chat_id FROM targets WHERE group_id = $1", source_group_id)
            if not targets:
                logger.warning(f"[PNL_ALERT] No targets found for source group {source_group_id}.")
                return False

            # This is a system-generated call, not from a specific user message
            source_info = json.dumps({"name": "System PNL Alerter"})
            additional_info = json.dumps({"message_override": f"/pnl {token['address']}"})

            for target in targets:
                try:
                    await self.call_queue_model.add_job(
                        token_address=token['address'],
                        target_group_id=source_group_id,
                        target_chat_id=target['dest_chat_id'],
                        forwarding_userbot_id=forwarding_userbot_id,
                        source_info=source_info,
                        additional_info=additional_info,
                        # These fields are not applicable for system PNL alerts
                        routing_rule_id=None, 
                        source_message_id=None,
                        source_chat_id=None,
                        source_user_id=None,
                    )
                    success_count += 1
                    logger.info(f"[PNL_ALERT] Queued /pnl for {token['address'][:8]}... to target {target['dest_chat_id']}")
                except Exception as e:
                    logger.error(f"Failed to queue PNL command for target {target['dest_chat_id']}: {e}")

            # Also handle curated alpha rules that want PNL alerts
            curated_rules = await db.fetch("""
                SELECT r.id as rule_id, r.destination_chat_id, r.forwarding_userbot_id
                FROM curated_alpha_rules r
                JOIN curated_alpha_token_state s ON r.id = s.rule_id
                WHERE s.token_address = $1 AND s.status = 'triggered' AND r.forward_pnl_alerts = true
            """, token['address'])

            for rule in curated_rules:
                if not rule['forwarding_userbot_id'] or not rule['destination_chat_id']:
                    continue
                try:
                    await self.call_queue_model.add_job(
                        token_address=token['address'],
                        curated_alpha_rule_id=rule['rule_id'],
                        target_chat_id=rule['destination_chat_id'],
                        forwarding_userbot_id=rule['forwarding_userbot_id'],
                        source_info=source_info,
                        additional_info=additional_info,
                    )
                    success_count += 1
                    logger.info(f"[CuratedAlpha] Queued PNL alert for {token['address'][:8]}... to curated destination {rule['destination_chat_id']}")
                except Exception as e:
                    logger.error(f"Failed to queue Curated Alpha PNL alert for destination {rule['destination_chat_id']}: {e}")

        except Exception as e:
            logger.error(f"CRITICAL: Error in _queue_pnl_command: {e}", exc_info=True)

        return success_count > 0

    def _safe_decimal(self, value: Any, default: Optional[Decimal] = None) -> Optional[Decimal]:
        """Coerce any numeric-like value into a Decimal with fallback."""
        if value is None:
            return default
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return default

    async def _fetch_jupiter_market_cap(self, token_address: str) -> Optional[Decimal]:
        """Fetch market cap from Jupiter via the Rust bridge."""
        try:
            payload = await rust_dex_bridge.fetch_dex_payload(token_address)
        except Exception as err:
            logger.error(f"[JUPITER] Error requesting payload for {token_address[:8]}...: {err}")
            return None

        if not payload:
            return None

        jupiter_payload = payload.get('jupiter') or {}
        if not jupiter_payload:
            return None

        mcap_value = (
            jupiter_payload.get('mcap')
            or jupiter_payload.get('market_cap')
            or jupiter_payload.get('marketCap')
        )

        mcap_decimal = self._safe_decimal(mcap_value, default=None)
        if mcap_decimal is None or mcap_decimal <= 0:
            return None

        return mcap_decimal

    async def _verify_with_jupiter(self, token_address: str, dex_market_cap: Decimal) -> bool:
        """Validate Dex reading against Jupiter before firing alerts."""
        if dex_market_cap is None or dex_market_cap <= 0:
            return False

        jupiter_mc = await self._fetch_jupiter_market_cap(token_address)
        if not jupiter_mc or jupiter_mc <= 0:
            logger.warning(f"[JUPITER] Missing market cap for {token_address[:8]}... during verification.")
            return False

        max_mc = max(jupiter_mc, dex_market_cap)
        if max_mc == 0:
            return False

        diff_ratio = abs(jupiter_mc - dex_market_cap) / max_mc
        if diff_ratio <= self.JUPITER_TOLERANCE:
            return True

        logger.warning(
            "[JUPITER] MC mismatch for %s (Dex: %s, Jup: %s, diff: %.2f%%)",
            token_address[:8],
            f"{dex_market_cap:,.0f}",
            f"{jupiter_mc:,.0f}",
            float(diff_ratio * 100)
        )
        return False
    
    async def _check_drop_alerts(self, token: Dict[str, Any], new_mc: Decimal) -> bool:
        """
        Check for drop alerts.
        Returns True if monitoring was stopped, False otherwise.
        """
        try:
            peak_mc = token.get('peak_mc')
            # Initialize peak_mc if it's not set
            if not peak_mc or peak_mc <= 0:
                await self.token_model.update_peak_mc(token['id'], new_mc)
                token['peak_mc'] = new_mc
                peak_mc = new_mc
    
            # Update peak if new high
            if new_mc > peak_mc:
                await self.token_model.update_peak_mc(token['id'], new_mc)
                token['peak_mc'] = new_mc
                peak_mc = new_mc
                
            # Get drop threshold from settings 
            drop_settings = await db.fetchval("SELECT value FROM settings WHERE key = 'drop_percentage'")
            if not drop_settings:
                return False
                
            import json
            drop_threshold = float(json.loads(drop_settings))
            
            # Check drop from peak
            if peak_mc > 0: # Avoid division by zero
                current_from_peak = new_mc / peak_mc
                if current_from_peak <= drop_threshold:
                    await self.token_model.set_status(token['id'], 'stopped')
                    logger.info(
                        f"Stopped monitoring {token['address'][:8]}... (MC dropped by {(1-current_from_peak)*100:.1f}%, "
                        f"below threshold of {drop_threshold*100:.0f}% of peak)"
                    )
                    return True
                        
        except Exception as e:
            logger.error(f"Error checking drop alerts: {e}")
        
        return False    
    async def add_token(self, token_address: str) -> Dict[str, Any]:
        """Add a new token for monitoring"""
        try:
            # Check if token already exists
            existing = await self.token_model.get_by_address(token_address)
            if existing:
                return {
                    'success': False,
                    'error': 'Token already being tracked',
                    'token': dict(existing)
                }
            
            # Fetch initial data
            token_data = await self._fetch_token_data(token_address)
            if not token_data:
                return {
                    'success': False,
                    'error': 'Could not fetch token data from DexScreener'
                }

            # Extract initial market cap from new API format
            pairs = token_data if isinstance(token_data, list) else token_data.get('pairs', [])
            if not pairs:
                return {
                    'success': False,
                    'error': 'No trading pairs found for token'
                }

            # Just use first pair since liquidity isn't needed
            best_pair = pairs[0]
            market_cap = best_pair.get('marketCap')

            if not market_cap:
                return {
                    'success': False,
                    'error': 'Could not determine market cap'
                }

            jupiter_mc = await self._fetch_jupiter_market_cap(token_address)
            if jupiter_mc:
                initial_mc = jupiter_mc
                logger.debug(f"[JUPITER] Using Jupiter MC {initial_mc} for token {token_address[:8]}... as first_seen_mc")
            else:
                initial_mc = Decimal(str(market_cap))
                logger.debug(f"[JUPITER] Fallback to DexScreener MC {initial_mc} for token {token_address[:8]}...")
            ticker = best_pair.get('baseToken', {}).get('symbol')

            # Create token record
            token = await self.token_model.create_or_update(token_address, initial_mc, ticker)
            
            logger.info(f"Added token {token_address[:8]}... with initial MC ${initial_mc:,.0f}")
            
            return {
                'success': True,
                'token': dict(token),
                'initial_mc': float(initial_mc)
            }
            
        except Exception as e:
            logger.error(f"Error adding token: {e}")
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
            
            logger.info(f"Stopped tracking token {token_address[:8]}...")
            
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
            
            # Get fresh data from API
            api_data = await self._fetch_token_data(token_address)
            
            result = {
                'success': True,
                'token': dict(token),
                'api_data': api_data
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
            
            return {
                'running': self.running,
                'poll_interval': settings.dex_poll_secs,
                'timeout': settings.dex_timeout,
                'max_retries': settings.dex_max_retries,
                'tokens': token_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting service stats: {e}")
            return {'error': str(e)}
