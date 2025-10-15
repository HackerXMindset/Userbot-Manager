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
                COUNT(DISTINCT tga.token_id) AS token_count,
                COUNT(DISTINCT mst.target_chat_id) AS target_count,
                ARRAY_AGG(DISTINCT mst.target_chat_id) FILTER (WHERE mst.target_chat_id IS NOT NULL) AS target_chat_ids
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            LEFT JOIN monitored_source_targets mst ON mst.source_id = ms.id
            GROUP BY ms.id
            ORDER BY ms.created_at DESC
        """)

    async def get_by_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """Get all monitored sources for a specific chat"""
        return await self.db.fetch("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) AS token_count,
                COUNT(DISTINCT mst.target_chat_id) AS target_count,
                ARRAY_AGG(DISTINCT mst.target_chat_id) FILTER (WHERE mst.target_chat_id IS NOT NULL) AS target_chat_ids
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            LEFT JOIN monitored_source_targets mst ON mst.source_id = ms.id
            WHERE ms.chat_id = $1
            GROUP BY ms.id
            ORDER BY ms.created_at DESC
        """, chat_id)

    async def get_with_stats(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get a single monitored source with token count stats"""
        return await self.db.fetchrow("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) AS token_count,
                COUNT(DISTINCT mst.target_chat_id) AS target_count,
                ARRAY_AGG(DISTINCT mst.target_chat_id) FILTER (WHERE mst.target_chat_id IS NOT NULL) AS target_chat_ids
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            LEFT JOIN monitored_source_targets mst ON mst.source_id = ms.id
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

    async def update_source_fields(self, source_id: int, **fields: Any) -> Optional[Dict[str, Any]]:
        """
        Update one or more override fields on a monitored source.

        Passing None as a value clears the field.
        """
        assignments = []
        values: List[Any] = []
        param_idx = 1

        for column, value in fields.items():
            assignments.append(f"{column} = ${param_idx}")
            values.append(value)
            param_idx += 1

        if not assignments:
            logger.debug("No fields provided for update on monitored source %s", source_id)
            return await self.get_by_id(source_id)

        values.append(source_id)

        query = f"""
            UPDATE monitored_sources
            SET {', '.join(assignments)}
            WHERE id = ${param_idx}
            RETURNING *
        """
        return await self.db.fetchrow(query, *values)

    async def set_display_name(self, source_id: int, display_name: Optional[str]) -> Optional[Dict[str, Any]]:
        """Set or clear the display name override for a source."""
        return await self.update_source_fields(source_id, display_name=display_name)

    async def set_enabled(self, source_id: int, enabled: bool) -> Optional[Dict[str, Any]]:
        """Enable or disable gain alerts for the source."""
        return await self.update_source_fields(source_id, is_enabled=enabled)

    async def set_sensitivity(self, source_id: int, sensitivity_pct: Optional[float]) -> Optional[Dict[str, Any]]:
        """Set a custom gain threshold multiplier override for the source."""
        return await self.update_source_fields(source_id, sensitivity_pct=sensitivity_pct)

    async def assign_userbot(self, source_id: int, userbot_id: Optional[int]) -> Optional[Dict[str, Any]]:
        """Assign or clear the userbot responsible for this source."""
        return await self.update_source_fields(source_id, assigned_userbot_id=userbot_id)

    async def set_template_for_chat(self, chat_id: int, template_text: Optional[str]) -> None:
        """Apply a template override to all monitored source rows for the chat."""
        await self.db.execute(
            """
            UPDATE monitored_sources
            SET template_text = $1
            WHERE chat_id = $2
            """,
            template_text,
            chat_id,
        )

    async def set_management_bot_for_chat(self, chat_id: int, use_management_bot: bool) -> None:
        """Toggle management bot delivery for all records tied to the chat."""
        if use_management_bot:
            await self.db.execute(
                """
                UPDATE monitored_sources
                SET use_management_bot = $1, assigned_userbot_id = NULL
                WHERE chat_id = $2
                """,
                use_management_bot,
                chat_id,
            )
        else:
            await self.db.execute(
                """
                UPDATE monitored_sources
                SET use_management_bot = $1
                WHERE chat_id = $2
                """,
                use_management_bot,
                chat_id,
            )

    async def get_targets(self, source_id: int) -> List[Dict[str, Any]]:
        """List routing targets configured for a monitored source."""
        return await self.db.fetch("""
            SELECT
                mst.*,
                COALESCE(g.display_name, g.title, 'Chat ' || mst.target_chat_id::TEXT) AS target_label
            FROM monitored_source_targets mst
            LEFT JOIN groups g ON g.tg_chat_id = mst.target_chat_id
            WHERE mst.source_id = $1
            ORDER BY mst.target_chat_id
        """, source_id)

    async def add_target(self, source_id: int, target_chat_id: int) -> Optional[Dict[str, Any]]:
        """Attach a routing target to a monitored source."""
        return await self.db.fetchrow("""
            INSERT INTO monitored_source_targets (source_id, target_chat_id)
            VALUES ($1, $2)
            ON CONFLICT (source_id, target_chat_id) DO NOTHING
            RETURNING *
        """, source_id, target_chat_id)

    async def remove_target(self, source_id: int, target_chat_id: int) -> bool:
        """Remove a routing target from a monitored source."""
        result = await self.db.execute("""
            DELETE FROM monitored_source_targets
            WHERE source_id = $1 AND target_chat_id = $2
        """, source_id, target_chat_id)
        return result.endswith("1")

    async def list_available_userbots(self) -> List[Dict[str, Any]]:
        """Return all known userbots for assignment."""
        return await self.db.fetch("""
            SELECT
                id,
                COALESCE(display_name, username, 'Userbot ' || id::TEXT) AS label,
                status,
                last_seen,
                phone,
                session_name
            FROM bots
            WHERE kind = 'userbot'
            ORDER BY
                (status = 'active') DESC,
                last_seen DESC NULLS LAST,
                id
        """)

    async def list_known_target_chats(self) -> List[Dict[str, Any]]:
        """Return a deduplicated list of known chat IDs that can receive gain alerts."""
        return await self.db.fetch("""
            WITH combined AS (
                SELECT
                    g.tg_chat_id AS chat_id,
                    COALESCE(g.display_name, g.title, 'Group ' || g.tg_chat_id::TEXT) AS label,
                    'group' AS origin,
                    1 AS priority
                FROM groups g
                WHERE g.tg_chat_id IS NOT NULL

                UNION ALL

                SELECT
                    t.dest_chat_id AS chat_id,
                    COALESCE(g.display_name, g.title, 'Target ' || t.dest_chat_id::TEXT) AS label,
                    'target' AS origin,
                    2 AS priority
                FROM targets t
                LEFT JOIN groups g ON g.id = t.group_id
                WHERE t.dest_chat_id IS NOT NULL

                UNION ALL

                SELECT
                    ms.chat_id AS chat_id,
                    COALESCE(ms.display_name, 'Monitored ' || ms.chat_id::TEXT) AS label,
                    'monitored' AS origin,
                    3 AS priority
                FROM monitored_sources ms
            ),
            aggregated AS (
                SELECT
                    chat_id,
                    ARRAY_AGG(label ORDER BY priority, label) AS labels,
                    ARRAY_AGG(origin ORDER BY priority, origin) AS origins
                FROM combined
                GROUP BY chat_id
            )
            SELECT
                chat_id,
                labels[1] AS label,
                origins
            FROM aggregated
            ORDER BY chat_id
        """)
