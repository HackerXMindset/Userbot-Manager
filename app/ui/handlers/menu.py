from aiogram import types
from typing import Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.ui.keyboards import Keyboards
from app.models import TokenModel, GroupModel, BotModel
from app.config import settings
import time

logger = logging.getLogger(__name__)

class MenuHandler:
    """Handler for main menu operations"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.token_model = TokenModel(db)
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)
        
        self.cache = {}
        self.cache_time = {}
    
    def is_fresh(self, key, seconds=300):
        """Check if cache entry is fresh (default 5 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    async def get_cached_dashboard_stats(self):
        """Get dashboard stats using caching"""
        if self.is_fresh("dashboard_stats"):
            return self.cache["dashboard_stats"]
        
        stats = await self.db.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM groups WHERE enabled = true) as groups_count,
                (SELECT COUNT(*) FROM bots WHERE kind = 'userbot' AND status = 'active') as userbots_count,
                (SELECT COUNT(*) FROM tokens_tracked WHERE status = 'active') as tokens_active,
                (SELECT COUNT(*) FROM token_call_history WHERE DATE(called_at) = CURRENT_DATE) as calls_today
        """)
        
        self.cache["dashboard_stats"] = dict(stats) if stats else {}
        self.cache_time["dashboard_stats"] = time.time()
        return self.cache["dashboard_stats"]
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_time.clear()
    
    async def get_status_text(self) -> str:
        """Generate status overview"""
        try:
            # Use cached dashboard stats
            result = await self.get_cached_dashboard_stats()
            
            return (
                f"📊 <b>System Status</b>\n"
                f"├ Groups: {result['groups_count']} active\n"
                f"├ Userbots: {result['userbots_count']} online\n"
                f"├ Tokens: {result['tokens_active']} tracking\n"
                f"├ Calls Today: {result['calls_today']}\n"
                f"└ Time: {settings.get_local_time().strftime('%H:%M IST')}"
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return "⚠️ Error loading status"
    
    async def show_main_menu(self, query: types.CallbackQuery):
        """Show the main menu"""
        try:
            status_text = await self.get_status_text()
            await query.message.edit_text(
                f"<b>🎛 Management Console</b>\n\n{status_text}",
                reply_markup=self.keyboards.main_menu()
            )
            await query.answer()
        except Exception as e:
            if "message is not modified" in str(e).lower():
                await query.answer()
            else:
                logger.error(f"Error showing main menu: {e}")
                await query.answer("❌ Error loading menu", show_alert=True)
    
    async def show_detailed_status(self, query: types.CallbackQuery):
        """Show detailed system status"""
        try:
            # Get detailed statistics
            token_stats = await self.token_model.get_token_stats()
            groups = await self.group_model.get_groups_with_stats()
            userbots = await self.bot_model.get_userbots_with_assignments()
            
            # Recent activity
            recent_calls = await self.db.fetchval("""
                SELECT COUNT(*) FROM token_call_history
                WHERE called_at > NOW() - INTERVAL '1 hour'
            """)
            
            text = (
                f"<b>📊 Detailed System Status</b>\n\n"
                f"<b>🔢 Statistics:</b>\n"
                f"├ Total Groups: {len(groups)}\n"
                f"├ Active Groups: {len([g for g in groups if g['enabled']])}\n"
                f"├ Total Userbots: {len(userbots)}\n"
                f"├ Active Userbots: {len([u for u in userbots if u['status'] == 'active'])}\n"
                f"├ Tracked Tokens: {token_stats.get('total_tokens', 0)}\n"
                f"├ Active Tokens: {token_stats.get('active_tokens', 0)}\n"
                f"└ Avg Multiplier: {(token_stats.get('avg_multiplier') or 0):.2f}x\n\n"
                f"<b>📈 Recent Activity (1h):</b>\n"
                f"└ Calls: {recent_calls}\n\n"
                f"<b>⏰ System Info:</b>\n"
                f"├ Timezone: {settings.timezone}\n"
                f"├ DEx Poll: {settings.dex_poll_secs}s\n"
                f"└ Current Time: {settings.get_local_time().strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:main")
            )
            
        except Exception as e:
            logger.error(f"Error showing detailed status: {e}")
            await query.message.edit_text(
                "❌ Error loading detailed status",
                reply_markup=self.keyboards.back_button("menu:main")
            )
    
