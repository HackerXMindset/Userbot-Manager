from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg

class SourceChatModel(BaseModel):
    """Model for managing source chats"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "source_chats"
    
    async def get_all_sources(self) -> List[asyncpg.Record]:
        """Get all source chats globally"""
        query = """
            SELECT sc.*, COUNT(scu.id) as user_count,
                   COUNT(rr.id) as route_count,
                   COALESCE(g.display_name, g.title) as group_display_name
            FROM source_chats sc
            LEFT JOIN source_chat_users scu ON scu.source_chat_id = sc.id
            LEFT JOIN routing_rules rr ON rr.source_chat_id = sc.id AND rr.enabled = true
            LEFT JOIN groups g ON g.tg_chat_id = sc.source_chat_id
            GROUP BY sc.id, sc.display_name, g.display_name, g.title
            ORDER BY sc.created_at DESC
        """
        return await self.db.fetch(query)
    
    async def get_by_group(self, group_id: int) -> List[asyncpg.Record]:
        """Get all source chats routed to a specific group"""
        query = """
            SELECT sc.*, COUNT(scu.id) as user_count
            FROM source_chats sc
            LEFT JOIN source_chat_users scu ON scu.source_chat_id = sc.id
            LEFT JOIN routing_rules rr ON rr.source_chat_id = sc.id
            WHERE rr.target_group_id = $1 AND rr.enabled = true
            GROUP BY sc.id
            ORDER BY sc.created_at DESC
        """
        return await self.db.fetch(query, group_id)
    
    async def add_source(self, source_chat_id: int, source_type: str, 
                        name: str = None, title: str = None) -> asyncpg.Record:
        """Add a new global source chat"""
        query = """
            INSERT INTO source_chats (source_chat_id, source_type, name, title)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_chat_id) DO UPDATE SET
                source_type = $2, name = $3, title = $4, enabled = true
            RETURNING *
        """
        return await self.db.fetchrow(query, source_chat_id, source_type, name, title)
    
    async def add_routing_rule(self, source_id: int, target_group_id: int) -> asyncpg.Record:
        """Add a routing rule from source to target group"""
        query = """
            INSERT INTO routing_rules (source_chat_id, target_group_id)
            VALUES ($1, $2)
            ON CONFLICT (source_chat_id, target_group_id) DO UPDATE SET
                enabled = true
            RETURNING *
        """
        return await self.db.fetchrow(query, source_id, target_group_id)
    
    async def get_routing_rules(self, source_id: int) -> List[asyncpg.Record]:
        """Get all routing rules for a source"""
        query = """
            SELECT rr.*, COALESCE(g.display_name, g.title) as group_title, g.tg_chat_id
            FROM routing_rules rr
            JOIN groups g ON g.id = rr.target_group_id
            WHERE rr.source_chat_id = $1
            ORDER BY rr.enabled DESC, COALESCE(g.display_name, g.title)
        """
        return await self.db.fetch(query, source_id)
    
    async def remove_routing_rule(self, source_id: int, target_group_id: int) -> bool:
        """Remove a routing rule"""
        query = "DELETE FROM routing_rules WHERE source_chat_id = $1 AND target_group_id = $2"
        result = await self.db.execute(query, source_id, target_group_id)
        return result.split()[-1] == '1'
    
    async def toggle_enabled(self, source_id: int) -> bool:
        """Toggle source chat enabled status"""
        query = """
            UPDATE source_chats 
            SET enabled = NOT enabled 
            WHERE id = $1 
            RETURNING enabled
        """
        return await self.db.fetchval(query, source_id)
    
    async def remove_source(self, source_id: int) -> bool:
        """Remove a source chat"""
        query = "DELETE FROM source_chats WHERE id = $1"
        result = await self.db.execute(query, source_id)
        return result.split()[-1] == '1'
    
    async def get_sources_for_userbot(self, group_ids: List[int]) -> List[asyncpg.Record]:
        """Get enabled source chats for userbot monitoring"""
        if not group_ids:
            return []
        
        placeholders = ','.join(f'${i+1}' for i in range(len(group_ids)))
        query = f"""
            SELECT DISTINCT sc.source_chat_id, sc.source_type, sc.title, sc.group_id
            FROM source_chats sc
            WHERE sc.enabled = true AND sc.group_id IN ({placeholders})
        """
        return await self.db.fetch(query, *group_ids)
    
    async def add_user_to_source(self, source_id: int, user_id: int, 
                               username: str = None, first_name: str = None) -> asyncpg.Record:
        """Add user to source chat user filter"""
        query = """
            INSERT INTO source_chat_users (source_chat_id, user_id, username, first_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_chat_id, user_id) DO UPDATE SET
                username = $3, first_name = $4
            RETURNING *
        """
        return await self.db.fetchrow(query, source_id, user_id, username, first_name)
    
    async def remove_user_from_source(self, source_id: int, user_id: int) -> bool:
        """Remove user from source chat filter"""
        query = "DELETE FROM source_chat_users WHERE source_chat_id = $1 AND user_id = $2"
        result = await self.db.execute(query, source_id, user_id)
        return result.split()[-1] == '1'
    
    async def get_source_users(self, source_id: int) -> List[asyncpg.Record]:
        """Get all users for a source chat"""
        query = """
            SELECT * FROM source_chat_users 
            WHERE source_chat_id = $1 
            ORDER BY created_at DESC
        """
        return await self.db.fetch(query, source_id)
    
    async def is_user_allowed(self, source_chat_id: int, user_id: int) -> bool:
        """Check if user is allowed to trigger forwards from this source"""
        # Get the source type first
        source_query = "SELECT source_type FROM source_chats WHERE source_chat_id = $1"
        source_type = await self.db.fetchval(source_query, source_chat_id)
        
        if not source_type:
            return False
        
        # Channels allow all users
        if source_type == 'channel':
            return True
        
        # DMs: user is allowed if the source_chat_id matches their user_id
        # (DM sources have source_chat_id = user_id of the person in the DM)
        if source_type == 'dm':
            return source_chat_id == user_id
        
        # Groups: only allow specific users from source_chat_users table
        query = """
            SELECT EXISTS(
                SELECT 1 FROM source_chat_users scu
                JOIN source_chats sc ON sc.id = scu.source_chat_id
                WHERE sc.source_chat_id = $1 AND scu.user_id = $2
            )
        """
        return await self.db.fetchval(query, source_chat_id, user_id)
    
    async def get_source_by_chat_id(self, source_chat_id: int) -> Optional[asyncpg.Record]:
        """Get source chat by chat ID"""
        query = "SELECT * FROM source_chats WHERE source_chat_id = $1 AND enabled = true"
        return await self.db.fetchrow(query, source_chat_id)