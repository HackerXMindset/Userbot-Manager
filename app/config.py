import json
import logging
import os
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

from app.gain_alert_templates import (
    DEFAULT_GAIN_ALERT_TEMPLATE,
    normalise_template,
    missing_required_placeholders,
)
import pytz
from datetime import datetime

load_dotenv()

class Settings(BaseSettings):
    # Telegram
    admin_telegram_ids: str = Field(..., env='ADMIN_TELEGRAM_IDS')
    mgmt_bot_token: str = Field(..., env='MGMT_BOT_TOKEN')
    api_id: int = Field(..., env='API_ID')
    api_hash: str = Field(..., env='API_HASH')
    
    # Database
    supabase_pooler_url: str = Field(..., env='SUPABASE_POOLER_URL')
    db_pool_min: int = Field(default=2, env='DB_POOL_MIN')
    db_pool_max: int = Field(default=10, env='DB_POOL_MAX')
    
    # Timezone
    timezone: str = Field(default='Asia/Kolkata', env='TIMEZONE')
    
    # DexScreener
    dex_poll_secs: int = Field(default=5, env='DEX_POLL_SECS')
    dex_timeout: int = Field(default=10, env='DEX_TIMEOUT')
    dex_max_retries: int = Field(default=3, env='DEX_MAX_RETRIES')

    # Rust integration
    rust_analysis_base_url: str = Field(default='http://127.0.0.1:8080', env='RUST_ANALYSIS_BASE_URL')

    # Scanner Bot
    scanner_bot_id: Optional[int] = Field(default=None, env='SCANNER_BOT_ID')
    scanner_button_text: str = Field(default='🛰 Just Scanning', env='SCANNER_BUTTON_TEXT')
    
    # Solana
    solana_pattern: str = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'

    # BNB/BSC (Ethereum-compatible addresses)
    bnb_pattern: str = r'0x[a-fA-F0-9]{40}\b'
    
    @field_validator('admin_telegram_ids')
    @classmethod
    def validate_admin_ids(cls, v):
        if not isinstance(v, str):
            raise ValueError('Admin IDs must be a string')
        
        # Parse comma-separated values
        ids = [int(id_str.strip()) for id_str in v.split(',') if id_str.strip()]
        
        # Validate each ID
        for admin_id in ids:
            if admin_id <= 0:
                raise ValueError(f'Invalid admin Telegram ID: {admin_id}')
        
        if not ids:
            raise ValueError('At least one admin ID is required')
        
        return v  # Return the original string
    
    @property
    def admin_telegram_ids_list(self) -> List[int]:
        """Get admin IDs as a list of integers"""
        return [int(id_str.strip()) for id_str in self.admin_telegram_ids.split(',') if id_str.strip()]
    
    @property
    def tz(self):
        return pytz.timezone(self.timezone)
    
    def get_local_time(self) -> datetime:
        return datetime.now(self.tz)
    
    model_config = {
        "env_file": ".env",
        "case_sensitive": False,
        "extra": "ignore"
    }

settings = Settings()

# Gain alert system defaults (fallback if DB unavailable)
GAIN_THRESHOLD_DEFAULT_PCT = 0.30  # 30% gain triggers alert
DROP_THRESHOLD_DEFAULT_PCT = 0.70  # 70% of first_seen_mc triggers stop
DROP_FLOOR_MC_DEFAULT = 8000.0     # $8,000 absolute floor

GAIN_ALERT_TEMPLATE_KEY = "gain_alert_template"
GLOBAL_CHART_THRESHOLD_KEY = "chart_global_mc_threshold"
GLOBAL_CHART_BOT_ID_KEY = "chart_global_bot_id"
DEFAULT_GLOBAL_CHART_THRESHOLD = Decimal("100000")

# Market cap validation bounds
MIN_VALID_MARKET_CAP = 1000.0       # $1K minimum
MAX_VALID_MARKET_CAP = 1_000_000_000_000.0  # $1T maximum

# In-memory cache for global gain alert template
_GAIN_TEMPLATE_CACHE: Optional[str] = None

async def get_gain_alert_settings():
    """
    Load gain alert settings from database with fallback to defaults.
    Returns dict with: gain_threshold_pct, drop_threshold_pct, drop_floor_mc
    """
    from app.db import db

    try:
        # Fetch settings from DB
        gain_threshold = await db.fetchval(
            "SELECT value FROM settings WHERE key = $1",
            'gain_threshold_pct'
        )
        drop_threshold = await db.fetchval(
            "SELECT value FROM settings WHERE key = $1",
            'drop_threshold_pct'
        )
        drop_floor = await db.fetchval(
            "SELECT value FROM settings WHERE key = $1",
            'drop_floor_mc'
        )

        return {
            'gain_threshold_pct': float(gain_threshold) if gain_threshold else GAIN_THRESHOLD_DEFAULT_PCT,
            'drop_threshold_pct': float(drop_threshold) if drop_threshold else DROP_THRESHOLD_DEFAULT_PCT,
            'drop_floor_mc': float(drop_floor) if drop_floor else DROP_FLOOR_MC_DEFAULT,
        }
    except Exception as e:
        # Fallback to defaults if DB unavailable
        logging.warning(f"Failed to load gain alert settings from DB, using defaults: {e}")
        return {
            'gain_threshold_pct': GAIN_THRESHOLD_DEFAULT_PCT,
            'drop_threshold_pct': DROP_THRESHOLD_DEFAULT_PCT,
            'drop_floor_mc': DROP_FLOOR_MC_DEFAULT,
        }


