import logging
from typing import Dict, Any, Optional, List
from .base import BaseModel

logger = logging.getLogger(__name__)


class GainAlertModel(BaseModel):
    """Model for recording sensitivity-based gain alert events."""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "gain_alert_events"

    async def record_event(
        self,
        token_id: int,
        group_id: int,
        multiplier: float,
        vip_multiplier: Optional[float],
        initial_mc: float,
        current_mc: float,
        time_delta_seconds: int,
        threshold: float,
        emoji: str,
    ) -> Optional[int]:
        """Insert a new gain alert event."""
        try:
            query = """
                INSERT INTO gain_alert_events (
                    token_id,
                    group_id,
                    multiplier,
                    vip_multiplier,
                    initial_market_cap,
                    current_market_cap,
                    elapsed_seconds,
                    threshold_multiplier,
                    emoji
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING id
            """
            event_id = await self.db.fetchval(
                query,
                token_id,
                group_id,
                multiplier,
                vip_multiplier,
                initial_mc,
                current_mc,
                time_delta_seconds,
                threshold,
                emoji,
            )
            logger.debug(
                "Recorded gain alert event: token=%s group=%s multiplier=%.2f emoji=%s",
                token_id,
                group_id,
                multiplier,
                emoji,
            )
            return event_id
        except Exception as exc:
            logger.error("Failed to record gain alert event: %s", exc)
            return None

