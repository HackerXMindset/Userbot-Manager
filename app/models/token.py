from typing import Dict, Any, Optional, List
from .base import BaseModel
from decimal import Decimal
import asyncpg

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
    
    async def create_or_update(self, address: str, market_cap: Decimal) -> asyncpg.Record:
        """Create new token or update existing"""
        query = """
            INSERT INTO tokens_tracked (address, first_seen_mc, last_mc, last_checked_at)
            VALUES ($1, $2, $2, NOW())
            ON CONFLICT (address) DO UPDATE SET
                last_mc = $2,
                last_checked_at = NOW()
            RETURNING *
        """
        return await self.db.fetchrow(query, address, market_cap)
    
    async def update_market_cap(self, token_id: int, market_cap: Decimal) -> asyncpg.Record:
        """Update token's market cap"""
        query = """
            UPDATE tokens_tracked 
            SET last_mc = $1, 
                first_seen_mc = COALESCE(first_seen_mc, $1),
                last_checked_at = NOW()
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, market_cap, token_id)
    
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