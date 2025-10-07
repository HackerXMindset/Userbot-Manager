from typing import Optional, List, Dict, Any
from .base import BaseModel
import asyncpg
import json

class CuratedAlphaRuleModel(BaseModel):
    """Model for managing Curated Alpha rules"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "curated_alpha_rules"

    async def get_all_rules(self) -> List[asyncpg.Record]:
        """Get all rules"""
        query = "SELECT * FROM curated_alpha_rules ORDER BY created_at DESC"
        return await self.db.fetch(query)

    async def update_rule_chains(self, rule_id: int, allowed_chains: list):
        """Update allowed_chains for a curated alpha rule"""
        query = """
            UPDATE curated_alpha_rules
            SET allowed_chains = $1::jsonb, updated_at = NOW()
            WHERE id = $2
        """
        await self.db.execute(query, json.dumps(allowed_chains), rule_id)

class CuratedAlphaTokenStateModel(BaseModel):
    """Model for managing the state of tokens for Curated Alpha rules"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "curated_alpha_token_state"
