from aiogram import types
from typing import Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.ui.keyboards import Keyboards
from app.models import TokenModel, GroupModel, BotModel
from app.config import settings

logger = logging.getLogger(__name__)

class MenuHandler:
    """Handler for main menu operations"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.token_model = TokenModel(db)
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)
    
    async def get_status_text(self) -> str:
        """Generate status overview"""
        try:
            # Get counts from database
            groups_count = await self.db.fetchval("SELECT COUNT(*) FROM groups WHERE enabled = true")
            userbots_count = await self.db.fetchval("SELECT COUNT(*) FROM bots WHERE kind = 'userbot' AND status = 'active'")
            tokens_active = await self.db.fetchval("SELECT COUNT(*) FROM tokens_tracked WHERE status = 'active'")
            calls_today = await self.db.fetchval("""
                SELECT COUNT(*) FROM calls 
                WHERE sent_at > CURRENT_DATE 
                AND status = 'sent'
            """)
            
            return (
                f"📊 <b>System Status</b>\n"
                f"├ Groups: {groups_count} active\n"
                f"├ Userbots: {userbots_count} online\n"
                f"├ Tokens: {tokens_active} tracking\n"
                f"├ Calls Today: {calls_today}\n"
                f"└ Time: {settings.get_local_time().strftime('%H:%M IST')}"
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return "⚠️ Error loading status"
    
    async def show_main_menu(self, query: types.CallbackQuery):
        """Show the main menu"""
        status_text = await self.get_status_text()
        await query.message.edit_text(
            f"<b>🎛 Management Console</b>\n\n{status_text}",
            reply_markup=self.keyboards.main_menu()
        )
    
    async def show_detailed_status(self, query: types.CallbackQuery):
        """Show detailed system status"""
        try:
            # Get detailed statistics
            token_stats = await self.token_model.get_token_stats()
            groups = await self.group_model.get_groups_with_stats()
            userbots = await self.bot_model.get_userbots_with_assignments()
            
            # Recent activity
            recent_calls = await self.db.fetchval("""
                SELECT COUNT(*) FROM calls 
                WHERE created_at > NOW() - INTERVAL '1 hour'
            """)
            
            recent_alerts = await self.db.fetchval("""
                SELECT COUNT(*) FROM alerts 
                WHERE triggered_at > NOW() - INTERVAL '1 hour'
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
                f"├ Calls: {recent_calls}\n"
                f"└ Alerts: {recent_alerts}\n\n"
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
    
    async def show_tracking_menu(self, query: types.CallbackQuery):
        """Show token tracking overview"""
        try:
            # Get top performing tokens
            top_tokens = await self.token_model.get_performance_tokens(limit=5)
            token_stats = await self.token_model.get_token_stats()
            
            text = (
                f"<b>📈 Token Tracking</b>\n\n"
                f"<b>📊 Overview:</b>\n"
                f"├ Total: {token_stats.get('total_tokens', 0)}\n"
                f"├ Active: {token_stats.get('active_tokens', 0)}\n"
                f"├ Stopped: {token_stats.get('stopped_tokens', 0)}\n"
                f"└ Avg Performance: {(token_stats.get('avg_multiplier') or 0):.2f}x\n\n"
            )
            
            if top_tokens:
                text += "<b>🏆 Top Performers:</b>\n"
                for i, token in enumerate(top_tokens, 1):
                    multiplier = token['last_mc'] / token['first_seen_mc'] if token['first_seen_mc'] > 0 else 1
                    address_short = f"{token['address'][:8]}...{token['address'][-8:]}"
                    text += f"{i}. {address_short}: {multiplier:.2f}x\n"
            else:
                text += "No tokens being tracked yet."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:tracking"),
                    InlineKeyboardButton(text="🧹 Cleanup", callback_data="tracking:cleanup")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing tracking menu: {e}")
            await query.message.edit_text(
                "❌ Error loading tracking data",
                reply_markup=self.keyboards.back_button("menu:main")
            )
    
    async def show_settings_menu(self, query: types.CallbackQuery):
        """Show system settings"""
        try:
            # Get current settings from database
            settings_data = await self.db.fetch("SELECT key, value FROM settings")
            settings_dict = {s['key']: s['value'] for s in settings_data}
            
            text = (
                f"<b>⚙️ System Settings</b>\n\n"
                f"<b>📊 Alerts:</b>\n"
                f"├ Gain Thresholds: {settings_dict.get('gain_multipliers', [])}\n"
                f"└ Drop Threshold: {float(settings_dict.get('drop_percentage', 0.7)) * 100:.0f}%\n\n"
                f"<b>🔧 System:</b>\n"
                f"├ Timezone: {settings_dict.get('timezone', 'Asia/Kolkata')}\n"
                f"├ DEx Poll Rate: {settings_dict.get('dex_poll_secs', 5)}s\n"
                f"└ Admin ID: {settings_dict.get('admin_id', 'Not set')}\n\n"
                f"<b>📱 Telegram API:</b>\n"
                f"├ API ID: {settings.api_id}\n"
                f"└ API Hash: {'*' * 20}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚨 Alert Settings", callback_data="menu:alerts"),
                    InlineKeyboardButton(text="🌍 Timezone", callback_data="settings:timezone")
                ],
                [
                    InlineKeyboardButton(text="📊 DEx Settings", callback_data="settings:dex"),
                    InlineKeyboardButton(text="🔧 Advanced", callback_data="settings:advanced")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing settings: {e}")
            await query.message.edit_text(
                "❌ Error loading settings",
                reply_markup=self.keyboards.back_button("menu:main")
            )