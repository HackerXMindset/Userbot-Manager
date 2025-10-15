"""
Token Monitor - Handles token detection and tracking from source messages
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.db import db
from .utils import UserbotUtils
from app.services.okx_market_api import get_okx_market_client

logger = logging.getLogger(__name__)


class TokenMonitor:
    """Monitors and processes token addresses from messages"""
    
    def __init__(self, userbot_id: int):
        self.userbot_id = userbot_id
        self.utils = UserbotUtils()
        self.okx_client = get_okx_market_client()
    
    async def process_source_message(self, event, source_chat_id: int, target_groups: List[Dict[str, Any]] = None) -> List[tuple]:
        """Process a message from a source chat and extract tokens

        Returns:
            List of tuples: [(address, blockchain), ...]
        """
        try:
            message = event.message
            text = self.utils.get_message_text(message)

            # Debug logging for message content
            logger.debug(f"[TOKEN_EXTRACT] Source {source_chat_id} - Message text: {text[:200] if text else 'EMPTY'}")
            logger.debug(f"[TOKEN_EXTRACT] Message type: {type(message).__name__}, has text attr: {hasattr(message, 'text')}, text value: {message.text if hasattr(message, 'text') else 'N/A'}")

            # Extract all token addresses with blockchain tags
            tagged_addresses = self.utils.extract_token_addresses(text)

            # Count by blockchain for logging
            sol_count = sum(1 for _, chain in tagged_addresses if chain == "SOL")
            bnb_count = sum(1 for _, chain in tagged_addresses if chain == "BNB")

            logger.debug(f"[TOKEN_EXTRACT] Extracted {len(tagged_addresses)} addresses from source {source_chat_id}: {sol_count} SOL, {bnb_count} BNB")

            if tagged_addresses:
                logger.info(f"Found {len(tagged_addresses)} token(s) in source {source_chat_id}: {[(addr, chain) for addr, chain in tagged_addresses]}")

                # Process each token
                for address, blockchain in tagged_addresses:
                    await self._process_token_address(address, blockchain, event, target_groups or [])

            return tagged_addresses
            
        except Exception as e:
            logger.error(f"Error processing source message: {e}")
            return []
    
    async def _process_token_address(self, address: str, blockchain: str, event, target_groups: List[Dict[str, Any]]):
        """Process a single token address"""
        try:
            # Add token to tracking system with target groups
            token_id = await self._add_token_to_tracking(address, blockchain, target_groups)

            if token_id is not None:
                # Log token detection
                source_title = self.utils.get_chat_title(event.chat)
                user_name = self.utils.get_user_name(event.sender)

                logger.info(f"Token {address} detected from {source_title} by {user_name}")
            
        except Exception as e:
            logger.error(f"Error processing token address {address}: {e}")
    
    async def _fetch_market_snapshot(self, address: str, blockchain: str) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[str]]:
        """Fetch current market data for a token."""
        from app.services.jupiter_api import get_jupiter_service

        jupiter_service = get_jupiter_service()
        market_cap: Optional[Decimal] = None
        price: Optional[Decimal] = None
        ticker: Optional[str] = None
        token_data = None

        if blockchain.upper() == "SOL":
            token_data = await jupiter_service.get_token_data(address, use_cache=False)

        okx_info = await self.okx_client.fetch_token_info(address, blockchain)
        if okx_info:
            market_cap = self._normalize_decimal(self.okx_client.get_market_cap(okx_info))
            price = self._normalize_decimal(self.okx_client.get_price(okx_info))
            ticker = self.okx_client.get_ticker(okx_info)

        if market_cap is None:
            if token_data is None:
                token_data = await jupiter_service.get_token_data(address, use_cache=False)
            if token_data:
                market_cap = self._normalize_decimal(jupiter_service.get_market_cap(token_data))
                price = price or self._normalize_decimal(jupiter_service.get_price(token_data))
                ticker = ticker or jupiter_service.get_ticker(token_data)

        return market_cap, price, ticker

    async def _add_token_to_tracking(self, address: str, blockchain: str, target_groups: List[Dict[str, Any]]) -> Optional[int]:
        """Add token to tracking database with Jupiter snapshot"""
        try:
            # Add to DexScreener service for tracking - this creates the initial record
            from app.dex import get_dex_service

            dex_service = get_dex_service()

            result = await dex_service.add_token(address)

            if not result['success']:
                logger.info(f"Skipping Dex registration for {address}: {result.get('error', 'no data available')}")
                return None

            # Fetch market snapshot for baseline configuration
            market_cap, price, ticker = await self._fetch_market_snapshot(address, blockchain)

            # Use first target group as primary source group for routing
            source_group_id = target_groups[0]['id'] if target_groups else None

            if market_cap and market_cap > 0:
                # Validate market cap bounds
                from app.config import MIN_VALID_MARKET_CAP, MAX_VALID_MARKET_CAP

                if not (Decimal(MIN_VALID_MARKET_CAP) <= market_cap <= Decimal(MAX_VALID_MARKET_CAP)):
                    logger.warning(
                        f"[JUPITER_SNAPSHOT] {address} MC out of valid range: "
                        f"${float(market_cap):,.2f} (valid: ${MIN_VALID_MARKET_CAP:,} - ${MAX_VALID_MARKET_CAP:,}), skipping"
                    )
                    return None

                # Successfully got valid Jupiter data - initialize gain alert fields
                logger.info(f"[JUPITER_SNAPSHOT] {address} MC: ${float(market_cap):,.2f}, Ticker: {ticker}")

                token_record = await db.fetchrow("""
                    UPDATE tokens_tracked
                    SET source_group_id = COALESCE(source_group_id, $2),
                        first_seen_mc = $3,
                        last_mc = $3,
                        ticker = COALESCE($4, ticker),
                        current_tier = 'tier_a',
                        next_poll_at = NOW() + INTERVAL '10 seconds',
                        last_checked_at = NOW()
                    WHERE address = $1
                    RETURNING id
                """, address, source_group_id, market_cap, ticker)
            else:
                # Jupiter miss - still schedule Tier A for retry but log warning
                logger.warning(f"[JUPITER_SNAPSHOT] No market cap data for {address}, scheduling Tier A retry")

                token_record = await db.fetchrow("""
                    UPDATE tokens_tracked
                    SET source_group_id = COALESCE(source_group_id, $2),
                        current_tier = 'tier_a',
                        next_poll_at = NOW() + INTERVAL '10 seconds',
                        last_checked_at = NOW()
                    WHERE address = $1
                    RETURNING id
                """, address, source_group_id)

            if token_record:
                token_id = token_record['id']
                logger.debug(f"Token {address} updated in tracking (ID: {token_id}, Group: {source_group_id})")

                # Add token to scheduler heap for polling
                await dex_service.add_token_to_scheduler(token_id)

                return token_id
            else:
                logger.error(f"Token {address} not found after DexScreener add")
                return None

        except Exception as e:
            logger.error(f"Error adding token to tracking: {e}")
            return None

    async def process_monitored_token(
        self,
        address: str,
        blockchain: str,
        chat_id: int,
        message_id: Optional[int],
        user_id: Optional[int],
        chat_type: Optional[str] = None,
    ) -> None:
        """Create per-chat tracking when a monitored source posts a token."""
        try:
            if message_id is None:
                logger.debug(f"[MONITOR_DETECT] Missing message_id for {address} in chat {chat_id}, skipping")
                return

            token = await db.fetchrow("SELECT id FROM tokens_tracked WHERE address = $1", address)
            if token:
                token_id = token["id"]
            else:
                token_id = await self._add_token_to_tracking(address, blockchain, [])
                if token_id is None:
                    logger.warning(f"[MONITOR_DETECT] Unable to register {address} for chat {chat_id}")
                    return

            market_cap, _, _ = await self._fetch_market_snapshot(address, blockchain)

            if market_cap is None or market_cap <= 0:
                logger.warning(f"[MONITOR_DETECT] Invalid market cap for {address[:8]}...: {market_cap}, skipping")
                return

            from app.config import MIN_VALID_MARKET_CAP, MAX_VALID_MARKET_CAP

            min_cap = Decimal(MIN_VALID_MARKET_CAP)
            max_cap = Decimal(MAX_VALID_MARKET_CAP)

            if not (min_cap <= market_cap <= max_cap):
                logger.warning(
                    f"[MONITOR_DETECT] Market cap for {address[:8]}... out of range: "
                    f"${float(market_cap):,.2f} (valid ${MIN_VALID_MARKET_CAP:,} - ${MAX_VALID_MARKET_CAP:,}), skipping"
                )
                return

            result = await db.fetchrow("""
                INSERT INTO token_group_alerts
                (token_id, chat_id, first_seen_mc, original_message_id, original_user_id)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (token_id, chat_id) DO NOTHING
                RETURNING id
            """, token_id, chat_id, market_cap, message_id, user_id)

            if result:
                logger.info(
                    f"[GROUP_ALERT_NEW] Token {address[:8]}... monitoring started for chat {chat_id} "
                    f"(type={chat_type or 'unknown'}) at ${float(market_cap):,.2f}"
                )
            else:
                logger.debug(f"[GROUP_ALERT_DUP] Chat {chat_id} already tracking token {address[:8]}..., skipping")

        except Exception as exc:
            logger.error(
                f"[MONITOR_DETECT] Error processing monitored token {address[:8]}... for chat {chat_id}: {exc}",
                exc_info=True,
            )
    
    async def get_token_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Get token record by address"""
        try:
            return await db.fetchrow("""
                SELECT * FROM tokens_tracked WHERE address = $1
            """, address)
        except Exception as e:
            logger.error(f"Error getting token by address: {e}")
            return None
    
    async def update_token_stats(self, address: str, stats: Dict[str, Any]):
        """Update token statistics"""
        try:
            await db.execute("""
                UPDATE tokens_tracked 
                SET 
                    last_price = $2,
                    market_cap = $3,
                    volume_24h = $4,
                    last_checked_at = NOW()
                WHERE address = $1
            """, address, 
                stats.get('price'),
                stats.get('market_cap'), 
                stats.get('volume_24h')
            )
            
            logger.debug(f"Updated stats for token {address}...")
            
        except Exception as e:
            logger.error(f"Error updating token stats: {e}")
    
    async def get_recent_tokens(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recently detected tokens"""
        try:
            return await db.fetch("""
                SELECT * FROM tokens_tracked 
                ORDER BY created_at DESC 
                LIMIT $1
            """, limit)
        except Exception as e:
            logger.error(f"Error getting recent tokens: {e}")
            return []
    
    async def get_token_stats(self) -> Dict[str, Any]:
        """Get token monitoring statistics"""
        try:
            stats = await db.fetchrow("""
                SELECT 
                    COUNT(*) as total_tokens,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day') as today_tokens,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as hour_tokens,
                    COUNT(*) FILTER (WHERE status = 'active') as active_tokens
                FROM tokens_tracked
            """)
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting token stats: {e}")
            return {}
    
    async def cleanup_old_tokens(self, days_old: int = 30):
        """Clean up old token records"""
        try:
            deleted_count = await db.fetchval("""
                DELETE FROM tokens_tracked
                WHERE created_at < NOW() - INTERVAL $1
                AND status != 'active'
                RETURNING COUNT(*)
            """, f"{days_old} days")
            
            if deleted_count:
                logger.info(f"Cleaned up {deleted_count} old token records")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old tokens: {e}")
            return 0

    @staticmethod
    def _normalize_decimal(value: Optional[Any]) -> Optional[Decimal]:
        """Best-effort conversion of numeric inputs to Decimal."""
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
