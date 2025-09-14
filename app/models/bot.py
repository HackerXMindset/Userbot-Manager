from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg

class BotModel(BaseModel):
    """Model for managing bot records"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "bots"
    
    async def get_by_session_name(self, session_name: str) -> Optional[asyncpg.Record]:
        """Get bot by session name"""
        query = "SELECT * FROM bots WHERE session_name = $1"
        return await self.db.fetchrow(query, session_name)
    
    async def get_active_userbots(self) -> List[asyncpg.Record]:
        """Get all active userbots"""
        query = """
            SELECT * FROM bots 
            WHERE kind = 'userbot' AND status = 'active'
            ORDER BY last_seen DESC
        """
        return await self.db.fetch(query)
    
    async def get_userbots_with_assignments(self) -> List[asyncpg.Record]:
        """Get userbots with their group assignments"""
        query = """
            SELECT b.*, 
                   COUNT(ua.group_id) as assigned_groups,
                   ARRAY_AGG(ua.group_id) FILTER (WHERE ua.group_id IS NOT NULL) as group_ids
            FROM bots b
            LEFT JOIN userbot_assignments ua ON ua.userbot_id = b.id
            WHERE b.kind = 'userbot'
            GROUP BY b.id
            ORDER BY b.status DESC, b.last_seen DESC
        """
        return await self.db.fetch(query)
    
    async def update_last_seen(self, bot_id: int) -> None:
        """Update bot's last seen timestamp"""
        query = "UPDATE bots SET last_seen = NOW() WHERE id = $1"
        await self.db.execute(query, bot_id)
    
    async def set_status(self, bot_id: int, status: str) -> None:
        """Update bot status"""
        query = "UPDATE bots SET status = $1, last_seen = NOW() WHERE id = $2"
        await self.db.execute(query, status, bot_id)
    
    async def assign_to_group(self, userbot_id: int, group_id: int) -> asyncpg.Record:
        """Assign userbot to a group, ensuring the group is only assigned to one userbot."""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                # Remove any existing assignment for this group to enforce a one-to-one mapping
                await conn.execute(
                    "DELETE FROM userbot_assignments WHERE group_id = $1",
                    group_id
                )
                # Insert the new assignment
                query = """
                    INSERT INTO userbot_assignments (userbot_id, group_id)
                    VALUES ($1, $2)
                    RETURNING *
                """
                return await conn.fetchrow(query, userbot_id, group_id)
    
    async def unassign_from_group(self, group_id: int) -> bool:
        """Remove userbot assignment from group"""
        query = "DELETE FROM userbot_assignments WHERE group_id = $1"
        result = await self.db.execute(query, group_id)
        return result.split()[-1] == '1'
    
    async def get_assigned_groups(self, userbot_id: int) -> List[asyncpg.Record]:
        """Get groups assigned to a userbot"""
        query = """
            SELECT g.* FROM groups g
            JOIN userbot_assignments ua ON ua.group_id = g.id
            WHERE ua.userbot_id = $1
        """
        return await self.db.fetch(query, userbot_id)