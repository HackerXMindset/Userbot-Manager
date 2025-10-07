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
