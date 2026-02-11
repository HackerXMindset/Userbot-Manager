from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg
import json

class SourceChatModel(BaseModel):
    """Model for managing source chats"""
    
    def __init__(self, db):
        super().__init__(db)
        self.table_name = "source_chats"
    
    async def get_all_sources(self) -> List[asyncpg.Record]:
        """Get all source chats globally"""
        query = """
            SELECT sc.*, COUNT(scu.id) as user_count,
                   COUNT(rr.id) as route_count,
                   COALESCE(g.display_name, g.title) as group_display_name,
                   mb.session_name as monitoring_bot_name,
                   fb.session_name as forwarding_bot_name
            FROM source_chats sc
            LEFT JOIN source_chat_users scu ON scu.source_chat_id = sc.id
            LEFT JOIN routing_rules rr ON rr.source_chat_id = sc.id AND rr.enabled = true
            LEFT JOIN groups g ON g.tg_chat_id = sc.source_chat_id
            LEFT JOIN bots mb ON mb.id = sc.default_monitoring_userbot_id
            LEFT JOIN bots fb ON fb.id = sc.default_forwarding_userbot_id
            GROUP BY sc.id, sc.display_name, g.display_name, g.title, mb.session_name, fb.session_name
            ORDER BY sc.created_at DESC
        """
        return await self.db.fetch(query)
    
    async def get_by_group(self, group_id: int) -> List[asyncpg.Record]:
        """Get all source chats routed to a specific group"""
        query = """
            SELECT sc.*, COUNT(scu.id) as user_count
            FROM source_chats sc
            LEFT JOIN source_chat_users scu ON scu.source_chat_id = sc.id
            LEFT JOIN routing_rules rr ON rr.source_chat_id = sc.id
            WHERE rr.target_group_id = $1 AND rr.enabled = true
            GROUP BY sc.id
            ORDER BY sc.created_at DESC
        """
        return await self.db.fetch(query, group_id)
    
    async def add_source(self, source_chat_id: int, source_type: str, 
                        name: str = None, title: str = None) -> asyncpg.Record:
        """Add a new global source chat"""
        query = """
            INSERT INTO source_chats (source_chat_id, source_type, name, title)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_chat_id) DO UPDATE SET
                source_type = $2, name = $3, title = $4, enabled = true
            RETURNING *
        """
        return await self.db.fetchrow(query, source_chat_id, source_type, name, title)
    
    async def add_routing_rule(
        self,
        source_id: int,
        target_group_id: int,
        monitoring_userbot_id: int = None,
        forwarding_userbot_id: int = None,
        allowed_chains: List[str] = None,
        forwarding_mode: str = "tokens",
        keyword_filters: List[str] = None,
        forward_summary: bool = False,
        forward_media: bool = True,
        forward_rewrite_rules: Optional[List[Dict[str, str]]] = None,
    ) -> asyncpg.Record:
        """Add a routing rule from source to target group with userbot assignments, blockchain filter, and forwarding mode."""
        if allowed_chains is None:
            allowed_chains = ["SOL", "BNB"]  # Default to both chains for new rules

        VALID_CHAINS = {"SOL", "BNB"}
        if not allowed_chains:
            raise ValueError("At least one blockchain must be selected")

        invalid_chains = set(allowed_chains) - VALID_CHAINS
        if invalid_chains:
            raise ValueError(f"Invalid blockchain identifiers: {invalid_chains}. Valid options: {VALID_CHAINS}")

        VALID_FORWARDING_MODES = {"tokens", "keywords", "everything"}
        forwarding_mode = (forwarding_mode or "tokens").lower()
        if forwarding_mode not in VALID_FORWARDING_MODES:
            raise ValueError(f"Invalid forwarding mode '{forwarding_mode}'. Valid options: {VALID_FORWARDING_MODES}")

        normalized_keywords = self._normalize_keywords(keyword_filters or [])
        normalized_rewrites = self._normalize_rewrite_rules(forward_rewrite_rules or [])

        query = """
            INSERT INTO routing_rules (
                source_chat_id,
                target_group_id,
                monitoring_userbot_id,
                forwarding_userbot_id,
                allowed_chains,
                forwarding_mode,
                keyword_filters,
                forward_summary,
                forward_media,
                forward_rewrite_rules
            )
            VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7::jsonb, $8, $9, $10::jsonb)
            ON CONFLICT (source_chat_id, target_group_id) DO UPDATE SET
                enabled = true,
                monitoring_userbot_id = EXCLUDED.monitoring_userbot_id,
                forwarding_userbot_id = EXCLUDED.forwarding_userbot_id,
                allowed_chains = EXCLUDED.allowed_chains,
                forwarding_mode = EXCLUDED.forwarding_mode,
                keyword_filters = EXCLUDED.keyword_filters,
                forward_summary = EXCLUDED.forward_summary,
                forward_media = EXCLUDED.forward_media,
                forward_rewrite_rules = EXCLUDED.forward_rewrite_rules
            RETURNING *
        """
        return await self.db.fetchrow(
            query,
            source_id,
            target_group_id,
            monitoring_userbot_id,
            forwarding_userbot_id,
            json.dumps(allowed_chains),
            forwarding_mode,
            json.dumps(normalized_keywords),
            forward_summary,
            forward_media,
            json.dumps(normalized_rewrites),
        )
    
    async def get_routing_rules(self, source_id: int) -> List[asyncpg.Record]:
        """Get all routing rules for a source with userbot assignments"""
        query = """
            SELECT rr.*,
                   COALESCE(g.display_name, g.title) as group_title,
                   g.tg_chat_id,
                   COALESCE(mb.display_name, mb.session_name) as monitoring_userbot_name,
                   COALESCE(fb.display_name, fb.session_name) as forwarding_userbot_name
            FROM routing_rules rr
            JOIN groups g ON g.id = rr.target_group_id
            LEFT JOIN bots mb ON mb.id = rr.monitoring_userbot_id
            LEFT JOIN bots fb ON fb.id = rr.forwarding_userbot_id
            WHERE rr.source_chat_id = $1
            ORDER BY rr.enabled DESC, COALESCE(g.display_name, g.title)
        """
        return await self.db.fetch(query, source_id)
    
    async def remove_routing_rule(self, source_id: int, target_group_id: int) -> bool:
        """Remove a routing rule"""
        query = "DELETE FROM routing_rules WHERE source_chat_id = $1 AND target_group_id = $2"
        result = await self.db.execute(query, source_id, target_group_id)
        return result.split()[-1] == '1'

    async def update_routing_rule_chains(self, rule_id: int, allowed_chains: List[str]) -> asyncpg.Record:
        """Update allowed_chains for a routing rule"""
        # Validate blockchain identifiers
        VALID_CHAINS = {"SOL", "BNB"}

        if not allowed_chains:
            raise ValueError("At least one blockchain must be selected")

        invalid_chains = set(allowed_chains) - VALID_CHAINS
        if invalid_chains:
            raise ValueError(f"Invalid blockchain identifiers: {invalid_chains}. Valid options: {VALID_CHAINS}")

        query = """
            UPDATE routing_rules
            SET allowed_chains = $1::jsonb
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, json.dumps(allowed_chains), rule_id)

    async def update_routing_rule_forwarding(
        self,
        rule_id: int,
        forwarding_mode: str,
        keyword_filters: Optional[List[str]] = None,
    ) -> asyncpg.Record:
        """Update forwarding mode and keywords for a routing rule."""
        VALID_FORWARDING_MODES = {"tokens", "keywords", "everything"}
        forwarding_mode = (forwarding_mode or "tokens").lower()
        if forwarding_mode not in VALID_FORWARDING_MODES:
            raise ValueError(f"Invalid forwarding mode '{forwarding_mode}'. Valid options: {VALID_FORWARDING_MODES}")

        normalized_keywords = self._normalize_keywords(keyword_filters or [])

        query = """
            UPDATE routing_rules
            SET forwarding_mode = $1,
                keyword_filters = $2::jsonb
            WHERE id = $3
            RETURNING *
        """
        return await self.db.fetchrow(query, forwarding_mode, json.dumps(normalized_keywords), rule_id)

    async def set_routing_rule_summary(self, rule_id: int, enabled: bool) -> asyncpg.Record:
        """Toggle summary reply for a routing rule."""
        query = """
            UPDATE routing_rules
            SET forward_summary = $1
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, enabled, rule_id)

    async def set_routing_rule_media(self, rule_id: int, enabled: bool) -> asyncpg.Record:
        """Toggle media forwarding for a routing rule."""
        query = """
            UPDATE routing_rules
            SET forward_media = $1
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, enabled, rule_id)

    async def set_routing_rule_rewrites(self, rule_id: int, rewrite_rules: List[Dict[str, str]]) -> asyncpg.Record:
        """Replace rewrite rules for a routing rule."""
        normalized = self._normalize_rewrite_rules(rewrite_rules)
        query = """
            UPDATE routing_rules
            SET forward_rewrite_rules = $1::jsonb
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, json.dumps(normalized), rule_id)

    async def remove_routing_rule_rewrite(self, rule_id: int, index: int) -> asyncpg.Record:
        """Remove a single rewrite rule by index."""
        query = """
            UPDATE routing_rules
            SET forward_rewrite_rules = (
                SELECT COALESCE(jsonb_agg(value), '[]'::jsonb)
                FROM (
                    SELECT value, row_number() OVER () AS idx
                    FROM jsonb_array_elements(forward_rewrite_rules) AS value
                ) sub
                WHERE sub.idx <> $1
            )
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, index + 1, rule_id)

    async def set_routing_rule_keywords(self, rule_id: int, keyword_filters: List[str]) -> asyncpg.Record:
        """Replace keyword filters for a routing rule."""
        normalized_keywords = self._normalize_keywords(keyword_filters)
        query = """
            UPDATE routing_rules
            SET keyword_filters = $1::jsonb
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, json.dumps(normalized_keywords), rule_id)

    async def remove_routing_rule_keyword(self, rule_id: int, keyword: str) -> asyncpg.Record:
        """Remove a single keyword from the routing rule."""
        keyword = keyword.strip().lower()
        if not keyword:
            raise ValueError("Keyword cannot be empty")

        query = """
            UPDATE routing_rules
            SET keyword_filters = (
                SELECT COALESCE(
                    jsonb_agg(value),
                    '[]'::jsonb
                )
                FROM jsonb_array_elements_text(keyword_filters) AS value
                WHERE lower(value) <> $1
            )
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, keyword, rule_id)

    async def get_routing_rule(self, rule_id: int) -> Optional[asyncpg.Record]:
        """Fetch a routing rule by id."""
        query = "SELECT * FROM routing_rules WHERE id = $1"
        return await self.db.fetchrow(query, rule_id)

    async def get_routing_rule_for_pair(self, source_id: int, group_id: int) -> Optional[asyncpg.Record]:
        """Fetch routing rule for a specific source / group pair."""
        query = """
            SELECT * FROM routing_rules
            WHERE source_chat_id = $1 AND target_group_id = $2
        """
        return await self.db.fetchrow(query, source_id, group_id)

    @staticmethod
    def _normalize_keywords(keyword_filters: List[str]) -> List[str]:
        """Normalize keyword filters to lowercase unique values."""
        seen = set()
        normalized: List[str] = []
        for keyword in keyword_filters:
            if not keyword:
                continue
            cleaned = keyword.strip().lower()
            if cleaned and cleaned not in seen:
                normalized.append(cleaned)
                seen.add(cleaned)
        return normalized

    @staticmethod
    def _normalize_rewrite_rules(rewrite_rules: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Normalize rewrite rules by stripping whitespace and removing empties."""
        normalized: List[Dict[str, str]] = []
        for rule in rewrite_rules:
            if not isinstance(rule, dict):
                continue
            source_value = (rule.get("source") or "").strip()
            target_value = (rule.get("target") or "").strip()
            if not source_value:
                continue
            normalized.append({"source": source_value, "target": target_value})
        return normalized

    async def toggle_enabled(self, source_id: int) -> bool:
        """Toggle source chat enabled status"""
        query = """
            UPDATE source_chats 
            SET enabled = NOT enabled 
            WHERE id = $1 
            RETURNING enabled
        """
        return await self.db.fetchval(query, source_id)
    
    async def remove_source(self, source_id: int) -> bool:
        """Remove a source chat"""
        query = "DELETE FROM source_chats WHERE id = $1"
        result = await self.db.execute(query, source_id)
        return result.split()[-1] == '1'
    
    async def get_sources_for_userbot(self, group_ids: List[int]) -> List[asyncpg.Record]:
        """Get enabled source chats for userbot monitoring"""
        if not group_ids:
            return []
        
        placeholders = ','.join(f'${i+1}' for i in range(len(group_ids)))
        query = f"""
            SELECT DISTINCT sc.source_chat_id, sc.source_type, sc.title, sc.group_id
            FROM source_chats sc
            WHERE sc.enabled = true AND sc.group_id IN ({placeholders})
        """
        return await self.db.fetch(query, *group_ids)
    
    async def add_user_to_source(self, source_id: int, user_id: int, 
                               username: str = None, first_name: str = None) -> asyncpg.Record:
        """Add user to source chat user filter"""
        query = """
            INSERT INTO source_chat_users (source_chat_id, user_id, username, first_name)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (source_chat_id, user_id) DO UPDATE SET
                username = $3, first_name = $4
            RETURNING *
        """
        return await self.db.fetchrow(query, source_id, user_id, username, first_name)
    
    async def remove_user_from_source(self, source_id: int, user_id: int) -> bool:
        """Remove user from source chat filter"""
        query = "DELETE FROM source_chat_users WHERE source_chat_id = $1 AND user_id = $2"
        result = await self.db.execute(query, source_id, user_id)
        return result.split()[-1] == '1'
    
    async def get_source_users(self, source_id: int) -> List[asyncpg.Record]:
        """Get all users for a source chat"""
        query = """
            SELECT * FROM source_chat_users 
            WHERE source_chat_id = $1 
            ORDER BY created_at DESC
        """
        return await self.db.fetch(query, source_id)
    
    async def is_user_allowed(self, source_chat_id: int, user_id: int) -> bool:
        """Check if user is allowed to trigger forwards from this source"""
        # Get the source type first
        source_query = "SELECT source_type FROM source_chats WHERE source_chat_id = $1"
        source_type = await self.db.fetchval(source_query, source_chat_id)
        
        if not source_type:
            return False
        
        # Channels allow all users
        if source_type == 'channel':
            return True
        
        # DMs: user is allowed if the source_chat_id matches their user_id
        # (DM sources have source_chat_id = user_id of the person in the DM)
        if source_type == 'dm':
            return source_chat_id == user_id
        
        # Groups: only allow specific users from source_chat_users table
        query = """
            SELECT EXISTS(
                SELECT 1 FROM source_chat_users scu
                JOIN source_chats sc ON sc.id = scu.source_chat_id
                WHERE sc.source_chat_id = $1 AND scu.user_id = $2
            )
        """
        return await self.db.fetchval(query, source_chat_id, user_id)
    
    async def get_source_by_chat_id(self, source_chat_id: int) -> Optional[asyncpg.Record]:
        """Get source chat by chat ID"""
        query = "SELECT * FROM source_chats WHERE source_chat_id = $1 AND enabled = true"
        return await self.db.fetchrow(query, source_chat_id)

    async def update_routing_rule_userbots(self, routing_rule_id: int,
                                          monitoring_userbot_id: int = None,
                                          forwarding_userbot_id: int = None) -> asyncpg.Record:
        """Update userbot assignments for a routing rule"""
        query = """
            UPDATE routing_rules
            SET monitoring_userbot_id = $2, forwarding_userbot_id = $3
            WHERE id = $1
            RETURNING *
        """
        return await self.db.fetchrow(query, routing_rule_id, monitoring_userbot_id, forwarding_userbot_id)

    async def get_rules_for_monitoring_userbot(self, userbot_id: int) -> List[asyncpg.Record]:
        """Get all routing rules assigned to a monitoring userbot"""
        query = """
            SELECT rr.*, sc.source_chat_id, sc.source_type, sc.name as source_name
            FROM routing_rules rr
            JOIN source_chats sc ON sc.id = rr.source_chat_id
            WHERE rr.monitoring_userbot_id = $1 AND rr.enabled = true
            ORDER BY sc.name, rr.created_at
        """
        return await self.db.fetch(query, userbot_id)

    async def update_source_bots(self, source_id: int,
                                monitoring_userbot_id: int = None,
                                forwarding_userbot_id: int = None) -> asyncpg.Record:
        """Update default monitor and forwarding bots for a source"""
        query = """
            UPDATE source_chats
            SET default_monitoring_userbot_id = $2, default_forwarding_userbot_id = $3
            WHERE id = $1
            RETURNING *
        """
        return await self.db.fetchrow(query, source_id, monitoring_userbot_id, forwarding_userbot_id)
