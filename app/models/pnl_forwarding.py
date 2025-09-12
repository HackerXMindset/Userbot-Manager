from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg
import logging
import traceback

logger = logging.getLogger(__name__)

# Set detailed logging for PNL model operations
logging.getLogger(__name__).setLevel(logging.DEBUG)

class PnlForwardingRuleModel(BaseModel):
    """Model for managing PNL forwarding rules with comprehensive debugging"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "pnl_forwarding_rules"
        logger.debug("PnlForwardingRuleModel initialized")

    async def get_by_id(self, record_id: int) -> Optional[asyncpg.Record]:
        """Get rule by ID with group title"""
        query = """
            SELECT pfr.*, 
                   COALESCE(g.title, g.display_name, 'Unknown Group') as source_group_title
            FROM pnl_forwarding_rules pfr
            LEFT JOIN groups g ON g.id = pfr.source_group_id
            WHERE pfr.id = $1
        """
        return await self.db.fetchrow(query, record_id)
    
    async def get_by_source_group(self, source_group_id: int) -> List[asyncpg.Record]:
        """Get all rules for a source group"""
        query = """
            SELECT pfr.*, g.title as source_group_title
            FROM pnl_forwarding_rules pfr
            JOIN groups g ON g.id = pfr.source_group_id
            WHERE pfr.source_group_id = $1
            ORDER BY pfr.created_at DESC
        """
        return await self.db.fetch(query, source_group_id)
    
    async def get_enabled_rules_for_group(self, source_group_id: int) -> List[asyncpg.Record]:
        """Get enabled rules for a source group with debugging"""
        try:
            logger.debug(f"Getting enabled PNL rules for group: {source_group_id}")
            query = """
                SELECT * FROM pnl_forwarding_rules
                WHERE source_group_id = $1 AND enabled = true
                ORDER BY created_at DESC
            """
            result = await self.db.fetch(query, source_group_id)
            logger.debug(f"Found {len(result)} enabled PNL rules for group {source_group_id}")
            
            for rule in result:
                logger.debug(f"Rule {rule['id']}: userbot={rule['forwarding_userbot_id']}, "
                           f"destination={rule['destination_channel_id']}, "
                           f"monitored_users={rule['allowed_pnl_command_user_ids']}, "
                           f"reply_users={rule['allowed_reply_user_ids']}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get enabled rules for group {source_group_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def create_rule(self, source_group_id: int, destination_channel_id: int, 
                         allowed_pnl_command_user_ids: List[int], allowed_reply_user_ids: List[int], 
                         forwarding_userbot_id: int) -> asyncpg.Record:
        """Create a new PNL forwarding rule with debugging"""
        try:
            logger.info(f"Creating PNL rule: source_group={source_group_id}, "
                       f"destination={destination_channel_id}, "
                       f"monitored_users={allowed_pnl_command_user_ids}, "
                       f"reply_users={allowed_reply_user_ids}, "
                       f"userbot={forwarding_userbot_id}")
            
            data = {
                'source_group_id': source_group_id,
                'destination_channel_id': destination_channel_id,
                'allowed_pnl_command_user_ids': allowed_pnl_command_user_ids,
                'allowed_reply_user_ids': allowed_reply_user_ids,
                'forwarding_userbot_id': forwarding_userbot_id
            }
            
            logger.debug(f"Rule data: {data}")
            result = await self.create(data)
            logger.info(f"Successfully created PNL rule with ID: {result['id']}")
            return result
            
        except Exception as e:
            logger.error(f"Failed to create PNL rule: {str(e)}")
            logger.error(f"Parameters: source_group={source_group_id}, destination={destination_channel_id}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
    
    async def toggle_enabled(self, rule_id: int) -> bool:
        """Toggle rule enabled status"""
        query = """
            UPDATE pnl_forwarding_rules 
            SET enabled = NOT enabled, updated_at = NOW()
            WHERE id = $1 
            RETURNING enabled
        """
        result = await self.db.fetchval(query, rule_id)
        return result
    
    async def update_allowed_users(self, rule_id: int, allowed_user_ids: List[int]) -> Optional[asyncpg.Record]:
        """Update allowed user IDs for a rule"""
        data = {'allowed_user_ids': allowed_user_ids}
        return await self.update(rule_id, data)
    
    async def get_all_with_details(self) -> List[asyncpg.Record]:
        """Get all rules with group and channel details"""
        query = """
            SELECT pfr.*, 
                   g.title as source_group_title,
                   g.tg_chat_id as source_group_chat_id
            FROM pnl_forwarding_rules pfr
            JOIN groups g ON g.id = pfr.source_group_id
            ORDER BY pfr.enabled DESC, pfr.created_at DESC
        """
        return await self.db.fetch(query)