async def get_gain_alert_template_text() -> str:
    """
    Load the global gain alert template, falling back to the default string
    when unset, invalid, or on database errors.
    """
    global _GAIN_TEMPLATE_CACHE

    if _GAIN_TEMPLATE_CACHE is not None:
        return _GAIN_TEMPLATE_CACHE

    from app.db import db

    try:
        template = await db.fetchval(
            "SELECT value FROM settings WHERE key = $1",
            GAIN_ALERT_TEMPLATE_KEY,
        )

        if isinstance(template, str) and template.startswith("\"") and template.endswith("\""):
            try:
                template = json.loads(template)
            except json.JSONDecodeError:
                logging.debug("Gain alert template stored with extra quotes; falling back to raw string.")

        template = normalise_template(template) if template else ""
        if not template:
            return DEFAULT_GAIN_ALERT_TEMPLATE

        _GAIN_TEMPLATE_CACHE = template
        return template
    except Exception as exc:
        logging.warning(
            "Failed to load gain alert template from DB (%s). Using default.",
            exc,
        )
        _GAIN_TEMPLATE_CACHE = DEFAULT_GAIN_ALERT_TEMPLATE
        return _GAIN_TEMPLATE_CACHE


async def set_gain_alert_template_text(template: str) -> None:
    """
    Persist the global gain alert template string.

    Args:
        template: Template text to store. If blank, the default template is written.
    """
    from app.db import db

    cleaned = normalise_template(template)
    if not cleaned:
        cleaned = DEFAULT_GAIN_ALERT_TEMPLATE

    await db.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, to_jsonb($2::text))
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """,
        GAIN_ALERT_TEMPLATE_KEY,
        cleaned,
    )

    global _GAIN_TEMPLATE_CACHE
    _GAIN_TEMPLATE_CACHE = cleaned


async def get_global_chart_settings() -> Dict[str, Any]:
    """Fetch global chart configuration defaults with safe fallbacks."""
    from app.db import db

    defaults = {
        "chart_threshold_override": None,
        "chart_threshold_default": DEFAULT_GLOBAL_CHART_THRESHOLD,
        "chart_bot_id": None,
    }

    try:
        threshold_raw = await db.fetchval(
            "SELECT value FROM settings WHERE key = $1",
            GLOBAL_CHART_THRESHOLD_KEY,
        )
        bot_id_raw = await db.fetchval(
            "SELECT value FROM settings WHERE key = $1",
            GLOBAL_CHART_BOT_ID_KEY,
        )
    except Exception as exc:
        logging.warning(
            "Failed to load global chart settings from DB (%s). Using defaults.",
            exc,
        )
        return defaults

    if threshold_raw is not None:
        try:
            defaults["chart_threshold_override"] = Decimal(str(threshold_raw))
        except (InvalidOperation, TypeError, ValueError):
            logging.warning(
                "Invalid global chart threshold value %s; ignoring.",
                threshold_raw,
            )

    if bot_id_raw is not None:
        try:
            defaults["chart_bot_id"] = int(bot_id_raw)
        except (TypeError, ValueError):
            logging.warning(
                "Invalid global chart bot id %s; ignoring.",
                bot_id_raw,
            )

    return defaults


async def set_global_chart_threshold(value: Optional[Decimal]) -> None:
    """Persist or clear the global chart market cap threshold override."""
    from app.db import db

    if value is None:
        await db.execute(
            "DELETE FROM settings WHERE key = $1",
            GLOBAL_CHART_THRESHOLD_KEY,
        )
        return

    numeric_str = str(float(value))
    await db.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        GLOBAL_CHART_THRESHOLD_KEY,
        numeric_str,
    )


async def set_global_chart_bot_id(bot_id: Optional[int]) -> None:
    """Persist or clear the global chart bot identifier."""
    from app.db import db

    if bot_id is None:
        await db.execute(
            "DELETE FROM settings WHERE key = $1",
            GLOBAL_CHART_BOT_ID_KEY,
        )
        return

    bot_id_str = str(int(bot_id))
    await db.execute(
        """
        INSERT INTO settings (key, value)
        VALUES ($1, $2)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """,
        GLOBAL_CHART_BOT_ID_KEY,
        bot_id_str,
    )


def clear_gain_alert_template_cache() -> None:
    """Clear the in-memory cache for the gain alert template."""
    global _GAIN_TEMPLATE_CACHE
    _GAIN_TEMPLATE_CACHE = None
