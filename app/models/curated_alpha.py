from typing import Optional, List, Dict, Any
from .base import BaseModel
import asyncpg

class CuratedAlphaRuleModel(BaseModel):
    """Model for managing Curated Alpha rules"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "curated_alpha_rules"

    async def get_all_rules(self) -> List[asyncpg.Record]:
        """Get all rules"""
        query = "SELECT * FROM curated_alpha_rules ORDER BY created_at DESC"
        return await self.db.fetch(query)

class CuratedAlphaTokenStateModel(BaseModel):
    """Model for managing the state of tokens for Curated Alpha rules"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "curated_alpha_token_state"
