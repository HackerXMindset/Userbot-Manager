"""
Call History Service - Formats call history for template placeholders
"""

import logging
from typing import List, Optional

from app.db import db
from app.models.token_call_history import TokenCallHistoryModel
from app.utils.call_history_utils import format_call_history_line

logger = logging.getLogger(__name__)


class CallHistoryService:
    """Service for formatting call history data for template display"""

    def __init__(self):
        self.history_model = TokenCallHistoryModel(db)

    async def format_call_history_for_token(self,
                                          token_address: str,
                                          limit: int = 15,
                                          hours_back: int = 48) -> str:
        """
        Generate formatted call history string for a token.
        Returns format like:

        🌕 Recent History
        1h:26min ago - Twae_ @11.26K in 101 in the Trenches [FC]
        1h:25min ago - 47 @12.16K in Cache's Lounge😝
        55min ago - Kekule @26.27K in PBC Lounge
        0s ago - Naked @42.66K in DJ's LOUNGE
        """
        try:
            # Get recent calls for this token
            recent_calls = await self.history_model.get_recent_calls(
                token_address=token_address,
                limit=limit,
                hours_back=hours_back
            )

            if not recent_calls:
                return "🌕 Recent History\nNo recent call history found"

            # Format header
            lines = ["🌕 Recent History"]

            # Format each call record
            for record in recent_calls:
                try:
                    formatted_line = format_call_history_line(record)
                    lines.append(formatted_line)
                except Exception as format_error:
                    logger.warning(f"Failed to format call history line: {format_error}")
                    # Add fallback line so we don't lose the entry completely
                    time_ago = "Unknown time"
                    caller = record.get('caller_name', 'Unknown')
                    source = record.get('source_name', 'Unknown Source')
                    lines.append(f"{time_ago} - {caller} in {source}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error formatting call history for token {token_address}: {e}", exc_info=True)
            return "🌕 Recent History\nError loading call history"

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