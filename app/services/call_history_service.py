"""
Call History Service - Formats call history for template placeholders
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from app.db import db
from app.models.token_call_history import TokenCallHistoryModel
from app.utils.call_history_utils import (
    format_call_history_time,
    format_call_history_market_cap,
    format_source_name_with_type,
    get_caller_display_name,
)

logger = logging.getLogger(__name__)


class CallHistoryService:
    """Service for formatting call history data for template display"""

    def __init__(self):
        self.history_model = TokenCallHistoryModel(db)

    async def log_call(self, call_data: Dict[str, Any]) -> None:
        """Persist a call event into token_call_history using structured data."""

        if not call_data:
            logger.warning("log_call invoked with empty call_data")
            return

        token_address = call_data.get('token_address')
        if not token_address:
            logger.warning("log_call missing token_address; skipping")
            return

        try:
            await self.history_model.log_call(
                token_address=token_address,
                caller_user_id=call_data.get('caller_user_id'),
                caller_name=call_data.get('caller_name'),
                source_chat_id=call_data.get('source_chat_id'),
                source_name=call_data.get('source_name'),
                source_type=call_data.get('source_type'),
                target_chat_id=call_data.get('target_chat_id'),
                forwarding_userbot_id=call_data.get('forwarding_userbot_id'),
                routing_rule_id=call_data.get('routing_rule_id'),
                curated_alpha_rule_id=call_data.get('curated_alpha_rule_id'),
                market_cap_at_call=call_data.get('market_cap_cents'),
                call_job_id=call_data.get('call_job_id'),
            )
        except Exception as exc:
            logger.error(
                "Failed to log call history for %s: %s", token_address, exc, exc_info=True
            )

    async def build_recent_history_block(
        self,
        token_address: str,
        limit: int = 10,
        hours_back: int = 48,
        current_sources: Optional[List[Dict[str, Any]]] = None,
        market_cap_display: Optional[str] = None,
        fallback_caller_name: Optional[str] = None,
        fallback_caller_id: Optional[int] = None,
    ) -> str:
        """Return a formatted recent-call block for template consumption."""

        try:
            recent_calls = await self.history_model.get_recent_calls(
                token_address=token_address,
                limit=limit,
                hours_back=hours_back,
            )
        except Exception as exc:
            logger.error(
                "Error fetching call history for token %s: %s", token_address, exc, exc_info=True
            )
            return "🌕 Recent Callers\nError loading history"

        lines: List[str] = ["🌕 Recent Callers (Last 48h)"]

        current_market_cap = self._parse_market_cap_display(market_cap_display)

        if current_sources:
            now = datetime.now(timezone.utc)
            for source in current_sources:
                source_name = source.get('name')
                source_type = source.get('type')
                entry_caller = source.get('caller_name') or fallback_caller_name
                entry_caller_id = source.get('caller_user_id') or fallback_caller_id

                caller_display = get_caller_display_name(entry_caller, entry_caller_id)
                market_cap_value = source.get('market_cap_cents') or current_market_cap
                market_cap_text = format_call_history_market_cap(market_cap_value)
                source_display = format_source_name_with_type(source_name, source_type)
                time_str = format_call_history_time(now)

                lines.append(f"• {time_str} — {caller_display} {market_cap_text} via {source_display}")

        if not recent_calls:
            if len(lines) == 1:
                return "🌕 Recent Callers\nNo logged forwards yet"
            return "\n".join(lines)

        for record in recent_calls:
            try:
                lines.append(f"• {self._format_history_entry(record)}")
            except Exception as format_error:
                logger.warning(f"Failed to format call history line: {format_error}")
                caller = record.get('caller_name', 'Unknown')
                source = record.get('source_name', 'Unknown Source')
                lines.append(f"• {caller} via {source}")

        return "\n".join(lines)

    def _format_history_entry(self, record: Dict[str, Any]) -> str:
        time_str = format_call_history_time(record.get('called_at'))
        caller = get_caller_display_name(record.get('caller_name'), record.get('caller_user_id'))
        market_cap = format_call_history_market_cap(record.get('market_cap_at_call'))
        source = format_source_name_with_type(record.get('source_name'), record.get('source_type'))

        return f"{time_str} — {caller} {market_cap} via {source}"

    def _parse_market_cap_display(self, mc_str: Optional[str]) -> Optional[int]:
        if not mc_str or mc_str == 'N/A':
            return None
        try:
            value = mc_str.replace('$', '').replace(',', '').strip()
            multiplier = 1
            if value.endswith('K'):
                multiplier = 1_000
                value = value[:-1]
            elif value.endswith('M'):
                multiplier = 1_000_000
                value = value[:-1]
            elif value.endswith('B'):
                multiplier = 1_000_000_000
                value = value[:-1]
            numeric = float(value) * multiplier
            return int(numeric * 100)
        except (ValueError, TypeError):
            logger.debug(f"Could not parse market cap display: {mc_str}")
            return None

    async def get_call_history_stats(self, token_address: str) -> dict:
        """Get basic statistics about call history for a token"""
        try:
            total_calls_24h = await self.history_model.get_call_count_for_token(
                token_address, hours_back=24
            )
            total_calls_48h = await self.history_model.get_call_count_for_token(
                token_address, hours_back=48
            )

            return {
                'total_calls_24h': total_calls_24h,
                'total_calls_48h': total_calls_48h,
                'has_recent_activity': total_calls_24h > 0
            }
        except Exception as e:
            logger.error(f"Error getting call history stats for token {token_address}: {e}")
            return {
                'total_calls_24h': 0,
                'total_calls_48h': 0,
                'has_recent_activity': False
            }

    async def cleanup_old_history(self, days_to_keep: int = 7) -> int:
        """Clean up old call history records"""
        try:
            deleted_count = await self.history_model.cleanup_old_records(days_to_keep)
            logger.info(f"Cleaned up {deleted_count} old call history records")
            return deleted_count
        except Exception as e:
            logger.error(f"Error cleaning up call history: {e}", exc_info=True)
            return 0
