"""
Monitored Source Model - Database operations for gain alert monitored sources
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MonitoredSourceModel:
    """Model for monitored_sources table operations"""

    def __init__(self, db):
        self.db = db

    async def get_all_with_stats(self) -> List[Dict[str, Any]]:
        """Get all monitored sources with token tracking stats"""
        return await self.db.fetch("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) as token_count
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            GROUP BY ms.id
            ORDER BY ms.created_at DESC
        """)

    async def get_by_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """Get all monitored sources for a specific chat"""
        return await self.db.fetch("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) as token_count
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            WHERE ms.chat_id = $1
            GROUP BY ms.id
            ORDER BY ms.created_at DESC
        """, chat_id)

    async def get_with_stats(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get a single monitored source with token count stats"""
        return await self.db.fetchrow("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) as token_count
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            WHERE ms.id = $1
            GROUP BY ms.id
        """, source_id)

    async def add_source(self, chat_id: int, chat_type: str, user_id: Optional[int], admin_id: int) -> Dict[str, Any]:
        """Add new monitored source"""
        if chat_type not in {"group", "channel", "dm"}:
            raise ValueError(f"Unsupported chat_type '{chat_type}' for monitored source")

        if chat_type == "group" and user_id is None:
            raise ValueError("Groups require a specific user_id to monitor")

        if chat_type in {"channel", "dm"} and user_id is not None:
            raise ValueError(f"{chat_type} sources must not specify user_id")

        return await self.db.fetchrow("""
            INSERT INTO monitored_sources (chat_id, chat_type, user_id, added_by_admin_id)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """, chat_id, chat_type, user_id, admin_id)

    async def remove_source(self, source_id: int) -> bool:
        """Remove monitored source and all related token_group_alerts"""
        # Get source details for cleanup
        source = await self.db.fetchrow("SELECT * FROM monitored_sources WHERE id = $1", source_id)
        if not source:
            return False

        # Delete token_group_alerts entries
        await self.db.execute("""
            DELETE FROM token_group_alerts
            WHERE chat_id = $1
            AND (original_user_id = $2 OR $2 IS NULL)
        """, source['chat_id'], source['user_id'])

        # Delete monitored source
        result = await self.db.execute("DELETE FROM monitored_sources WHERE id = $1", source_id)
        return result == "DELETE 1"

    async def get_by_id(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get monitored source by ID"""
        return await self.db.fetchrow("SELECT * FROM monitored_sources WHERE id = $1", source_id)

    async def is_monitored(self, chat_id: int, user_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Check if chat/user combination is monitored"""
        return await self.db.fetchrow("""
            SELECT * FROM monitored_sources
            WHERE chat_id = $1
            AND (
                (user_id = $2)
                OR (user_id IS NULL AND $2 IS NULL)
            )
        """, chat_id, user_id)
