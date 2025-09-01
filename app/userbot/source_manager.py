"""
Source Manager - Handles source chat management and user permissions
"""

import logging
from typing import Dict, Any, List, Optional

from app.db import db
from app.models.source_chat import SourceChatModel

logger = logging.getLogger(__name__)


class SourceManager:
    """Manages source chats and user permissions"""
    
    def __init__(self, userbot_id: int):
        self.userbot_id = userbot_id
        self.source_model = SourceChatModel(db)
    
    async def get_sources_for_groups(self, group_ids: List[int]) -> List[Dict[str, Any]]:
        """Get all source chats for given groups using routing rules"""
        try:
            if not group_ids:
                return []
            
            # Get all sources that route to any of the provided groups
            placeholders = ','.join(f'${i+1}' for i in range(len(group_ids)))
            query = f"""
                SELECT DISTINCT sc.*, COUNT(rr.id) as route_count
                FROM source_chats sc
                JOIN routing_rules rr ON rr.source_chat_id = sc.id
                WHERE rr.target_group_id IN ({placeholders}) 
                AND sc.enabled = true AND rr.enabled = true
                GROUP BY sc.id
                ORDER BY sc.created_at DESC
            """
            
            sources = await db.fetch(query, *group_ids)
            return [dict(source) for source in sources] if sources else []
        except Exception as e:
            logger.error(f"Error getting sources for groups: {e}")
            return []
    
    async def get_source_chat_ids(self, group_ids: List[int]) -> List[int]:
        """Get list of source chat IDs for given groups"""
        try:
            sources = await self.get_sources_for_groups(group_ids)
            return [s['source_chat_id'] for s in sources]
        except Exception as e:
            logger.error(f"Error getting source chat IDs: {e}")
            return []
    
    async def is_user_allowed(self, source_chat_id: int, user_id: int) -> bool:
        """Check if user is allowed to trigger forwards from source chat"""
        try:
            return await self.source_model.is_user_allowed(source_chat_id, user_id)
        except Exception as e:
            logger.error(f"Error checking user permissions: {e}")
            return False
    
    async def get_source_by_chat_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """Get source configuration by chat ID"""
        try:
            source = await self.source_model.get_source_by_chat_id(chat_id)
            return dict(source) if source else None
        except Exception as e:
            logger.error(f"Error getting source by chat ID: {e}")
            return None
    
    async def get_sources_with_routing(self, group_ids: List[int] = None) -> List[Dict[str, Any]]:
        """Get all sources with their routing information"""
        try:
            if group_ids:
                # Get sources that route to specific groups
                placeholders = ','.join(f'${i+1}' for i in range(len(group_ids)))
                query = f"""
                    SELECT sc.*, rr.target_group_id, g.title as target_group_title
                    FROM source_chats sc
                    JOIN routing_rules rr ON rr.source_chat_id = sc.id
                    JOIN groups g ON g.id = rr.target_group_id
                    WHERE rr.target_group_id IN ({placeholders})
                    AND sc.enabled = true AND rr.enabled = true
                    ORDER BY sc.source_type, sc.created_at DESC
                """
                results = await db.fetch(query, *group_ids)
            else:
                # Get all sources with all their routing rules
                query = """
                    SELECT sc.*, rr.target_group_id, g.title as target_group_title
                    FROM source_chats sc
                    LEFT JOIN routing_rules rr ON rr.source_chat_id = sc.id AND rr.enabled = true
                    LEFT JOIN groups g ON g.id = rr.target_group_id
                    WHERE sc.enabled = true
                    ORDER BY sc.source_type, sc.created_at DESC
                """
                results = await db.fetch(query)
            
            # Group results by source to handle multiple routing rules per source
            sources_dict = {}
            for row in results:
                source_id = row['id']
                if source_id not in sources_dict:
                    sources_dict[source_id] = {
                        'id': row['id'],
                        'source_chat_id': row['source_chat_id'],
                        'source_type': row['source_type'],
                        'name': row['name'],
                        'title': row['title'],
                        'enabled': row['enabled'],
                        'created_at': row['created_at'],
                        'target_groups': []
                    }
                
                if row['target_group_id']:
                    sources_dict[source_id]['target_groups'].append({
                        'group_id': row['target_group_id'],
                        'group_title': row['target_group_title']
                    })
            
            return list(sources_dict.values())
            
        except Exception as e:
            logger.error(f"Error getting sources with routing: {e}")
            return []
    
    async def get_target_groups_for_source(self, source_chat_id: int) -> List[Dict[str, Any]]:
        """Get all target groups that should receive tokens from this source"""
        try:
            query = """
                SELECT g.id, g.tg_chat_id, g.title
                FROM routing_rules rr
                JOIN groups g ON g.id = rr.target_group_id
                JOIN source_chats sc ON sc.id = rr.source_chat_id
                WHERE sc.source_chat_id = $1 
                AND sc.enabled = true AND rr.enabled = true AND g.enabled = true
            """
            results = await db.fetch(query, source_chat_id)
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Error getting target groups for source: {e}")
            return []
    
    async def add_source_chat(self, group_id: int, source_chat_id: int, 
                             source_type: str = 'group') -> Optional[Dict[str, Any]]:
        """Add a new source chat"""
        try:
            source = await self.source_model.create({
                'group_id': group_id,
                'source_chat_id': source_chat_id,
                'source_type': source_type,
                'enabled': True
            })
            return dict(source) if source else None
        except Exception as e:
            logger.error(f"Error adding source chat: {e}")
            return None
    
    async def remove_source_chat(self, group_id: int, source_chat_id: int) -> bool:
        """Remove a source chat"""
        try:
            # Find and delete the source
            await db.execute("""
                DELETE FROM source_chats 
                WHERE group_id = $1 AND source_chat_id = $2
            """, group_id, source_chat_id)
            
            logger.info(f"Removed source chat {source_chat_id} from group {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error removing source chat: {e}")
            return False
    
    async def toggle_source_enabled(self, source_id: int) -> bool:
        """Toggle source chat enabled status"""
        try:
            result = await db.fetchval("""
                UPDATE source_chats 
                SET enabled = NOT enabled 
                WHERE id = $1 
                RETURNING enabled
            """, source_id)
            
            return result if result is not None else False
            
        except Exception as e:
            logger.error(f"Error toggling source enabled: {e}")
            return False
    
    async def add_allowed_user(self, source_id: int, user_id: int, 
                              username: str = None) -> bool:
        """Add allowed user to source chat"""
        try:
            await db.execute("""
                INSERT INTO source_allowed_users (source_id, user_id, username)
                VALUES ($1, $2, $3)
                ON CONFLICT (source_id, user_id) DO UPDATE SET 
                    username = EXCLUDED.username,
                    updated_at = NOW()
            """, source_id, user_id, username)
            
            logger.info(f"Added allowed user {user_id} to source {source_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error adding allowed user: {e}")
            return False
    
    async def remove_allowed_user(self, source_id: int, user_id: int) -> bool:
        """Remove allowed user from source chat"""
        try:
            result = await db.execute("""
                DELETE FROM source_allowed_users 
                WHERE source_id = $1 AND user_id = $2
            """, source_id, user_id)
            
            # Check if any rows were affected
            deleted_count = int(result.split()[-1]) if result else 0
            
            if deleted_count > 0:
                logger.info(f"Removed allowed user {user_id} from source {source_id}")
                return True
            else:
                logger.warning(f"User {user_id} not found in source {source_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error removing allowed user: {e}")
            return False
    
    async def get_allowed_users(self, source_id: int) -> List[Dict[str, Any]]:
        """Get all allowed users for a source chat"""
        try:
            users = await db.fetch("""
                SELECT * FROM source_allowed_users 
                WHERE source_id = $1
                ORDER BY username, user_id
            """, source_id)
            
            return [dict(user) for user in users]
            
        except Exception as e:
            logger.error(f"Error getting allowed users: {e}")
            return []
    
    async def get_source_stats(self) -> Dict[str, Any]:
        """Get source management statistics"""
        try:
            stats = await db.fetchrow("""
                SELECT 
                    COUNT(DISTINCT sc.id) as total_sources,
                    COUNT(DISTINCT sc.id) FILTER (WHERE sc.enabled = true) as enabled_sources,
                    COUNT(DISTINCT sc.group_id) as groups_with_sources,
                    COUNT(DISTINCT sau.user_id) as total_allowed_users
                FROM source_chats sc
                LEFT JOIN source_allowed_users sau ON sau.source_id = sc.id
            """)
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting source stats: {e}")
            return {}
    
    async def validate_source_permissions(self, event) -> Dict[str, Any]:
        """Validate if a source event should be processed"""
        try:
            chat_id = event.chat_id
            user_id = event.sender_id
            
            # Get source configuration
            source = await self.get_source_by_chat_id(chat_id)
            if not source:
                return {
                    'allowed': False,
                    'reason': 'Source chat not configured'
                }
            
            if not source['enabled']:
                return {
                    'allowed': False,
                    'reason': 'Source chat disabled'
                }
            
            # Check user permissions
            user_allowed = await self.is_user_allowed(chat_id, user_id)
            if not user_allowed:
                return {
                    'allowed': False,
                    'reason': 'User not allowed in this source'
                }
            
            return {
                'allowed': True,
                'source': source,
                'reason': 'Permission granted'
            }
            
        except Exception as e:
            logger.error(f"Error validating source permissions: {e}")
            return {
                'allowed': False,
                'reason': f'Validation error: {str(e)}'
            }
    
    async def cleanup_inactive_sources(self, days_inactive: int = 30) -> int:
        """Clean up sources that haven't been used recently"""
        try:
            # This would need implementation based on usage tracking
            # For now, just return 0
            logger.info("Source cleanup not implemented yet")
            return 0
            
        except Exception as e:
            logger.error(f"Error cleaning up inactive sources: {e}")
            return 0