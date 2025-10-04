"""
Auto-reply session management with state machine design.
Replaces the old pending_dm_replies system with a clearer, more reliable approach.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)


class AutoReplySessionModel:
    """
    Manages auto-reply sessions with a clear state machine.

    States:
        WAITING       - Session created, waiting for turn
        READY_TO_CLICK - Turn arrived, ready to click
        CLICKED       - Button clicked, waiting for DM
        DM_RECEIVED   - DM received, ready to reply
        REPLIED       - Reply sent, session complete
        TIMEOUT       - Session expired without completing
        FAILED        - Error occurred
    """

    def __init__(self, db):
        self.db = db

    async def create_session(
        self,
        rule_id: int,
        message_id: int,
        userbot_id: int,
        bot_user_id: int,
        ticker_value: str = ""
    ) -> int:
        """
        Create a new auto-reply session in WAITING state.
        Returns session ID.
        """
        expires_at = datetime.now() + timedelta(minutes=5)

        query = """
            INSERT INTO auto_reply_sessions
                (rule_id, message_id, userbot_id, bot_user_id, ticker_value, state, expires_at)
            VALUES ($1, $2, $3, $4, $5, 'WAITING', $6)
            ON CONFLICT (rule_id, message_id, userbot_id)
            DO UPDATE SET
                bot_user_id = EXCLUDED.bot_user_id,
                ticker_value = EXCLUDED.ticker_value,
                expires_at = EXCLUDED.expires_at,
                state = 'WAITING',
                created_at = NOW()
            RETURNING id
        """

        row = await self.db.fetchrow(query, rule_id, message_id, userbot_id, bot_user_id, ticker_value, expires_at)
        session_id = row['id']

        logger.info(f"[AUTO_REPLY_SESSION] Created session {session_id}: userbot={userbot_id} msg={message_id} rule={rule_id} state=WAITING")
        return session_id

    async def mark_ready(self, session_id: int) -> None:
        """Mark session as READY_TO_CLICK."""
        query = """
            UPDATE auto_reply_sessions
            SET state = 'READY_TO_CLICK', ready_at = NOW()
            WHERE id = $1 AND state = 'WAITING'
        """
        await self.db.execute(query, session_id)
        logger.info(f"[AUTO_REPLY_SESSION] Session {session_id}: state=WAITING→READY_TO_CLICK")

    async def mark_clicked(self, session_id: int) -> None:
        """Mark session as CLICKED after button click."""
        query = """
            UPDATE auto_reply_sessions
            SET state = 'CLICKED', clicked_at = NOW()
            WHERE id = $1 AND state = 'READY_TO_CLICK'
        """
        await self.db.execute(query, session_id)
        logger.info(f"[AUTO_REPLY_SESSION] Session {session_id}: state=READY_TO_CLICK→CLICKED")

    async def mark_dm_received(self, session_id: int) -> None:
        """Mark session as DM_RECEIVED when DM arrives (from any pre-reply state)."""
        # Get old state first for logging
        get_state_query = "SELECT state FROM auto_reply_sessions WHERE id = $1"
        state_row = await self.db.fetchrow(get_state_query, session_id)
        old_state = state_row['state'] if state_row else 'UNKNOWN'

        # Update to DM_RECEIVED
        query = """
            UPDATE auto_reply_sessions
            SET state = 'DM_RECEIVED', dm_received_at = NOW()
            WHERE id = $1 AND state IN ('WAITING', 'READY_TO_CLICK', 'CLICKED')
        """
        result = await self.db.execute(query, session_id)

        if result == 'UPDATE 1':
            logger.info(f"[AUTO_REPLY_SESSION] Session {session_id}: state={old_state}→DM_RECEIVED")
        else:
            logger.warning(f"[AUTO_REPLY_SESSION] Failed to mark session {session_id} as DM_RECEIVED (current state={old_state})")

    async def mark_replied(self, session_id: int) -> None:
        """Mark session as REPLIED after sending reply."""
        query = """
            UPDATE auto_reply_sessions
            SET state = 'REPLIED', replied_at = NOW()
            WHERE id = $1 AND state = 'DM_RECEIVED'
        """
        await self.db.execute(query, session_id)
        logger.info(f"[AUTO_REPLY_SESSION] Session {session_id}: state=DM_RECEIVED→REPLIED")

    async def mark_failed(self, session_id: int, error_message: str) -> None:
        """Mark session as FAILED with error message."""
        query = """
            UPDATE auto_reply_sessions
            SET state = 'FAILED', error_message = $2
            WHERE id = $1
        """
        await self.db.execute(query, session_id, error_message)
        logger.error(f"[AUTO_REPLY_SESSION] Session {session_id}: state→FAILED error={error_message}")

    async def get_session_for_dm(self, userbot_id: int, bot_user_id: int) -> Optional[Dict]:
        """
        Get active session waiting for DM from this bot.
        Accepts sessions in WAITING, READY_TO_CLICK, or CLICKED states.
        (Bot may send DM before click completes)
        """
        query = """
            SELECT id, rule_id, ticker_value, message_id, expires_at, state
            FROM auto_reply_sessions
            WHERE userbot_id = $1
              AND bot_user_id = $2
              AND state IN ('WAITING', 'READY_TO_CLICK', 'CLICKED')
              AND expires_at > NOW()
            ORDER BY created_at DESC
            LIMIT 1
        """
        row = await self.db.fetchrow(query, userbot_id, bot_user_id)

        if row:
            logger.info(f"[AUTO_REPLY_SESSION] Found session {row['id']} for DM: userbot={userbot_id} bot={bot_user_id} state={row['state']}")
            return dict(row)
        else:
            logger.warning(f"[AUTO_REPLY_SESSION] No active session found for DM: userbot={userbot_id} bot={bot_user_id}")
            return None

    async def get_session_by_id(self, session_id: int) -> Optional[Dict]:
        """Get session details by ID."""
        query = "SELECT * FROM auto_reply_sessions WHERE id = $1"
        row = await self.db.fetchrow(query, session_id)
        return dict(row) if row else None

    async def cleanup_expired(self) -> int:
        """
        Mark expired sessions as TIMEOUT and delete old completed sessions.
        Returns count of cleaned up sessions.
        """
        # Mark expired sessions as TIMEOUT
        timeout_query = """
            UPDATE auto_reply_sessions
            SET state = 'TIMEOUT'
            WHERE state NOT IN ('REPLIED', 'TIMEOUT', 'FAILED')
              AND expires_at < NOW()
        """
        await self.db.execute(timeout_query)

        # Delete old completed sessions (older than 10 minutes)
        delete_query = """
            DELETE FROM auto_reply_sessions
            WHERE state IN ('REPLIED', 'TIMEOUT', 'FAILED')
              AND created_at < NOW() - INTERVAL '10 minutes'
        """
        result = await self.db.execute(delete_query)

        # Extract count from result string like "DELETE 5"
        count = 0
        if result:
            parts = result.split()
            if len(parts) == 2 and parts[0] == 'DELETE':
                count = int(parts[1])

        if count > 0:
            logger.info(f"[AUTO_REPLY_SESSION] Cleaned up {count} old sessions")

        return count
