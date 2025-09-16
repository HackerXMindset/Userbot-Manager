from typing import Optional, List, Dict
from .base import BaseModel
import asyncpg

class TemplateModel(BaseModel):
    """Model for managing post templates"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "post_templates"

    async def get_all_with_assignment_counts(self) -> List[asyncpg.Record]:
        """Get all templates with a count of how many groups they are assigned to."""
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

class TemplateAssignmentModel(BaseModel):
    """Model for managing template assignments to groups"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "target_template_assignments"

    async def get_by_group_id(self, group_id: int) -> Optional[asyncpg.Record]:
        """Get assignment by group ID"""
        query = "SELECT * FROM target_template_assignments WHERE group_id = $1"
        return await self.db.fetchrow(query, group_id)

    async def get_template_for_group(self, group_id: int) -> Optional[asyncpg.Record]:
        """Get the full template record for a given group ID."""
        query = """
            SELECT pt.*
            FROM post_templates pt
            JOIN target_template_assignments tta ON pt.id = tta.template_id
            WHERE tta.group_id = $1
        """
        return await self.db.fetchrow(query, group_id)

    async def get_assigned_groups(self, template_id: int) -> List[asyncpg.Record]:
        """Get all groups assigned to a specific template."""
        query = """
            SELECT g.id, g.display_name, g.title, g.tg_chat_id
            FROM groups g
            JOIN target_template_assignments tta ON g.id = tta.group_id
            WHERE tta.template_id = $1
            ORDER BY g.display_name, g.title
        """
        return await self.db.fetch(query, template_id)

    async def assign(self, group_id: int, template_id: int) -> asyncpg.Record:
        """Assign a template to a group, overwriting if an assignment exists."""
        query = """
            INSERT INTO target_template_assignments (group_id, template_id)
            VALUES ($1, $2)
            ON CONFLICT (group_id) DO UPDATE SET
                template_id = EXCLUDED.template_id,
                updated_at = NOW()
            RETURNING *
        """
        return await self.db.fetchrow(query, group_id, template_id)

    async def unassign(self, group_id: int) -> bool:
        """Unassign a template from a group."""
        query = "DELETE FROM target_template_assignments WHERE group_id = $1"
        result = await self.db.execute(query, group_id)
        return result.split()[-1] == '1'
