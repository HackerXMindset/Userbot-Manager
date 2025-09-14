from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg

class GroupModel(BaseModel):
    """Model for managing group records"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "groups"
    
    async def get_by_chat_id(self, tg_chat_id: int) -> Optional[asyncpg.Record]:
        """Get group by Telegram chat ID"""
        query = "SELECT * FROM groups WHERE tg_chat_id = $1"
        return await self.db.fetchrow(query, tg_chat_id)
    
    async def get_enabled_groups(self) -> List[asyncpg.Record]:
        """Get all enabled groups"""
        query = """
            SELECT g.*, ua.userbot_id, b.session_name as userbot_name
            FROM groups g
            LEFT JOIN userbot_assignments ua ON ua.group_id = g.id
            LEFT JOIN bots b ON b.id = ua.userbot_id
            WHERE g.enabled = true
            ORDER BY g.id
        """
        return await self.db.fetch(query)
    
    async def get_groups_with_stats(self) -> List[asyncpg.Record]:
        """Get groups with statistics"""
        query = """
            SELECT g.*, 
                   COUNT(DISTINCT t.id) as targets_count,
                   COUNT(DISTINCT s.id) as schedules_count,
                   ua.userbot_id,
                   COALESCE(b.display_name, b.session_name) as userbot_name,
                   (SELECT COUNT(*) FROM calls WHERE group_id = g.id AND sent_at > CURRENT_DATE) as calls_today
            FROM groups g
            LEFT JOIN targets t ON t.group_id = g.id
            LEFT JOIN group_schedules s ON s.group_id = g.id
            LEFT JOIN userbot_assignments ua ON ua.group_id = g.id
            LEFT JOIN bots b ON b.id = ua.userbot_id
            GROUP BY g.id, g.display_name, ua.userbot_id, b.session_name, b.display_name
            ORDER BY g.enabled DESC, g.id DESC
        """
        return await self.db.fetch(query)
    
    async def toggle_enabled(self, group_id: int) -> bool:
        """Toggle group enabled status"""
        query = """
            UPDATE groups 
            SET enabled = NOT enabled 
            WHERE id = $1 
            RETURNING enabled
        """
        result = await self.db.fetchval(query, group_id)
        return result
    
    async def set_quota(self, group_id: int, daily_cap: int) -> None:
        """Set daily quota for group"""
        query = "UPDATE groups SET daily_cap = $1 WHERE id = $2"
        await self.db.execute(query, daily_cap, group_id)
    
    async def set_cooldown(self, group_id: int, minutes: int) -> None:
        """Set cooldown minutes for group"""
        query = "UPDATE groups SET cooldown_minutes = $1 WHERE id = $2"
        await self.db.execute(query, minutes, group_id)
    
    async def get_targets(self, group_id: int) -> List[asyncpg.Record]:
        """Get all targets for a group"""
        query = "SELECT * FROM targets WHERE group_id = $1"
        return await self.db.fetch(query, group_id)
    
    async def add_target(self, group_id: int, dest_chat_id: int) -> asyncpg.Record:
        """Add target channel for group"""
        query = """
            INSERT INTO targets (group_id, dest_chat_id)
            VALUES ($1, $2)
            ON CONFLICT (group_id, dest_chat_id) DO NOTHING
            RETURNING *
        """
        return await self.db.fetchrow(query, group_id, dest_chat_id)
    
    async def remove_target(self, group_id: int, dest_chat_id: int) -> bool:
        """Remove target from group"""
        query = "DELETE FROM targets WHERE group_id = $1 AND dest_chat_id = $2"
        result = await self.db.execute(query, group_id, dest_chat_id)
        return result.split()[-1] == '1'

    async def get_targets_with_group_info(self) -> List[asyncpg.Record]:
        query = """
            SELECT 
                t.*, 
                g.title as group_title,
                dest_g.display_name as dest_group_display_name,
                dest_g.title as dest_group_title
            FROM targets t
            JOIN groups g ON g.id = t.group_id
            LEFT JOIN groups dest_g ON dest_g.tg_chat_id = t.dest_chat_id
            ORDER BY g.title, t.dest_chat_id
        """
        return await self.db.fetch(query)

class ScheduleModel(BaseModel):
    """Model for managing group schedules"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "group_schedules"
    
    async def get_by_group(self, group_id: int) -> List[asyncpg.Record]:
        """Get all schedules for a group"""
        query = """
            SELECT * FROM group_schedules 
            WHERE group_id = $1 
            ORDER BY start_time
        """
        return await self.db.fetch(query, group_id)
    
    async def create_schedule(self, group_id: int, weekdays: List[int], 
                            start_time: str, end_time: str, max_calls: int = 0) -> asyncpg.Record:
        """Create a new schedule"""
        query = """
            INSERT INTO group_schedules (group_id, weekdays, start_time, end_time, max_calls_in_window)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """
        return await self.db.fetchrow(query, group_id, weekdays, start_time, end_time, max_calls)
    
    async def delete_schedule(self, schedule_id: int) -> bool:
        """Delete a schedule"""
        query = "DELETE FROM group_schedules WHERE id = $1"
        result = await self.db.execute(query, schedule_id)
        return result.split()[-1] == '1'
    
    async def get_active_schedules(self, current_day: int, current_time) -> List[asyncpg.Record]:
        """Get currently active schedules"""
        query = """
            SELECT gs.*, g.tg_chat_id, g.enabled, g.daily_cap, g.cooldown_minutes,
                   ua.userbot_id, b.session_name as userbot_name
            FROM group_schedules gs
            JOIN groups g ON g.id = gs.group_id
            LEFT JOIN userbot_assignments ua ON ua.group_id = g.id
            LEFT JOIN bots b ON b.id = ua.userbot_id
            WHERE g.enabled = true
            AND $1 = ANY(gs.weekdays)
            AND gs.start_time <= $2
            AND gs.end_time >= $2
            AND b.status = 'active'
        """
        return await self.db.fetch(query, current_day, current_time)