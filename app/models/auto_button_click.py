import json
from typing import Optional, List
from .base import BaseModel
import asyncpg

class AutoButtonClickRuleModel(BaseModel):
    """Model for managing auto button click rules"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "auto_button_click_rules"
    
    async def get_all_rules(self) -> List[asyncpg.Record]:
        """Get all rules"""
        query = "SELECT * FROM auto_button_click_rules ORDER BY created_at DESC"
        return await self.db.fetch(query)

    async def get_rule_for_chat_and_bot(self, target_chat_id: int, bot_id: int) -> Optional[asyncpg.Record]:
        """Get rule for a specific chat and bot (static rules only)"""
        query = "SELECT * FROM auto_button_click_rules WHERE target_chat_id = $1 AND bot_id = $2 AND enabled = true AND rule_type = 'static' LIMIT 1"
        return await self.db.fetchrow(query, target_chat_id, bot_id)

    async def get_dynamic_rules_for_chat_and_user(self, target_chat_id: int, user_id: int) -> List[asyncpg.Record]:
        """Get all enabled dynamic rules for specific chat and user"""
        query = """
            SELECT * FROM auto_button_click_rules
            WHERE rule_type = 'dynamic'
            AND target_chat_id = $1
            AND user_id = $2
            AND enabled = true
        """
        return await self.db.fetch(query, target_chat_id, user_id)

    async def create_dynamic_rule(self, data: dict) -> asyncpg.Record:
        """Create a dynamic click rule"""
        query = """
            INSERT INTO auto_button_click_rules
            (rule_type, target_chat_id, user_id, button_texts, clicking_userbot_ids, enabled)
            VALUES ('dynamic', $1, $2, $3, $4, true)
            RETURNING *
        """
        return await self.db.fetchrow(
            query,
            data['target_chat_id'],
            data['user_id'],
            json.dumps(data['button_texts']),  # JSONB array
            json.dumps(data['clicking_userbot_ids']) # JSONB array of userbot IDs
        )
