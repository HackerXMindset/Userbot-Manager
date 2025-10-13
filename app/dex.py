"""
DexScreener Token Monitoring Service

Responsibility overview:
- Initialize tokens using DexScreener data
- Poll DexScreener for fast market cap updates
- Auto-stop monitoring when liquidity drops below the configured threshold
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal

from app.config import settings
from app.db import db
from app.models import TokenModel

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
    - Token initialization using DexScreener data
    - Batch price polling (DexScreener API)
    - Drop monitoring and auto-stop
    """

    BASE_URL = "https://api.dexscreener.com/tokens/v1/solana"
    MIN_MC_THRESHOLD = Decimal('8000')  # Stop monitoring below $8K

    def __init__(self):
        self.token_model = TokenModel(db)

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
        Update token with DexScreener data

        Flow:
        1. Extract MC from DexScreener
        2. Update last_mc in database
        3. Check drop conditions
        4. Auto-stop if needed
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

            # Stop monitoring if too small
            if dex_mc < self.MIN_MC_THRESHOLD:
                await self.token_model.set_status(token['id'], 'stopped')
                logger.info(f"Stopped {token['address'][:8]}... (MC below ${self.MIN_MC_THRESHOLD}: ${dex_mc:,.0f})")
            else:
                logger.debug(f"Updated {token['address'][:8]}... MC: ${dex_mc:,.0f}")

        except Exception as e:
            logger.error(f"Error updating token from data: {e}", exc_info=True)

    # ==================== TOKEN MANAGEMENT ====================

    async def add_token(self, token_address: str) -> Dict[str, Any]:
        """
        Add a new token for monitoring without requiring external market-cap data.
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

            logger.info(f"[INIT] Registering {token_address[:8]}... without external market-cap data")

            # Create token record with zeroed financials; they'll be filled in when data becomes available.
            initial_mc = Decimal('0')
            token = await self.token_model.create_or_update(token_address, initial_mc, ticker=None)

            logger.info(f"[INIT] ✅ Registered {token_address[:8]}... with placeholder market cap $0")

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

            result = {
                'success': True,
                'token': dict(token),
                'dex_data': None
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
                'min_mc_threshold': float(self.MIN_MC_THRESHOLD),
                'tokens': token_stats
            }

        except Exception as e:
            logger.error(f"Error getting service stats: {e}")
            return {'error': str(e)}
