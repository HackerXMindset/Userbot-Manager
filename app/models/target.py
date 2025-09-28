from typing import Dict, Any, Optional, List
from .base import BaseModel
import asyncpg
import json
import logging

logger = logging.getLogger(__name__)

class TargetModel(BaseModel):
    """Model for managing target records with alert configuration"""

    def __init__(self, db):
        super().__init__(db)
        self.table_name = "targets"

    async def get_by_group_id(self, group_id: int) -> List[asyncpg.Record]:
        """Get all targets for a group"""
        query = "SELECT * FROM targets WHERE group_id = $1 ORDER BY id"
        return await self.db.fetch(query, group_id)

    async def get_by_dest_chat_id(self, dest_chat_id: int) -> Optional[asyncpg.Record]:
        """Get target by destination chat ID"""
        query = "SELECT * FROM targets WHERE dest_chat_id = $1"
        return await self.db.fetchrow(query, dest_chat_id)

    async def get_targets_with_group_info(self) -> List[asyncpg.Record]:
        """Get targets with group information"""
        query = """
            SELECT t.*, g.display_name as group_display_name, g.title as group_title, g.tg_chat_id as group_tg_chat_id
            FROM targets t
            LEFT JOIN groups g ON g.id = t.group_id
            ORDER BY g.display_name, t.dest_chat_id
        """
        return await self.db.fetch(query)

    async def get_targets_for_source_group(self, source_group_id: int, alerts_enabled_only: bool = False) -> List[asyncpg.Record]:
        """Get targets for a source group, optionally filtering by alerts enabled"""
        where_clause = "WHERE group_id = $1"
        if alerts_enabled_only:
            where_clause += " AND alerts_enabled = true"

        query = f"""
            SELECT * FROM targets
            {where_clause}
            ORDER BY id
        """
        return await self.db.fetch(query, source_group_id)

    # Alert Configuration Getters/Setters

    def parse_alert_modes(self, target_record: asyncpg.Record) -> Dict[str, bool]:
        """Parse alert modes from JSONB with defaults"""
        defaults = {
            "pnl": True,
            "dynamic": True,
            "threshold": True,
            "sensitivity": True
        }

        try:
            if target_record and 'alerts_modes' in target_record and target_record['alerts_modes']:
                modes = target_record['alerts_modes']
                if isinstance(modes, str):
                    modes = json.loads(modes)

                # Merge with defaults to ensure all keys exist
                result = defaults.copy()
                if isinstance(modes, dict):
                    result.update(modes)
                return result
        except (json.JSONDecodeError, TypeError) as e:
            target_id = target_record['id'] if target_record and 'id' in target_record else 'unknown'
            logger.warning(f"Failed to parse alerts_modes for target {target_id}: {e}")

        return defaults

    def parse_alert_thresholds(self, target_record: asyncpg.Record) -> List[float]:
        """Parse alert thresholds from JSONB with defaults"""
        defaults = [2, 7, 25]

        try:
            if target_record and 'alerts_thresholds' in target_record and target_record['alerts_thresholds']:
                thresholds = target_record['alerts_thresholds']
                if isinstance(thresholds, str):
                    thresholds = json.loads(thresholds)

                if isinstance(thresholds, list) and all(isinstance(x, (int, float)) for x in thresholds):
                    return sorted([float(x) for x in thresholds])
        except (json.JSONDecodeError, TypeError) as e:
            target_id = target_record['id'] if target_record and 'id' in target_record else 'unknown'
            logger.warning(f"Failed to parse alerts_thresholds for target {target_id}: {e}")

        return defaults

    def get_alert_sensitivity_percent(self, target_record: asyncpg.Record) -> float:
        """Get alert sensitivity percentage with default"""
        if target_record and 'alerts_sensitivity_percent' in target_record and target_record['alerts_sensitivity_percent'] is not None:
            return float(target_record['alerts_sensitivity_percent'])
        return 0.50  # 50% default

    async def update_alerts_enabled(self, target_id: int, enabled: bool) -> Optional[asyncpg.Record]:
        """Toggle alerts enabled for target"""
        query = """
            UPDATE targets
            SET alerts_enabled = $1
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, enabled, target_id)

    async def update_alert_modes(self, target_id: int, modes: Dict[str, bool]) -> Optional[asyncpg.Record]:
        """Update alert modes for target"""
        query = """
            UPDATE targets
            SET alerts_modes = $1::jsonb
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, json.dumps(modes), target_id)

    async def update_alert_thresholds(self, target_id: int, thresholds: List[float]) -> Optional[asyncpg.Record]:
        """Update alert thresholds for target"""
        # Ensure sorted and deduplicated
        unique_thresholds = sorted(list(set(thresholds)))

        query = """
            UPDATE targets
            SET alerts_thresholds = $1::jsonb
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, json.dumps(unique_thresholds), target_id)

    async def update_alert_sensitivity(self, target_id: int, sensitivity_percent: float) -> Optional[asyncpg.Record]:
        """Update alert sensitivity percentage for target"""
        # Clamp to reasonable range
        sensitivity_percent = max(0.05, min(5.0, sensitivity_percent))

        query = """
            UPDATE targets
            SET alerts_sensitivity_percent = $1
            WHERE id = $2
            RETURNING *
        """
        return await self.db.fetchrow(query, sensitivity_percent, target_id)

    async def create_target(self, group_id: int, dest_chat_id: int, **kwargs) -> asyncpg.Record:
        """Create a new target with default alert settings"""
        data = {
            'group_id': group_id,
            'dest_chat_id': dest_chat_id,
            'alerts_enabled': kwargs.get('alerts_enabled', True),
            'alerts_modes': json.dumps(kwargs.get('alerts_modes', {
                "pnl": True,
                "dynamic": True,
                "threshold": True,
                "sensitivity": True
            })),
            'alerts_thresholds': json.dumps(kwargs.get('alerts_thresholds', [2, 7, 25])),
            'alerts_sensitivity_percent': kwargs.get('alerts_sensitivity_percent', 0.50)
        }

        # Add any other provided fields
        for key, value in kwargs.items():
            if key not in data:
                data[key] = value

        return await self.create(data)

    async def get_alert_summary(self, target_id: int) -> Dict[str, Any]:
        """Get formatted alert summary for a target"""
        target = await self.get_by_id(target_id)
        if not target:
            return {}

        modes = self.parse_alert_modes(target)
        thresholds = self.parse_alert_thresholds(target)
        sensitivity = self.get_alert_sensitivity_percent(target)

        # Build status indicators
        mode_indicators = []
        for mode, enabled in modes.items():
            if enabled:
                mode_indicators.append(f"{mode}✅")
            else:
                mode_indicators.append(f"{mode}❌")

        threshold_text = ",".join([f"{x}" for x in thresholds])

        return {
            'enabled': target['alerts_enabled'],
            'modes': modes,
            'thresholds': thresholds,
            'sensitivity_percent': sensitivity,
            'summary_text': f"Alerts: {'ON' if target['alerts_enabled'] else 'OFF'} ({' '.join(mode_indicators)}) S={sensitivity*100:.0f}% T=[{threshold_text}]"
        }

    async def get_global_alert_stats(self) -> Dict[str, Any]:
        """Get global statistics for target alert configurations."""
        query = """
            SELECT
                COUNT(*) AS total_targets,
                COUNT(*) FILTER (WHERE alerts_enabled = true) AS enabled_targets,
                COUNT(*) FILTER (WHERE (alerts_modes->>'pnl')::boolean = true AND alerts_enabled = true) AS pnl_mode_enabled,
                COUNT(*) FILTER (WHERE (alerts_modes->>'dynamic')::boolean = true AND alerts_enabled = true) AS dynamic_mode_enabled,
                COUNT(*) FILTER (WHERE (alerts_modes->>'threshold')::boolean = true AND alerts_enabled = true) AS threshold_mode_enabled,
                COUNT(*) FILTER (WHERE (alerts_modes->>'sensitivity')::boolean = true AND alerts_enabled = true) AS sensitivity_mode_enabled,
                AVG(alerts_sensitivity_percent) FILTER (WHERE (alerts_modes->>'sensitivity')::boolean = true AND alerts_enabled = true) AS avg_sensitivity
            FROM
                targets;
        """
        stats = await self.db.fetchrow(query)
        return dict(stats) if stats else {}