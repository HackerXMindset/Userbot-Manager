"""
Models for managing dynamic reply messages and pending DM auto-replies.
"""
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)


class DynamicReplyModel:
    """Model for managing preset reply messages."""

    def __init__(self, db):
        self.db = db

    async def add_reply(self, message_text: str) -> int:
        """Add a new reply message."""
        query = """
            INSERT INTO dynamic_reply_messages (message_text)
            VALUES ($1)
            RETURNING id
        """
        reply_id = await self.db.fetchval(query, message_text)
        logger.info(f"[DYNAMIC_REPLY] Added new reply message (ID: {reply_id})")
        return reply_id

    async def get_all_replies(self) -> List[Dict]:
        """Get all reply messages."""
        query = """
            SELECT id, message_text, created_at
            FROM dynamic_reply_messages
            ORDER BY created_at DESC
        """
        rows = await self.db.fetch(query)
        return [dict(row) for row in rows]

    async def delete_reply(self, reply_id: int) -> bool:
        """Delete a reply message."""
        query = "DELETE FROM dynamic_reply_messages WHERE id = $1"
        result = await self.db.execute(query, reply_id)
        success = result.split()[-1] == "1"
        if success:
            logger.info(f"[DYNAMIC_REPLY] Deleted reply message (ID: {reply_id})")
        return success

    async def get_reply_by_id(self, reply_id: int) -> Optional[Dict]:
        """Get a specific reply message by ID."""
        query = "SELECT id, message_text, created_at FROM dynamic_reply_messages WHERE id = $1"
        row = await self.db.fetchrow(query, reply_id)
        return dict(row) if row else None

    async def get_usage_for_rule(self, rule_id: int, reply_id: int) -> Dict:
        """Get usage stats for a specific reply on a specific rule."""
        query = """
            SELECT use_count, last_used_at
            FROM dynamic_reply_usage
            WHERE rule_id = $1 AND reply_id = $2
        """
        row = await self.db.fetchrow(query, rule_id, reply_id)
        if row:
            return {'use_count': row['use_count'], 'last_used_at': row['last_used_at']}
        return {'use_count': 0, 'last_used_at': None}

    async def increment_usage(self, rule_id: int, reply_id: int) -> None:
        """Increment usage count for a reply on a specific rule."""
        query = """
            INSERT INTO dynamic_reply_usage (rule_id, reply_id, use_count, last_used_at)
            VALUES ($1, $2, 1, NOW())
            ON CONFLICT (rule_id, reply_id)
            DO UPDATE SET
                use_count = dynamic_reply_usage.use_count + 1,
                last_used_at = NOW()
        """
        await self.db.execute(query, rule_id, reply_id)
        logger.debug(f"[DYNAMIC_REPLY] Incremented usage: rule={rule_id}, reply={reply_id}")

    async def get_all_usage_for_rule(self, rule_id: int) -> Dict[int, int]:
        """Get all usage stats for a rule. Returns {reply_id: use_count}."""
        query = """
            SELECT reply_id, use_count
            FROM dynamic_reply_usage
            WHERE rule_id = $1
        """
        rows = await self.db.fetch(query, rule_id)
        return {row['reply_id']: row['use_count'] for row in rows}

    async def get_random_reply_for_rule(self, rule_id: int) -> Optional[Dict]:
        """
        Get a random reply message and increment its usage for this rule.
        Returns the reply with 'id' and 'message_text'.
        """
        # Get all available replies
        all_replies = await self.get_all_replies()

        if not all_replies:
            logger.warning(f"[DYNAMIC_REPLY] No replies available for rule {rule_id}")
            return None

        # Pick random reply
        selected = random.choice(all_replies)

        # Increment usage
        await self.increment_usage(rule_id, selected['id'])

        logger.info(f"[DYNAMIC_REPLY] Selected random reply {selected['id']} for rule {rule_id}")
        return selected


