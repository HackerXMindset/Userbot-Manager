"""
Chart Request Group Model - Database operations for chart_request_groups table
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class ChartRequestGroupModel:
    """Model for chart_request_groups table operations"""

    def __init__(self, db):
        self.db = db

    async def list_all(self) -> List[Dict[str, Any]]:
        """Return all chart request groups"""
        return await self.db.fetch("""
            SELECT id, chat_id, label, added_at
            FROM chart_request_groups
            ORDER BY added_at DESC
        """)

    async def add_group(self, chat_id: int, label: Optional[str] = None) -> Dict[str, Any]:
        """
        Add new chart request group.

        Args:
            chat_id: Telegram chat ID (must be negative for groups)
            label: Optional descriptive label for the group

        Returns:
            Newly created chart request group record

        Raises:
            Exception if chat_id is positive or already exists
        """
        return await self.db.fetchrow("""
            INSERT INTO chart_request_groups (chat_id, label)
            VALUES ($1, $2)
            RETURNING *
        """, chat_id, label)

    async def remove_group(self, chat_id: int) -> bool:
        """
        Remove chart request group.

        Args:
            chat_id: Telegram chat ID to remove

        Returns:
            True if group was removed, False if not found
        """
        result = await self.db.execute("""
            DELETE FROM chart_request_groups
            WHERE chat_id = $1
        """, chat_id)
        return result == "DELETE 1"

    async def get_random_group(self) -> Optional[int]:
        """
        Pick random group chat_id.

        Returns:
            Random chat_id or None if no groups configured
        """
        result = await self.db.fetchrow("""
            SELECT chat_id
            FROM chart_request_groups
            ORDER BY RANDOM()
            LIMIT 1
        """)

        if result:
            return result['chat_id']
        return None

    async def get_by_chat_id(self, chat_id: int) -> Optional[Dict[str, Any]]:
        """
        Get chart request group by chat_id.

        Args:
            chat_id: Telegram chat ID

        Returns:
            Chart request group record or None if not found
        """
        return await self.db.fetchrow("""
            SELECT id, chat_id, label, added_at
            FROM chart_request_groups
            WHERE chat_id = $1
        """, chat_id)

    async def update_label(self, chat_id: int, label: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Update label for a chart request group.

        Args:
            chat_id: Telegram chat ID
            label: New label (None to clear)

        Returns:
            Updated chart request group record or None if not found
        """
        return await self.db.fetchrow("""
            UPDATE chart_request_groups
            SET label = $1
            WHERE chat_id = $2
            RETURNING *
        """, label, chat_id)

    async def count_groups(self) -> int:
        """
        Get total count of configured chart request groups.

        Returns:
            Number of chart request groups
        """
        result = await self.db.fetchval("""
            SELECT COUNT(*)
            FROM chart_request_groups
        """)
        return result or 0
