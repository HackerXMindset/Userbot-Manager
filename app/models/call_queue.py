import logging
from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg

logger = logging.getLogger(__name__)

class CallQueueModel(BaseModel):
    """Model for managing call queue jobs"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "call_queue"

    async def add_job(self, token_address: str, source_message_id: int,
                     source_chat_id: int, target_chat_id: int,
                     forwarding_userbot_id: int, routing_rule_id: int = None,
                     curated_alpha_rule_id: int = None, target_group_id: int = None,
                     source_info: str = None, additional_info: str = None,
                     priority: int = 0, source_user_id: int = None) -> asyncpg.Record:
        """Add a new call job to the queue, with fallback for older schema."""
        
        if not routing_rule_id and not curated_alpha_rule_id:
            raise ValueError("Either routing_rule_id or curated_alpha_rule_id must be provided.")

        try:
            # Build the query dynamically for the LATEST schema
            cols = [
                "token_address", "source_message_id", "source_chat_id", "target_chat_id",
                "forwarding_userbot_id", "priority"
            ]
            vals = [
                token_address, source_message_id, source_chat_id, target_chat_id,
                forwarding_userbot_id, priority
            ]

            if routing_rule_id:
                cols.append("routing_rule_id")
                vals.append(routing_rule_id)
            if curated_alpha_rule_id:
                cols.append("curated_alpha_rule_id")
                vals.append(curated_alpha_rule_id)
            if target_group_id:
                cols.append("target_group_id")
                vals.append(target_group_id)
            if source_info:
                cols.append("source_info")
                vals.append(source_info)
            if additional_info:
                cols.append("additional_info")
                vals.append(additional_info)
            if source_user_id:
                cols.append("source_user_id")
                vals.append(source_user_id)

            placeholders = ", ".join([f"${i+1}" for i in range(len(vals))])
            query = f"""
                INSERT INTO call_queue ({", ".join(cols)})
                VALUES ({placeholders})
                RETURNING *
            """
            return await self.db.fetchrow(query, *vals)

        except asyncpg.exceptions.UndefinedColumnError:
            logger.warning("Call queue schema appears to be outdated. Forcing fallback query for curated alpha calls.")
            attempts = []

            attempts.append((
                """
                    INSERT INTO call_queue (
                        token_address,
                        source_chat_id,
                        target_chat_id,
                        forwarding_userbot_id,
                        priority,
                        curated_alpha_rule_id,
                        target_group_id,
                        additional_info,
                        source_info,
                        source_user_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    ON CONFLICT DO NOTHING
                    RETURNING *
                """,
                [
                    token_address,
                    source_chat_id,
                    target_chat_id,
                    forwarding_userbot_id,
                    priority,
                    curated_alpha_rule_id,
                    target_group_id,
                    additional_info,
                    source_info,
                    source_user_id,
                ],
            ))

            attempts.append((
                """
                    INSERT INTO call_queue (
                        token_address,
                        target_chat_id,
                        forwarding_userbot_id,
                        priority,
                        curated_alpha_rule_id,
                        target_group_id,
                        additional_info,
                        source_info,
                        source_user_id
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT DO NOTHING
                    RETURNING *
                """,
                [
                    token_address,
                    target_chat_id,
                    forwarding_userbot_id,
                    priority,
                    curated_alpha_rule_id,
                    target_group_id,
                    additional_info,
                    source_info,
                    source_user_id,
                ],
            ))

            attempts.append((
                """
                    INSERT INTO call_queue (
                        token_address,
                        target_chat_id,
                        forwarding_userbot_id,
                        priority,
                        curated_alpha_rule_id,
                        target_group_id,
                        additional_info,
                        source_info
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT DO NOTHING
                    RETURNING *
                """,
                [
                    token_address,
                    target_chat_id,
                    forwarding_userbot_id,
                    priority,
                    curated_alpha_rule_id,
                    target_group_id,
                    additional_info,
                    source_info,
                ],
            ))

            for query, params in attempts:
                try:
                    return await self.db.fetchrow(query, *params)
                except asyncpg.exceptions.UndefinedColumnError:
                    continue
                except Exception as attempt_error:
                    logger.debug(f"Fallback insert attempt failed: {attempt_error}")

            logger.error("CRITICAL: All fallback call_queue inserts failed due to missing columns.")
            return None

    async def get_pending_jobs(self, limit: int = 10, userbot_id: int = None) -> List[asyncpg.Record]:
        """Get pending jobs from the queue, optionally filtered by userbot"""
        if userbot_id:
            query = """
                SELECT cq.*, rr.id as routing_rule_id, g.tg_chat_id as target_chat_id,
                       COALESCE(g.display_name, g.title) as target_title
                FROM call_queue cq
                JOIN routing_rules rr ON rr.id = cq.routing_rule_id
                JOIN groups g ON g.id = cq.target_group_id
                WHERE cq.status = 'pending' AND cq.forwarding_userbot_id = $1
                ORDER BY cq.priority DESC, cq.created_at ASC
                LIMIT $2
            """
            return await self.db.fetch(query, userbot_id, limit)
        else:
            query = """
                SELECT 
                    cq.*,
                    rr.id as routing_rule_id,
                    g.tg_chat_id as target_chat_id_from_group, -- Renamed to avoid conflict
                    COALESCE(g.display_name, g.title) as target_title,
                    b.session_name as forwarding_userbot_name
                FROM call_queue cq
                LEFT JOIN routing_rules rr ON rr.id = cq.routing_rule_id
                LEFT JOIN groups g ON g.id = cq.target_group_id
                LEFT JOIN bots b ON b.id = cq.forwarding_userbot_id
                WHERE cq.status = 'pending'
                ORDER BY cq.priority DESC, cq.created_at ASC
                LIMIT $1
            """
            return await self.db.fetch(query, limit)

    async def mark_processing(self, job_id: int) -> bool:
        """Mark a job as being processed"""
        query = "UPDATE call_queue SET status = 'processing' WHERE id = $1"
        result = await self.db.execute(query, job_id)
        return result.split()[-1] == '1'

    async def mark_completed(self, job_id: int) -> bool:
        """Mark a job as completed"""
        query = """
            UPDATE call_queue
            SET status = 'completed', processed_at = NOW()
            WHERE id = $1
        """
        result = await self.db.execute(query, job_id)
        return result.split()[-1] == '1'

    async def mark_failed(self, job_id: int, error_message: str = None) -> bool:
        """Mark a job as failed with optional error message"""
        query = """
            UPDATE call_queue
            SET status = 'failed', processed_at = NOW(), error_message = $2
            WHERE id = $1
        """
        result = await self.db.execute(query, job_id, error_message)
        return result.split()[-1] == '1'

    async def get_job_stats(self) -> Dict[str, int]:
        """Get statistics for the job queue"""
        query = """
            SELECT status, COUNT(*) as count
            FROM call_queue
            WHERE created_at > NOW() - INTERVAL '24 hours'
            GROUP BY status
        """
        results = await self.db.fetch(query)
        stats = {row['status']: row['count'] for row in results}
        return {
            'pending': stats.get('pending', 0),
            'processing': stats.get('processing', 0),
            'completed': stats.get('completed', 0),
            'failed': stats.get('failed', 0),
            'total': sum(stats.values())
        }

    async def cleanup_old_jobs(self, days_old: int = 7) -> int:
        """Clean up old completed/failed jobs"""
        query = """
            DELETE FROM call_queue
            WHERE status IN ('completed', 'failed')
            AND processed_at < NOW() - INTERVAL '%s days'
        """ % days_old
        result = await self.db.execute(query)
        return int(result.split()[-1])

    async def get_jobs_for_userbot(self, userbot_id: int, status: str = None,
                                  limit: int = 50) -> List[asyncpg.Record]:
        """Get jobs for a specific userbot, optionally filtered by status"""
        if status:
            query = """
                SELECT cq.*, g.tg_chat_id as target_chat_id,
                       COALESCE(g.display_name, g.title) as target_title
                FROM call_queue cq
                JOIN groups g ON g.id = cq.target_group_id
                WHERE cq.forwarding_userbot_id = $1 AND cq.status = $2
                ORDER BY cq.created_at DESC
                LIMIT $3
            """
            return await self.db.fetch(query, userbot_id, status, limit)
        else:
            query = """
                SELECT cq.*, g.tg_chat_id as target_chat_id,
                       COALESCE(g.display_name, g.title) as target_title
                FROM call_queue cq
                JOIN groups g ON g.id = cq.target_group_id
                WHERE cq.forwarding_userbot_id = $1
                ORDER BY cq.created_at DESC
                LIMIT $2
            """
            return await self.db.fetch(query, userbot_id, limit)

    async def reset_stuck_jobs(self, minutes_old: int = 5) -> int:
        """Reset jobs that have been stuck in processing state"""
        query = """
            UPDATE call_queue
            SET status = 'pending'
            WHERE status = 'processing'
            AND created_at < NOW() - INTERVAL '%s minutes'
        """ % minutes_old
        result = await self.db.execute(query)
        return int(result.split()[-1])
