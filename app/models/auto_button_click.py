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
        """Get rule for a specific chat and bot"""
        query = "SELECT * FROM auto_button_click_rules WHERE target_chat_id = $1 AND bot_id = $2 AND enabled = true LIMIT 1"
        return await self.db.fetchrow(query, target_chat_id, bot_id)
