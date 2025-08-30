from typing import Dict, Any, Optional, List
from .base import BaseModel
import json
import asyncpg

class NotificationModel(BaseModel):
    """Model for managing notification settings"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "notification_settings"
    
    async def get_settings(self) -> Optional[asyncpg.Record]:
        """Get current notification settings"""
        query = "SELECT * FROM notification_settings ORDER BY created_at DESC LIMIT 1"
        return await self.db.fetchrow(query)
    
    async def set_notification_channel(self, channel_id: int) -> None:
        """Set the notification channel ID"""
        await self.db.execute("""
            INSERT INTO notification_settings (notification_channel_id, blacklisted_user_ids, event_types_enabled)
            VALUES ($1, '{}', '{"reply": true, "mention": true, "dm": true, "token_call": false}')
            ON CONFLICT DO NOTHING
        """, channel_id)
        
        await self.db.execute("""
            UPDATE notification_settings 
            SET notification_channel_id = $1, updated_at = NOW()
            WHERE id = (SELECT id FROM notification_settings ORDER BY created_at DESC LIMIT 1)
        """, channel_id)
    
    async def clear_notification_channel(self) -> bool:
        """Clear the notification channel configuration"""
        try:
            await self.db.execute("""
                UPDATE notification_settings 
                SET notification_channel_id = NULL, updated_at = NOW()
                WHERE id = (SELECT id FROM notification_settings ORDER BY created_at DESC LIMIT 1)
            """)
            return True
        except Exception as e:
            logger.error(f"Error clearing notification channel: {e}")
            return False
    
    async def add_to_blacklist(self, user_id: int) -> bool:
        """Add a user to the blacklist"""
        try:
            # Get current settings
            settings = await self.get_settings()
            if not settings:
                # Create initial settings
                await self.db.execute("""
                    INSERT INTO notification_settings (blacklisted_user_ids, event_types_enabled)
                    VALUES ($1, '{"reply": true, "mention": true, "dm": true, "token_call": false}')
                """, [user_id])
                return True
            
            current_blacklist = list(settings['blacklisted_user_ids'] or [])
            if user_id not in current_blacklist:
                current_blacklist.append(user_id)
                
                await self.db.execute("""
                    UPDATE notification_settings 
                    SET blacklisted_user_ids = $1, updated_at = NOW()
                    WHERE id = $2
                """, current_blacklist, settings['id'])
                return True
            return False
        except Exception as e:
            raise e
    
    async def remove_from_blacklist(self, user_id: int) -> bool:
        """Remove a user from the blacklist"""
        try:
            settings = await self.get_settings()
            if not settings:
                return False
            
            current_blacklist = list(settings['blacklisted_user_ids'] or [])
            if user_id in current_blacklist:
                current_blacklist.remove(user_id)
                
                await self.db.execute("""
                    UPDATE notification_settings 
                    SET blacklisted_user_ids = $1, updated_at = NOW()
                    WHERE id = $2
                """, current_blacklist, settings['id'])
                return True
            return False
        except Exception as e:
            raise e
    
    async def is_user_blacklisted(self, user_id: int) -> bool:
        """Check if a user is blacklisted"""
        settings = await self.get_settings()
        if not settings:
            return False
        
        blacklist = settings['blacklisted_user_ids'] or []
        return user_id in blacklist
    
    async def get_blacklisted_users(self) -> List[int]:
        """Get list of blacklisted users"""
        settings = await self.get_settings()
        if not settings:
            return []
        
        return list(settings['blacklisted_user_ids'] or [])
    
    async def update_event_types(self, event_types: Dict[str, bool]) -> None:
        """Update enabled/disabled event types"""
        settings = await self.get_settings()
        if not settings:
            # Create initial settings
            await self.db.execute("""
                INSERT INTO notification_settings (event_types_enabled, blacklisted_user_ids)
                VALUES ($1, '{}')
            """, json.dumps(event_types))
        else:
            await self.db.execute("""
                UPDATE notification_settings 
                SET event_types_enabled = $1, updated_at = NOW()
                WHERE id = $2
            """, json.dumps(event_types), settings['id'])
    
    async def is_event_type_enabled(self, event_type: str) -> bool:
        """Check if an event type is enabled for notifications"""
        settings = await self.get_settings()
        if not settings:
            return True  # Default to enabled
        
        event_types = settings['event_types_enabled'] or {}
        if isinstance(event_types, str):
            import json
            event_types = json.loads(event_types)
        return event_types.get(event_type, True)
    
    async def get_notification_channel(self) -> Optional[int]:
        """Get the configured notification channel ID"""
        settings = await self.get_settings()
        if not settings:
            return None
        
        return settings['notification_channel_id']
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        settings = await self.get_settings()
        if not settings:
            return {
                'channel_configured': False,
                'blacklisted_users': 0,
                'enabled_events': 0
            }
        
        event_types = settings['event_types_enabled'] or {}
        if isinstance(event_types, str):
            import json
            event_types = json.loads(event_types)
        enabled_count = sum(1 for enabled in event_types.values() if enabled)
        
        return {
            'channel_configured': settings['notification_channel_id'] is not None,
            'notification_channel_id': settings['notification_channel_id'],
            'blacklisted_users': len(settings['blacklisted_user_ids'] or []),
            'enabled_events': enabled_count,
            'total_event_types': len(event_types),
            'blacklist': list(settings['blacklisted_user_ids'] or []),
            'event_types': event_types
        }