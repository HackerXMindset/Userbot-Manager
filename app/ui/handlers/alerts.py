from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
import logging

from app.ui.keyboards import Keyboards
from app.models import AlertModel

logger = logging.getLogger(__name__)

class AlertsHandler:
    """Handler for alerts configuration"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.alert_model = AlertModel(db)
    
    async def show_alerts_menu(self, query: types.CallbackQuery):
        """Display alerts configuration"""
        try:
            # Get current settings
            gains = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'gain_multipliers'"
            )
            drop = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'drop_percentage'"
            )
            
            current_gains = gains or [5, 10, 15]
            drop_pct = float(drop) if drop else 0.70
            
            # Get alert stats
            alerts_today = await self.db.fetchval("""
                SELECT COUNT(*) FROM alerts 
                WHERE triggered_at > CURRENT_DATE
            """)
            
            text = (
                f"<b>🚨 Alerts Configuration</b>\n\n"
                f"<b>Current Settings:</b>\n"
                f"├ Gain Thresholds: {', '.join([f'{g}x' for g in current_gains])}\n"
                f"├ Drop Threshold: {drop_pct*100:.0f}%\n"
                f"└ Alerts Today: {alerts_today}\n\n"
                f"<b>How it works:</b>\n"
                f"• Post /pnl when token hits gain thresholds\n"
                f"• Stop tracking globally at {drop_pct*100:.0f}% drop\n"
                f"• Each threshold fires once per token"
            )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.alerts_config(current_gains, drop_pct)
            )
            
        except Exception as e:
            logger.error(f"Error showing alerts menu: {e}")
            await query.answer("❌ Error loading alerts configuration")
    
    async def handle_alerts_action(self, query: types.CallbackQuery):
        """Handle alerts-related callbacks"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'gains':
            await self.show_gains_editor(query)
        elif action == 'drop':
            await self.show_drop_editor(query)
        elif action == 'add_gain':
            await self.show_add_gain(query)
        elif action == 'remove_gain':
            await self.show_remove_gain(query)
        elif action == 'set_drop':
            await self.show_set_drop(query)
        elif action == 'per_group':
            await self.show_per_group_alerts(query)
    
    async def show_gains_editor(self, query: types.CallbackQuery):
        """Show gain thresholds editor"""
        try:
            gains = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'gain_multipliers'"
            )
            current_gains = gains or [5, 10, 15]
            
            text = (
                f"<b>📈 Gain Thresholds</b>\n\n"
                f"Current: {', '.join([f'{g}x' for g in current_gains])}\n\n"
                f"These are the multipliers that trigger alerts.\n"
                f"Each threshold fires once per token."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Add Threshold", callback_data="alerts:add_gain"),
                    InlineKeyboardButton(text="➖ Remove Threshold", callback_data="alerts:remove_gain")
                ],
                [
                    InlineKeyboardButton(text="🔄 Reset to Default", callback_data="alerts:reset_gains")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:alerts")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing gains editor: {e}")
            await query.answer("❌ Error loading gains settings")
    
    async def show_drop_editor(self, query: types.CallbackQuery):
        """Show drop threshold editor"""
        try:
            drop = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'drop_percentage'"
            )
            drop_pct = float(drop) if drop else 0.70
            
            text = (
                f"<b>📉 Drop Threshold</b>\n\n"
                f"Current: {drop_pct*100:.0f}%\n\n"
                f"When a token drops by this percentage from its peak,\n"
                f"it will be stopped globally across all groups."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="60%", callback_data="drop:set:0.60"),
                    InlineKeyboardButton(text="70%", callback_data="drop:set:0.70"),
                    InlineKeyboardButton(text="80%", callback_data="drop:set:0.80")
                ],
                [
                    InlineKeyboardButton(text="🔧 Custom", callback_data="drop:custom")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:alerts")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing drop editor: {e}")
            await query.answer("❌ Error loading drop settings")
    
    async def show_recent_alerts(self, query: types.CallbackQuery):
        """Show recent alerts"""
        try:
            recent_alerts = await self.alert_model.get_recent_alerts(hours=24)
            
            text = "<b>🚨 Recent Alerts (24h)</b>\n\n"
            
            if not recent_alerts:
                text += "No alerts in the last 24 hours."
            else:
                for alert in recent_alerts[:10]:
                    address_short = f"{alert['address'][:8]}...{alert['address'][-8:]}"
                    multiplier = alert['multiplier']
                    time_str = alert['triggered_at'].strftime('%H:%M')
                    text += f"• {time_str}: {address_short} hit {multiplier}x\n"
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:alerts")
            )
            
        except Exception as e:
            logger.error(f"Error showing recent alerts: {e}")
            await query.answer("❌ Error loading recent alerts")
    
    async def update_gain_thresholds(self, thresholds: List[int]):
        """Update gain thresholds in database"""
        try:
            await self.db.execute(
                "INSERT INTO settings (key, value) VALUES ('gain_multipliers', $1) ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()",
                thresholds
            )
        except Exception as e:
            logger.error(f"Error updating gain thresholds: {e}")
            raise
    
    async def update_drop_threshold(self, percentage: float):
        """Update drop threshold in database"""
        try:
            await self.db.execute(
                "INSERT INTO settings (key, value) VALUES ('drop_percentage', $1) ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()",
                percentage
            )
        except Exception as e:
            logger.error(f"Error updating drop threshold: {e}")
            raise
