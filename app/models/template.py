from typing import Optional, List, Dict
from .base import BaseModel
import asyncpg

class TemplateModel(BaseModel):
    """Model for managing post templates"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "post_templates"

    async def get_all_with_assignment_counts(self, blockchain: Optional[str] = None) -> List[asyncpg.Record]:
        """Get all templates with assignment counts, optionally filtered by blockchain."""
        if blockchain:
            query = """
                SELECT
                    pt.*,
                    COUNT(tta.group_id) as assignment_count
                FROM post_templates pt
                LEFT JOIN target_template_assignments tta
                    ON pt.id = tta.template_id AND tta.blockchain = $1
                WHERE pt.blockchain = $1
                GROUP BY pt.id
                ORDER BY pt.name
            """
            return await self.db.fetch(query, blockchain.upper())

        query = """
            SELECT
                pt.*,
                COUNT(tta.group_id) as assignment_count
            FROM post_templates pt
            LEFT JOIN target_template_assignments tta ON pt.id = tta.template_id
            GROUP BY pt.id
            ORDER BY pt.name
        """
        return await self.db.fetch(query)

    async def list_by_blockchain(self, blockchain: str) -> List[asyncpg.Record]:
        query = """
            SELECT *
            FROM post_templates
            WHERE blockchain = $1
            ORDER BY name
        """
        return await self.db.fetch(query, blockchain.upper())

class TemplateAssignmentModel(BaseModel):
    """Model for managing template assignments to groups"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "target_template_assignments"

    async def get_by_group_id(self, group_id: int, blockchain: str = 'SOL') -> Optional[asyncpg.Record]:
        """Get assignment by group ID and blockchain"""
        query = """
            SELECT *
            FROM target_template_assignments
            WHERE group_id = $1 AND blockchain = $2
        """
        return await self.db.fetchrow(query, group_id, blockchain.upper())

    async def get_template_for_group(self, group_id: int, blockchain: str = 'SOL') -> Optional[asyncpg.Record]:
        """Get the full template record for a given group ID and blockchain."""
        query = """
            SELECT pt.*
            FROM post_templates pt
            JOIN target_template_assignments tta
                ON pt.id = tta.template_id
            WHERE tta.group_id = $1 AND tta.blockchain = $2
        """
        return await self.db.fetchrow(query, group_id, blockchain.upper())

    async def get_assigned_groups(self, template_id: int) -> List[asyncpg.Record]:
        """Get all groups assigned to a specific template."""
        query = """
            SELECT g.id, g.display_name, g.title, g.tg_chat_id, tta.blockchain
            FROM groups g
            JOIN target_template_assignments tta ON g.id = tta.group_id
            WHERE tta.template_id = $1
            ORDER BY g.display_name, g.title
        """
        return await self.db.fetch(query, template_id)

    async def assign(self, group_id: int, template_id: int, blockchain: str = 'SOL') -> asyncpg.Record:
        """Assign a template to a group for a specific blockchain, overwriting if exists."""
        query = """
            INSERT INTO target_template_assignments (group_id, blockchain, template_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (group_id, blockchain) DO UPDATE SET
                template_id = EXCLUDED.template_id,
                updated_at = NOW()
            RETURNING *
        """
        return await self.db.fetchrow(query, group_id, blockchain.upper(), template_id)

    async def unassign(self, group_id: int, blockchain: str = 'SOL') -> bool:
        """Unassign a template from a group for a specific blockchain."""
        query = """
            DELETE FROM target_template_assignments
            WHERE group_id = $1 AND blockchain = $2
        """
        result = await self.db.execute(query, group_id, blockchain.upper())
        return result.split()[-1] == '1'