class PendingDMReplyModel:
    """Model for tracking pending DM auto-replies after button clicks."""

    def __init__(self, db):
        self.db = db

    async def add_pending(self, rule_id: int, userbot_id: int, bot_user_id: int, ticker: str, message_id: int = None) -> None:
        """
        Add a pending DM watch entry. Expires in 5 minutes.
        Uses ON CONFLICT to update if already exists.
        """
        expires_at = datetime.now() + timedelta(minutes=5)

        query = """
            INSERT INTO pending_dm_replies
                (rule_id, userbot_id, expected_bot_user_id, ticker_value, expires_at, dm_received, replied, message_id)
            VALUES ($1, $2, $3, $4, $5, FALSE, FALSE, $6)
            ON CONFLICT (rule_id, userbot_id, expected_bot_user_id)
            DO UPDATE SET
                ticker_value = EXCLUDED.ticker_value,
                clicked_at = NOW(),
                expires_at = EXCLUDED.expires_at,
                dm_received = FALSE,
                replied = FALSE,
                message_id = EXCLUDED.message_id
        """
        await self.db.execute(query, rule_id, userbot_id, bot_user_id, ticker, expires_at, message_id)
        logger.info(f"[PENDING_DM] Added watch: rule={rule_id}, userbot={userbot_id}, bot={bot_user_id}, msg={message_id}, expires={expires_at}")

    async def check_pending(self, userbot_id: int, bot_user_id: int) -> Optional[Dict]:
        """
        Check if we're expecting a DM from this bot to this userbot.
        Returns rule info if found, not expired, and not already replied.
        Also cleans up the entry if it's expired.
        """
        query = """
            SELECT id, rule_id, ticker_value, expires_at, replied
            FROM pending_dm_replies
            WHERE userbot_id = $1 AND expected_bot_user_id = $2 AND replied = FALSE
            ORDER BY clicked_at DESC
            LIMIT 1
        """
        logger.info(f"[PENDING_DM] check_pending query: userbot={userbot_id}, bot={bot_user_id}")
        row = await self.db.fetchrow(query, userbot_id, bot_user_id)

        if not row:
            logger.info(f"[PENDING_DM] No pending entry found for userbot={userbot_id}, bot={bot_user_id}")
            # Debug: check if entry exists but with replied=TRUE
            debug_query = "SELECT id, replied, turn_completed_at FROM pending_dm_replies WHERE userbot_id = $1 AND expected_bot_user_id = $2 ORDER BY clicked_at DESC LIMIT 1"
            debug_row = await self.db.fetchrow(debug_query, userbot_id, bot_user_id)
            if debug_row:
                logger.info(f"[PENDING_DM] Found entry with replied={debug_row['replied']}, turn_completed_at={debug_row['turn_completed_at']}")
            return None

        # Check if expired
        if row['expires_at'] < datetime.now():
            logger.info(f"[PENDING_DM] Entry {row['id']} expired, removing")
            await self.remove_pending(row['id'])
            return None

        return dict(row)

    async def remove_pending(self, pending_id: int) -> None:
        """Remove a pending DM watch entry."""
        query = "DELETE FROM pending_dm_replies WHERE id = $1"
        await self.db.execute(query, pending_id)
        logger.debug(f"[PENDING_DM] Removed pending entry {pending_id}")

    async def mark_replied(self, pending_id: int) -> None:
        """Mark that we've replied to the DM."""
        query = """
            UPDATE pending_dm_replies
            SET replied = TRUE, turn_completed_at = NOW()
            WHERE id = $1
        """
        await self.db.execute(query, pending_id)
        logger.debug(f"[PENDING_DM] Marked pending {pending_id} as replied")

    async def get_previous_bot_status(self, rule_id: int, my_userbot_id: int, all_userbot_ids: List[int], message_id: int) -> bool:
        """
        Check if the previous bot in sequence has completed their turn for THIS message.
        Returns True if it's this bot's turn to click.
        """
        sorted_ids = sorted(all_userbot_ids)
        logger.info(f"[TURN_CHECK] Checking turn for userbot {my_userbot_id}, sorted_ids={sorted_ids}, msg={message_id}")

        try:
            my_index = sorted_ids.index(my_userbot_id)
        except ValueError:
            logger.info(f"[TURN_CHECK] Userbot {my_userbot_id} not in list, proceeding")
            return True  # Not in list, proceed anyway

        if my_index == 0:
            logger.info(f"[TURN_CHECK] Userbot {my_userbot_id} is first bot, proceeding")
            return True  # First bot, always go

        # Check if previous bot has completed for THIS specific message
        previous_bot_id = sorted_ids[my_index - 1]
        logger.info(f"[TURN_CHECK] Userbot {my_userbot_id} checking if previous bot {previous_bot_id} completed msg {message_id}")

        query = """
            SELECT replied, turn_completed_at
            FROM pending_dm_replies
            WHERE rule_id = $1 AND userbot_id = $2 AND message_id = $3 AND replied = TRUE
            ORDER BY turn_completed_at DESC
            LIMIT 1
        """
        row = await self.db.fetchrow(query, rule_id, previous_bot_id, message_id)

        if row:
            logger.info(f"[TURN_CHECK] Previous bot {previous_bot_id} HAS completed turn at {row['turn_completed_at']}, approving turn for {my_userbot_id}")
            return True
        else:
            logger.info(f"[TURN_CHECK] Previous bot {previous_bot_id} has NOT completed turn yet, denying turn for {my_userbot_id}")
            return False

    async def cleanup_expired(self) -> int:
        """Remove all expired pending DM entries. Returns count of removed entries."""
        query = """
            DELETE FROM pending_dm_replies
            WHERE expires_at < NOW()
        """
        result = await self.db.execute(query)
        count = int(result.split()[-1])
        if count > 0:
            logger.info(f"[PENDING_DM] Cleaned up {count} expired entries")
        return count
