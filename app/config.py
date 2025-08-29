import os
from typing import Optional, List, Dict, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import pytz
from datetime import datetime

load_dotenv()

class Settings(BaseSettings):
    # Telegram
    admin_telegram_id: int = Field(..., env='ADMIN_TELEGRAM_ID')
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
    
    # Scanner Bot
    scanner_bot_id: Optional[int] = Field(default=None, env='SCANNER_BOT_ID')
    scanner_button_text: str = Field(default='🛰 Just Scanning', env='SCANNER_BUTTON_TEXT')
    
    # Solana
    solana_pattern: str = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
    
    @field_validator('admin_telegram_id')
    @classmethod
    def validate_admin_id(cls, v):
        if v <= 0:
            raise ValueError('Invalid admin Telegram ID')
        return v
    
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