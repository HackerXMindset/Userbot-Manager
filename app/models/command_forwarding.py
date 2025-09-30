from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg
import logging
import traceback
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Set detailed logging for command forwarding model operations
logging.getLogger(__name__).setLevel(logging.DEBUG)

class CommandForwardingRuleModel(BaseModel):
    """Model for managing command forwarding rules with comprehensive debugging"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "command_forwarding_rules"
        logger.debug("CommandForwardingRuleModel initialized")

    async def get_by_id(self, record_id: int) -> Optional[asyncpg.Record]:
        """Get rule by ID with group title"""
        query = """
            SELECT cfr.*,
                   COALESCE(g.title, g.display_name, 'Unknown Group') as source_group_title
            FROM command_forwarding_rules cfr
            LEFT JOIN groups g ON g.id = cfr.source_group_id
            WHERE cfr.id = $1
        """
        return await self.db.fetchrow(query, record_id)

    async def get_by_source_group(self, source_group_id: int) -> List[asyncpg.Record]:
        """Get all rules for a source group"""
        query = """
            SELECT cfr.*, g.title as source_group_title
            FROM command_forwarding_rules cfr
            JOIN groups g ON g.id = cfr.source_group_id
            WHERE cfr.source_group_id = $1
            ORDER BY cfr.created_at DESC
        """
        return await self.db.fetch(query, source_group_id)

    async def get_enabled_rules_for_group(self, source_group_id: int) -> List[asyncpg.Record]:
        """Get enabled rules for a source group with debugging"""
        try:
            logger.debug(f"Getting enabled command forwarding rules for group: {source_group_id}")
            query = """
                SELECT * FROM command_forwarding_rules
                WHERE source_group_id = $1 AND enabled = true
                ORDER BY created_at DESC
            """
            result = await self.db.fetch(query, source_group_id)
            logger.debug(f"Found {len(result)} enabled command forwarding rules for group {source_group_id}")

            for rule in result:
                logger.debug(f"Rule {rule['id']}: command='{rule['command_text']}', "
                           f"userbot={rule['forwarding_userbot_id']}, "
                           f"destination={rule['destination_channel_id']}, "
                           f"monitored_users={rule['allowed_command_user_ids']}, "
                           f"reply_users={rule['allowed_reply_user_ids']}, "
                           f"schedule_enabled={rule['schedule_enabled']}")

            return result

        except Exception as e:
            logger.error(f"Failed to get enabled command rules for group {source_group_id}: {str(e)}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def create_rule(self, source_group_id: int, command_text: str, destination_channel_id: int,
                         allowed_command_user_ids: List[int], allowed_reply_user_ids: List[int],
                         forwarding_userbot_id: int, schedule_enabled: bool = False,
                         schedule_interval_minutes: Optional[int] = None, post_timestamp: bool = False,
                         timestamp_timezone: str = 'IST') -> asyncpg.Record:
        """Create a new command forwarding rule with debugging"""
        try:
            logger.info(f"Creating command forwarding rule: source_group={source_group_id}, "
                       f"command='{command_text}', destination={destination_channel_id}, "
                       f"monitored_users={allowed_command_user_ids}, "
                       f"reply_users={allowed_reply_user_ids}, "
                       f"userbot={forwarding_userbot_id}, "
                       f"schedule_enabled={schedule_enabled}, "
                       f"schedule_interval={schedule_interval_minutes}, "
                       f"post_timestamp={post_timestamp}, "
                       f"timezone={timestamp_timezone}")

            # Calculate next scheduled time if scheduling is enabled
            next_scheduled_at = None
            if schedule_enabled and schedule_interval_minutes:
                next_scheduled_at = datetime.utcnow() + timedelta(minutes=schedule_interval_minutes)

            data = {
                'source_group_id': source_group_id,
                'command_text': command_text,
                'destination_channel_id': destination_channel_id,
                'allowed_command_user_ids': allowed_command_user_ids,
                'allowed_reply_user_ids': allowed_reply_user_ids,
                'forwarding_userbot_id': forwarding_userbot_id,
                'schedule_enabled': schedule_enabled,
                'schedule_interval_minutes': schedule_interval_minutes,
                'next_scheduled_at': next_scheduled_at,
                'post_timestamp': post_timestamp,
                'timestamp_timezone': timestamp_timezone
            }

            logger.debug(f"Rule data: {data}")
            result = await self.create(data)
            logger.info(f"Successfully created command forwarding rule with ID: {result['id']}")
            return result

        except Exception as e:
            logger.error(f"Failed to create command forwarding rule: {str(e)}")
            logger.error(f"Parameters: source_group={source_group_id}, command='{command_text}', destination={destination_channel_id}")
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise

    async def toggle_enabled(self, rule_id: int) -> bool:
        """Toggle rule enabled status"""
        query = """
            UPDATE command_forwarding_rules
            SET enabled = NOT enabled, updated_at = NOW()
            WHERE id = $1
            RETURNING enabled
        """
        result = await self.db.fetchval(query, rule_id)
        return result

    async def toggle_schedule_enabled(self, rule_id: int) -> bool:
        """Toggle schedule enabled status and update next scheduled time"""
        query = """
            UPDATE command_forwarding_rules
            SET schedule_enabled = NOT schedule_enabled,
                next_scheduled_at = CASE
                    WHEN NOT schedule_enabled AND schedule_interval_minutes IS NOT NULL
                    THEN NOW() + INTERVAL '1 minute' * schedule_interval_minutes
                    ELSE NULL
                END,
                updated_at = NOW()
            WHERE id = $1
            RETURNING schedule_enabled
        """
        result = await self.db.fetchval(query, rule_id)
        return result

    async def toggle_timestamp_posting(self, rule_id: int) -> bool:
        """Toggle timestamp posting for a rule"""
        query = """
            UPDATE command_forwarding_rules
            SET post_timestamp = NOT post_timestamp, updated_at = NOW()
            WHERE id = $1
            RETURNING post_timestamp
        """
        result = await self.db.fetchval(query, rule_id)
        return result

    async def update_timezone(self, rule_id: int, timezone: str) -> Optional[asyncpg.Record]:
        """Update timezone for timestamp posting"""
        query = """
            UPDATE command_forwarding_rules
            SET timestamp_timezone = $1, updated_at = NOW()
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, timezone, rule_id)

    async def update_schedule(self, rule_id: int, schedule_enabled: bool,
                             schedule_interval_minutes: Optional[int] = None) -> Optional[asyncpg.Record]:
        """Update schedule settings for a rule"""
        next_scheduled_at = None
        if schedule_enabled and schedule_interval_minutes:
            next_scheduled_at = datetime.utcnow() + timedelta(minutes=schedule_interval_minutes)

        query = """
            UPDATE command_forwarding_rules
            SET schedule_enabled = $1,
                schedule_interval_minutes = $2,
                next_scheduled_at = $3,
                updated_at = NOW()
            WHERE id = $4
            RETURNING *
        """
        return await self.db.fetchrow(query, schedule_enabled, schedule_interval_minutes, next_scheduled_at, rule_id)

    async def get_rules_ready_for_execution(self) -> List[asyncpg.Record]:
        """Get rules that are ready for scheduled execution"""
        query = """
            SELECT cfr.*, g.tg_chat_id as source_chat_id
            FROM command_forwarding_rules cfr
            JOIN groups g ON g.id = cfr.source_group_id
            WHERE cfr.enabled = true
            AND cfr.schedule_enabled = true
            AND cfr.next_scheduled_at IS NOT NULL
            AND cfr.next_scheduled_at <= NOW()
            ORDER BY cfr.next_scheduled_at ASC
        """
        return await self.db.fetch(query)

    async def update_next_scheduled_time(self, rule_id: int) -> Optional[asyncpg.Record]:
        """Update the next scheduled time for a rule after execution"""
        query = """
            UPDATE command_forwarding_rules
            SET last_scheduled_at = NOW(),
                next_scheduled_at = CASE
                    WHEN schedule_interval_minutes IS NOT NULL
                    THEN NOW() + INTERVAL '1 minute' * schedule_interval_minutes
                    ELSE NULL
                END,
                updated_at = NOW()
            WHERE id = $1
            RETURNING *
        """
        return await self.db.fetchrow(query, rule_id)

    async def get_all_with_details(self) -> List[asyncpg.Record]:
        """Get all rules with group and channel details"""
        query = """
            SELECT cfr.*,
                   g.title as source_group_title,
                   g.tg_chat_id as source_group_chat_id
            FROM command_forwarding_rules cfr
            JOIN groups g ON g.id = cfr.source_group_id
            ORDER BY cfr.enabled DESC, cfr.created_at DESC
        """
        return await self.db.fetch(query)


