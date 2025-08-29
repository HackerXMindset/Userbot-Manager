from typing import Dict, Any, Optional, List
from .base import BaseModel
from decimal import Decimal
import asyncpg

class EventModel(BaseModel):
    """Model for managing events"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "events"
    
    async def create_event(self, kind: str, src_chat_id: int, src_msg_id: int, 
                          user_id: int, payload: Dict[str, Any], 
                          token_id: Optional[int] = None) -> asyncpg.Record:
        """Create a new event"""
        query = """
            INSERT INTO events (kind, src_chat_id, src_msg_id, user_id, token_id, payload)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
        """
        return await self.db.fetchrow(query, kind, src_chat_id, src_msg_id, user_id, token_id, payload)
    
    async def get_events_by_type(self, kind: str, limit: int = 100) -> List[asyncpg.Record]:
        """Get events by type"""
        query = """
            SELECT * FROM events 
            WHERE kind = $1 
            ORDER BY created_at DESC 
            LIMIT $2
        """
        return await self.db.fetch(query, kind, limit)
    
    async def get_events_by_chat(self, src_chat_id: int, limit: int = 50) -> List[asyncpg.Record]:
        """Get events from a specific chat"""
        query = """
            SELECT * FROM events 
            WHERE src_chat_id = $1 
            ORDER BY created_at DESC 
            LIMIT $2
        """
        return await self.db.fetch(query, src_chat_id, limit)
    
    async def mark_routed(self, event_id: int, channel_id: int) -> None:
        """Mark event as routed to notification channel"""
        query = "UPDATE events SET routed_to_channel_id = $1 WHERE id = $2"
        await self.db.execute(query, channel_id, event_id)
    
    async def get_unrouted_events(self, kind: Optional[str] = None) -> List[asyncpg.Record]:
        """Get events that haven't been routed yet"""
        if kind:
            query = """
                SELECT * FROM events 
                WHERE routed_to_channel_id IS NULL AND kind = $1
                ORDER BY created_at ASC
            """
            return await self.db.fetch(query, kind)
        else:
            query = """
                SELECT * FROM events 
                WHERE routed_to_channel_id IS NULL
                ORDER BY created_at ASC
            """
            return await self.db.fetch(query)
    
    async def get_event_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get event statistics"""
        query = """
            SELECT 
                kind,
                COUNT(*) as count,
                COUNT(*) FILTER (WHERE routed_to_channel_id IS NOT NULL) as routed_count
            FROM events 
            WHERE created_at > NOW() - INTERVAL '%s days'
            GROUP BY kind
            ORDER BY count DESC
        """
        results = await self.db.fetch(query % days)
        return {r['kind']: {'count': r['count'], 'routed': r['routed_count']} for r in results}

class AlertModel(BaseModel):
    """Model for managing alerts"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "alerts"
    
    async def create_alert(self, token_id: int, alert_type: str, 
                          multiplier: Decimal, threshold: Decimal,
                          channel_id: Optional[int] = None) -> asyncpg.Record:
        """Create a new alert"""
        query = """
            INSERT INTO alerts (token_id, alert_type, multiplier, threshold, channel_id)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        return await self.db.fetchrow(query, token_id, alert_type, multiplier, threshold, channel_id)
    
    async def get_alerts_by_token(self, token_id: int) -> List[asyncpg.Record]:
        """Get all alerts for a token"""
        query = """
            SELECT * FROM alerts 
            WHERE token_id = $1 
            ORDER BY triggered_at DESC
        """
        return await self.db.fetch(query, token_id)
    
    async def has_alert_fired(self, token_id: int, alert_type: str, multiplier: Decimal) -> bool:
        """Check if specific alert has already fired for a token"""
        query = """
            SELECT EXISTS(
                SELECT 1 FROM alerts 
                WHERE token_id = $1 AND alert_type = $2 AND multiplier = $3
            )
        """
        return await self.db.fetchval(query, token_id, alert_type, multiplier)
    
    async def update_posted_message(self, alert_id: int, msg_id: int, channel_id: int) -> None:
        """Update alert with posted message info"""
        query = """
            UPDATE alerts 
            SET posted_msg_id = $1, channel_id = $2 
            WHERE id = $3
        """
        await self.db.execute(query, msg_id, channel_id, alert_id)
    
    async def get_recent_alerts(self, hours: int = 24) -> List[asyncpg.Record]:
        """Get recent alerts with token info"""
        query = """
            SELECT a.*, t.address, t.first_seen_mc, t.last_mc
            FROM alerts a
            JOIN tokens_tracked t ON t.id = a.token_id
            WHERE a.triggered_at > NOW() - INTERVAL '%s hours'
            ORDER BY a.triggered_at DESC
        """
        return await self.db.fetch(query % hours)
    
    async def get_alert_stats(self, days: int = 7) -> Dict[str, Any]:
        """Get alert statistics"""
        query = """
            SELECT 
                alert_type,
                COUNT(*) as count,
                AVG(multiplier) as avg_multiplier,
                MAX(multiplier) as max_multiplier
            FROM alerts 
            WHERE triggered_at > NOW() - INTERVAL '%s days'
            GROUP BY alert_type
            ORDER BY count DESC
        """
        results = await self.db.fetch(query % days)
        return {
            r['alert_type']: {
                'count': r['count'], 
                'avg_multiplier': float(r['avg_multiplier'] or 0),
                'max_multiplier': float(r['max_multiplier'] or 0)
            } 
            for r in results
        }