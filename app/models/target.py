from typing import List, Optional

import asyncpg

from .base import BaseModel

class TargetModel(BaseModel):
    """Model for managing target records"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "targets"

    async def get_by_group_id(self, group_id: int) -> List[asyncpg.Record]:
        """Get all targets for a group"""
        query = "SELECT * FROM targets WHERE group_id = $1 ORDER BY id"
        return await self.db.fetch(query, group_id)

    async def get_by_dest_chat_id(self, dest_chat_id: int) -> Optional[asyncpg.Record]:
        """Get target by destination chat ID"""
        query = "SELECT * FROM targets WHERE dest_chat_id = $1"
        return await self.db.fetchrow(query, dest_chat_id)

    async def get_targets_with_group_info(self) -> List[asyncpg.Record]:
        """Get targets with group information"""
        query = """
            SELECT t.*, g.display_name as group_display_name, g.title as group_title, g.tg_chat_id as group_tg_chat_id
            FROM targets t
            LEFT JOIN groups g ON g.id = t.group_id
            ORDER BY g.display_name, t.dest_chat_id
        """
        return await self.db.fetch(query)

    async def get_targets_for_source_group(self, source_group_id: int) -> List[asyncpg.Record]:
        """Get targets for a source group"""
        query = """
            SELECT * FROM targets
            WHERE group_id = $1
            ORDER BY id
        """
        return await self.db.fetch(query, source_group_id)

    async def create_target(self, group_id: int, dest_chat_id: int, **kwargs) -> asyncpg.Record:
        """Create a new target"""
        data = {'group_id': group_id, 'dest_chat_id': dest_chat_id}
        for key, value in kwargs.items():
            data[key] = value
        return await self.create(data)
