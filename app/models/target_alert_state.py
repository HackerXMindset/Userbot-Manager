from typing import Dict, Any, Optional, List
from .base import BaseModel
from decimal import Decimal
import asyncpg
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TargetAlertStateModel(BaseModel):
    """Model for managing target+token alert state tracking"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "target_token_alert_state"

    async def get_or_create(self, target_id: int, token_id: int,
                           message_id: Optional[int] = None,
                           initial_market_cap: Optional[Decimal] = None) -> asyncpg.Record:
        """Get existing state or create new one for target+token pair"""
        try:
            # Try to get existing record first
            existing = await self.get_by_target_token(target_id, token_id)
            if existing:
                # If message_id provided and current first_message_id is None, update it
                if message_id is not None and existing['first_message_id'] is None:
                    updated = await self.update_first_message(existing['id'], message_id)
                    return updated or existing
                return existing

            # Create new record
            data = {
                'target_id': target_id,
                'token_id': token_id,
                'first_message_id': message_id,
                'initial_market_cap': initial_market_cap,
                'last_alert_multiplier': Decimal('1'),
                'first_sent_at': datetime.utcnow()
            }

            query = """
                INSERT INTO target_token_alert_state
                (target_id, token_id, first_message_id, initial_market_cap, last_alert_multiplier, first_sent_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (target_id, token_id) DO UPDATE SET
                    first_message_id = COALESCE(target_token_alert_state.first_message_id, EXCLUDED.first_message_id),
                    initial_market_cap = COALESCE(target_token_alert_state.initial_market_cap, EXCLUDED.initial_market_cap)
                RETURNING *
            """

            return await self.db.fetchrow(
                query,
                target_id,
                token_id,
                message_id,
                initial_market_cap,
                Decimal('1'),
                datetime.utcnow()
            )

        except Exception as e:
            logger.error(f"Error in get_or_create for target {target_id}, token {token_id}: {e}")
            raise

    async def get_by_target_token(self, target_id: int, token_id: int) -> Optional[asyncpg.Record]:
        """Get state record for specific target+token pair"""
        query = """
            SELECT * FROM target_token_alert_state
            WHERE target_id = $1 AND token_id = $2
        """
        return await self.db.fetchrow(query, target_id, token_id)

    async def get_by_token_id(self, token_id: int) -> List[asyncpg.Record]:
        """Get all state records for a token across all targets"""
        query = """
            SELECT tas.*, t.dest_chat_id, t.alerts_enabled
            FROM target_token_alert_state tas
            JOIN targets t ON t.id = tas.target_id
            WHERE tas.token_id = $1
            ORDER BY tas.target_id
        """
        return await self.db.fetch(query, token_id)

    async def update_after_alert(self, target_id: int, token_id: int,
                                new_multiplier: Decimal, alert_timestamp: Optional[datetime] = None) -> Optional[asyncpg.Record]:
        """Update state after sending an alert"""
        if alert_timestamp is None:
            alert_timestamp = datetime.utcnow()

        query = """
            UPDATE target_token_alert_state
            SET last_alert_multiplier = $3,
                last_alert_at = $4
            WHERE target_id = $1 AND token_id = $2
            RETURNING *
        """

        try:
            return await self.db.fetchrow(query, target_id, token_id, new_multiplier, alert_timestamp)
        except Exception as e:
            logger.error(f"Error updating alert state for target {target_id}, token {token_id}: {e}")
            raise

    async def update_first_message(self, state_id: int, message_id: Optional[int]) -> Optional[asyncpg.Record]:
        """Update first_message_id for threading"""
        query = """
            UPDATE target_token_alert_state
            SET first_message_id = $2
            WHERE id = $1
            RETURNING *
        """
        return await self.db.fetchrow(query, state_id, message_id)

    async def clear_first_message(self, target_id: int, token_id: int) -> Optional[asyncpg.Record]:
        """Clear first_message_id when message becomes invalid (deleted, etc.)"""
        query = """
            UPDATE target_token_alert_state
            SET first_message_id = NULL
            WHERE target_id = $1 AND token_id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, target_id, token_id)

    async def ensure_state(self, target_id: int, token_id: int,
                          message_id: Optional[int] = None,
                          initial_mc: Optional[Decimal] = None) -> asyncpg.Record:
        """
        Ensure state exists for target+token pair.
        Creates if missing, updates first_message_id if currently NULL.
        Sets initial_market_cap only on first insert.
        """
        return await self.get_or_create(target_id, token_id, message_id, initial_mc)

    async def get_states_by_target(self, target_id: int) -> List[asyncpg.Record]:
        """Get all alert states for a specific target"""
        query = """
            SELECT tas.*,
                   tt.address as token_address,
                   tt.ticker as token_ticker,
                   tt.last_mc as current_market_cap
            FROM target_token_alert_state tas
            JOIN tokens_tracked tt ON tt.id = tas.token_id
            WHERE tas.target_id = $1
            ORDER BY tas.last_alert_at DESC NULLS LAST, tas.first_sent_at DESC
        """
        return await self.db.fetch(query, target_id)

    async def get_active_states_for_token(self, token_id: int) -> List[asyncpg.Record]:
        """Get alert states for token where target has alerts enabled"""
        query = """
            SELECT tas.*,
                   t.dest_chat_id,
                   t.alerts_enabled,
                   t.alerts_modes,
                   t.alerts_thresholds,
                   t.alerts_sensitivity_percent
            FROM target_token_alert_state tas
            JOIN targets t ON t.id = tas.target_id
            WHERE tas.token_id = $1
            AND t.alerts_enabled = true
            ORDER BY tas.target_id
        """
        return await self.db.fetch(query, token_id)

    async def cleanup_old_states(self, days_old: int = 30) -> int:
        """Clean up old alert states for inactive tokens"""
        query = """
            DELETE FROM target_token_alert_state
            WHERE id IN (
                SELECT tas.id
                FROM target_token_alert_state tas
                JOIN tokens_tracked tt ON tt.id = tas.token_id
                WHERE tt.status IN ('stopped', 'error')
                AND tas.first_sent_at < NOW() - INTERVAL '%s days'
            )
        """
        result = await self.db.execute(query % days_old)
        deleted_count = int(result.split()[-1]) if result else 0
        logger.info(f"Cleaned up {deleted_count} old alert states")
        return deleted_count

    async def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for alert states"""
        query = """
            SELECT
                COUNT(*) as total_states,
                COUNT(DISTINCT target_id) as unique_targets,
                COUNT(DISTINCT token_id) as unique_tokens,
                COUNT(CASE WHEN last_alert_at IS NOT NULL THEN 1 END) as states_with_alerts,
                AVG(last_alert_multiplier) as avg_last_multiplier
            FROM target_token_alert_state
        """
        result = await self.db.fetchrow(query)
        return dict(result) if result else {}