class CommandTrackedMessageModel(BaseModel):
    """Model for managing tracked command messages"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "command_tracked_messages"
        logger.debug("CommandTrackedMessageModel initialized")

    async def track_command(self, rule_id: int, original_message_id: int, chat_id: int,
                           sender_id: int, command_text: str) -> Optional[asyncpg.Record]:
        """Track a new command message"""
        try:
            query = """
                INSERT INTO command_tracked_messages (rule_id, original_message_id, chat_id, sender_id, command_text)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (original_message_id, chat_id, rule_id) DO NOTHING
                RETURNING *
            """
            return await self.db.fetchrow(query, rule_id, original_message_id, chat_id, sender_id, command_text)
        except Exception as e:
            logger.error(f"Failed to track command: {e}")
            return None

    async def get_tracked_messages_for_reply(self, reply_to_message_id: int, chat_id: int) -> List[asyncpg.Record]:
        """Get tracked messages that a reply might be responding to"""
        query = """
            SELECT * FROM command_tracked_messages
            WHERE original_message_id = $1 AND chat_id = $2 AND status = 'tracking'
            AND created_at > NOW() - INTERVAL '3 minutes'
        """
        return await self.db.fetch(query, reply_to_message_id, chat_id)

    async def mark_forwarded(self, tracked_id: int, reply_sender_id: int, reply_message_id: int) -> bool:
        """Mark a tracked message as forwarded"""
        try:
            query = """
                UPDATE command_tracked_messages
                SET status = 'forwarded',
                    reply_sender_id = $1,
                    last_reply_message_id = $2,
                    updated_at = NOW()
                WHERE id = $3
            """
            await self.db.execute(query, reply_sender_id, reply_message_id, tracked_id)
            return True
        except Exception as e:
            logger.error(f"Failed to mark message as forwarded: {e}")
            return False

    async def cleanup_old_tracking(self, hours_old: int = 1) -> int:
        """Clean up old tracking records"""
        query = """
            DELETE FROM command_tracked_messages
            WHERE status = 'tracking' AND created_at < NOW() - INTERVAL '1 hour' * $1
        """
        result = await self.db.execute(query, hours_old)
        return int(result.split()[-1]) if result else 0