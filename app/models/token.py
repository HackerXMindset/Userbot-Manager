import logging
import asyncpg
from typing import Dict, Any, Optional, List
from .base import BaseModel
from decimal import Decimal

logger = logging.getLogger(__name__)

class TokenModel(BaseModel):
    """Model for managing tracked tokens"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "tokens_tracked"
    
    async def get_by_address(self, address: str) -> Optional[asyncpg.Record]:
        """Get token by address"""
        query = "SELECT * FROM tokens_tracked WHERE address = $1"
        return await self.db.fetchrow(query, address)
    
    async def get_active_tokens(self) -> List[asyncpg.Record]:
        """Get all active tokens"""
        query = """
            SELECT * FROM tokens_tracked 
            WHERE status = 'active'
            ORDER BY first_seen_at DESC
        """
        return await self.db.fetch(query)
    
    async def create_or_update(self, address: str, market_cap: Decimal, ticker: Optional[str] = None) -> asyncpg.Record:
        """Create new token or update existing, initializing peak_mc."""
        try:
            # First, try the query WITH the ticker column
            query = """
                INSERT INTO tokens_tracked (address, first_seen_mc, last_mc, peak_mc, ticker, last_checked_at)
                VALUES ($1, $2, $2, $2, $3, NOW())
                ON CONFLICT (address) DO UPDATE SET
                    last_mc = $2,
                    ticker = COALESCE($3, tokens_tracked.ticker),
                    last_checked_at = NOW()
                RETURNING *
            """
            return await self.db.fetchrow(query, address, market_cap, ticker)
        except asyncpg.exceptions.UndefinedColumnError:
            logger.warning("tokens_tracked schema appears to be outdated (missing 'ticker' column). Falling back. Please update your database.")
            # Fallback query WITHOUT the ticker column
            query_fallback = """
                INSERT INTO tokens_tracked (address, first_seen_mc, last_mc, peak_mc, last_checked_at)
                VALUES ($1, $2, $2, $2, NOW())
                ON CONFLICT (address) DO UPDATE SET
                    last_mc = $2,
                    last_checked_at = NOW()
                RETURNING *
            """
            return await self.db.fetchrow(query_fallback, address, market_cap)

    async def update_market_cap(self, token_id: int, market_cap: Decimal, ticker: Optional[str] = None) -> asyncpg.Record:
        """Update token's market cap and optionally its ticker."""
        try:
            # First, try the query WITH the ticker column
            query = """
                UPDATE tokens_tracked 
                SET last_mc = $1, 
                    first_seen_mc = CASE
                        WHEN first_seen_mc IS NULL OR first_seen_mc <= 0 THEN $1
                        ELSE first_seen_mc
                    END,
                    ticker = COALESCE($3, ticker),
                    last_checked_at = NOW()
                WHERE id = $2
                RETURNING *
            """
            return await self.db.fetchrow(query, market_cap, token_id, ticker)
        except asyncpg.exceptions.UndefinedColumnError:
            logger.warning("tokens_tracked schema appears to be outdated (missing 'ticker' column). Falling back. Please update your database.")
            # Fallback query WITHOUT the ticker column
            query_fallback = """
                UPDATE tokens_tracked 
                SET last_mc = $1, 
                    first_seen_mc = CASE
                        WHEN first_seen_mc IS NULL OR first_seen_mc <= 0 THEN $1
                        ELSE first_seen_mc
                    END,
                    last_checked_at = NOW()
                WHERE id = $2
                RETURNING *
            """
            return await self.db.fetchrow(query_fallback, market_cap, token_id)

    async def set_status(self, token_id: int, status: str) -> None:
        """Update token status"""
        query = "UPDATE tokens_tracked SET status = $1 WHERE id = $2"
        await self.db.execute(query, status, token_id)
    
    async def update_hit_multiplier(self, token_id: int, multiplier: Decimal) -> None:
        """Update last hit multiplier"""
        query = "UPDATE tokens_tracked SET last_hit_multiplier = $1 WHERE id = $2"
        await self.db.execute(query, multiplier, token_id)
    
    async def update_peak_mc(self, token_id: int, peak_mc: Decimal) -> None:
        """Update peak market cap"""
        query = "UPDATE tokens_tracked SET peak_mc = $1 WHERE id = $2"
        await self.db.execute(query, peak_mc, token_id)
    
    
    async def get_token_stats(self) -> Dict[str, Any]:
        """Get token statistics"""
        query = """
            SELECT 
                COUNT(*) as total_tokens,
                COUNT(*) FILTER (WHERE status = 'active') as active_tokens,
                COUNT(*) FILTER (WHERE status = 'stopped') as stopped_tokens,
                AVG(last_mc / first_seen_mc) as avg_multiplier
            FROM tokens_tracked
            WHERE first_seen_mc > 0
        """
        result = await self.db.fetchrow(query)
        return dict(result) if result else {}
    
    async def get_performance_tokens(self, limit: int = 10) -> List[asyncpg.Record]:
        """Get top performing tokens"""
        query = """
            SELECT *, 
                   (last_mc / first_seen_mc) as current_multiplier
            FROM tokens_tracked 
            WHERE first_seen_mc > 0 AND status = 'active'
            ORDER BY (last_mc / first_seen_mc) DESC
            LIMIT $1
        """
        return await self.db.fetch(query, limit)
    
    async def cleanup_old_tokens(self, days: int = 30) -> int:
        """Remove old inactive tokens"""
        query = """
            DELETE FROM tokens_tracked
            WHERE status = 'stopped'
            AND last_checked_at < NOW() - INTERVAL '%s days'
            RETURNING id
        """
        results = await self.db.fetch(query % days)
        return len(results)

    # Gain alert system methods

    async def update_tier(self, token_id: int, tier: str, next_poll_at) -> None:
        """Update token's current tier and next poll time"""
        query = """
            UPDATE tokens_tracked
            SET current_tier = $1, next_poll_at = $2
            WHERE id = $3
        """
        await self.db.execute(query, tier, next_poll_at, token_id)

    async def update_last_alert_mc(self, token_id: int, alert_mc: Decimal) -> None:
        """Update last alert market cap"""
        query = "UPDATE tokens_tracked SET last_alert_mc = $1 WHERE id = $2"
        await self.db.execute(query, alert_mc, token_id)

    async def set_stop_reason(self, token_id: int, reason: str) -> None:
        """Set stop reason for a token"""
        query = "UPDATE tokens_tracked SET stop_reason = $1 WHERE id = $2"
        await self.db.execute(query, reason, token_id)

    async def update_dex_refresh_time(self, token_id: int) -> None:
        """Update DexScreener refresh timestamp"""
        query = "UPDATE tokens_tracked SET dex_screener_refreshed_at = NOW() WHERE id = $1"
        await self.db.execute(query, token_id)

    async def get_tokens_by_next_poll(self, limit: int = 100) -> List[asyncpg.Record]:
        """Get active tokens ordered by next poll time for scheduler"""
        query = """
            SELECT * FROM tokens_tracked
            WHERE status = 'active'
            AND next_poll_at IS NOT NULL
            AND next_poll_at <= NOW()
            ORDER BY next_poll_at ASC
            LIMIT $1
        """
        return await self.db.fetch(query, limit)

    async def get_all_active_scheduled_tokens(self) -> List[asyncpg.Record]:
        """Get all active tokens with polling schedules for scheduler initialization"""
        query = """
            SELECT * FROM tokens_tracked
            WHERE status = 'active'
            AND next_poll_at IS NOT NULL
            ORDER BY next_poll_at ASC
        """
        return await self.db.fetch(query)

    async def update_original_message_id(self, token_id: int, message_id: int) -> None:
        """Store the original message ID for reply support"""
        query = "UPDATE tokens_tracked SET original_message_id = $1 WHERE id = $2"
        await self.db.execute(query, message_id, token_id)
