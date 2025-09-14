from typing import Optional, List
from .base import BaseModel
import asyncpg

class NotificationSettingsModel(BaseModel):
    """Model for managing notification settings"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "notification_settings"
    
    async def get_settings(self) -> Optional[asyncpg.Record]:
        """Get notification settings"""
        query = "SELECT * FROM notification_settings LIMIT 1"
        return await self.db.fetchrow(query)
    
    async def set_notification_channel(self, channel_id: int) -> asyncpg.Record:
        """Set the notification channel"""
        # There should only be one row in this table
        await self.db.execute("DELETE FROM notification_settings")
        return await self.create({'notification_channel_id': channel_id})

class NotificationBlacklistModel(BaseModel):
    """Model for managing the notification blacklist"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "notification_blacklist"
    
    async def get_all(self) -> List[asyncpg.Record]:
        """Get all blacklisted users"""
        query = "SELECT * FROM notification_blacklist"
        return await self.db.fetch(query)
    
    async def add_user(self, user_id: int) -> asyncpg.Record:
        """Add a user to the blacklist"""
        return await self.create({'user_id': user_id})
    
    async def remove_user(self, user_id: int) -> bool:
        """Remove a user from the blacklist"""
        query = "DELETE FROM notification_blacklist WHERE user_id = $1"
        result = await self.db.execute(query, user_id)
        return result.split()[-1] == '1'
    
    async def is_blacklisted(self, user_id: int) -> bool:
        """Check if a user is blacklisted"""
        query = "SELECT EXISTS(SELECT 1 FROM notification_blacklist WHERE user_id = $1)"
        return await self.db.fetchval(query, user_id)
