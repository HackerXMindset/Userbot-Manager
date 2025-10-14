from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from .base import BaseModel
import asyncpg

class TokenCallHistoryModel(BaseModel):
    """Model for managing token call history records"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "token_call_history"

    async def log_call(self,
                      token_address: str,
                      caller_user_id: Optional[int] = None,
                      caller_name: Optional[str] = None,
                      source_chat_id: int = None,
                      source_name: Optional[str] = None,
                      source_type: Optional[str] = None,
                      target_chat_id: int = None,
                      forwarding_userbot_id: Optional[int] = None,
                      routing_rule_id: Optional[int] = None,
                      curated_alpha_rule_id: Optional[int] = None,
                      market_cap_at_call: Optional[int] = None,
                      call_job_id: Optional[int] = None,
                      forwarded_message_id: Optional[int] = None) -> asyncpg.Record:
        """Log a successful call to history"""
        data = {
            'token_address': token_address,
            'source_chat_id': source_chat_id,
            'target_chat_id': target_chat_id,
            'called_at': datetime.now()
        }

        # Add optional fields if provided
        if caller_user_id is not None:
            data['caller_user_id'] = caller_user_id
        if caller_name is not None:
            data['caller_name'] = caller_name
        if source_name is not None:
            data['source_name'] = source_name
        if source_type is not None:
            data['source_type'] = source_type
        if forwarding_userbot_id is not None:
            data['forwarding_userbot_id'] = forwarding_userbot_id
        if routing_rule_id is not None:
            data['routing_rule_id'] = routing_rule_id
        if curated_alpha_rule_id is not None:
            data['curated_alpha_rule_id'] = curated_alpha_rule_id
        if market_cap_at_call is not None:
            data['market_cap_at_call'] = market_cap_at_call
        if call_job_id is not None:
            data['call_job_id'] = call_job_id
        if forwarded_message_id is not None:
            data['forwarded_message_id'] = forwarded_message_id

        if target_chat_id is not None:
            try:
                exists = await self.db.fetchval(
                    """
                    SELECT 1 FROM token_call_history
                    WHERE token_address = $1 AND target_chat_id = $2
                    LIMIT 1
                    """,
                    token_address,
                    target_chat_id,
                )
                if not exists:
                    data['is_first_message'] = True
            except Exception:
                data.setdefault('is_first_message', False)

        return await self.create(data)

    async def get_recent_calls(self,
                              token_address: str,
                              limit: int = 15,
                              hours_back: int = 48) -> List[asyncpg.Record]:
        """Get recent calls for a specific token"""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        query = """
            SELECT * FROM token_call_history
            WHERE token_address = $1
            AND called_at > $2
            ORDER BY called_at DESC
            LIMIT $3
        """

        return await self.db.fetch(query, token_address, cutoff_time, limit)

    async def get_call_count_for_token(self, token_address: str, hours_back: int = 24) -> int:
        """Get total call count for a token in the specified time period"""
        cutoff_time = datetime.now() - timedelta(hours=hours_back)

        query = """
            SELECT COUNT(*) FROM token_call_history
            WHERE token_address = $1
            AND called_at > $2
        """

        return await self.db.fetchval(query, token_address, cutoff_time)

    async def cleanup_old_records(self, days_to_keep: int = 7) -> int:
        """Remove old call history records older than specified days"""
        cutoff_time = datetime.now() - timedelta(days=days_to_keep)

        query = "DELETE FROM token_call_history WHERE called_at < $1"
        result = await self.db.execute(query, cutoff_time)

        # Extract count from result string like "DELETE 42"
        return int(result.split()[-1]) if result.split()[-1].isdigit() else 0
