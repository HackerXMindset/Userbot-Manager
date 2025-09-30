from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.models import TargetModel

logger = logging.getLogger(__name__)

class AlertsHandler:
    """Handles the display of the global alerts dashboard."""
    
    def __init__(self, db, keyboards):
        self.db = db
        self.keyboards = keyboards
        self.target_model = TargetModel(db)
        logger.info("AlertsHandler initialized.")

    async def show_alerts_menu(self, query: types.CallbackQuery):
        """Show the new alerts dashboard with global statistics."""
        try:
            logger.debug("Fetching global alert stats...")
            stats = await self.target_model.get_global_alert_stats()
            logger.debug(f"Stats received from DB: {stats}")

            total_targets = stats.get('total_targets', 0)
            enabled_targets = stats.get('enabled_targets', 0)
            
            enabled_percent = (enabled_targets / total_targets * 100) if total_targets > 0 else 0

            pnl_mode = stats.get('pnl_mode_enabled', 0)
            threshold_mode = stats.get('threshold_mode_enabled', 0)
            sensitivity_mode = stats.get('sensitivity_mode_enabled', 0)
            
            avg_sensitivity = stats.get('avg_sensitivity')
            avg_sensitivity_percent = (avg_sensitivity * 100) if avg_sensitivity else 0

            logger.debug(f"Formatted stats: total={total_targets}, enabled={enabled_targets}, pnl={pnl_mode}, thresh={threshold_mode}, sens={sensitivity_mode}, avg_sens={avg_sensitivity_percent}")

            # Build visual progress bar
            enabled_bar = "█" * int(enabled_percent / 10) + "░" * (10 - int(enabled_percent / 10))

            # Calculate next alert multiplier
            next_alert_mult = 1 + (avg_sensitivity if avg_sensitivity else 0.5)

            text = (
                f"🚨 Alert System\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"ACTIVE       <b>{enabled_targets} / {total_targets}</b> targets\n"
                f"COVERAGE     {enabled_bar}  <b>{enabled_percent:.0f}%</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"MODES IN USE\n\n"
                f"  📈  {pnl_mode}  PNL\n"
                f"  🎚️  {threshold_mode}  Threshold\n"
                f"  ⚡  {sensitivity_mode}  Sensitivity\n\n"
                f"━━━━━━━━━━━━━━━━━━━━\n\n"
                f"AVG SENSITIVITY     <b>{avg_sensitivity_percent:.0f}%</b>\n"
                f"Next alert at       <b>{next_alert_mult:.2f}x</b>\n\n"
                f"━━━━━━━━━━━━━━━━━━━━"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="⚙️ Manage Per-Target Alerts", callback_data="targets:menu")
                ],
                [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data="alerts:menu")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            
        except Exception as e:
            logger.error(f"Error showing alerts dashboard: {e}", exc_info=True)
            await query.message.edit_text(
                "❌ Error loading alerts dashboard.",
                reply_markup=self.keyboards.back_button("menu:main")
            )

    async def handle_alerts_action(self, query: types.CallbackQuery):
        """Handle alerts configuration actions."""
        try:
            action = query.data.split(':', 1)[1]
            
            if action == "menu":
                await self.show_alerts_menu(query)
            else:
                await query.answer("❌ Unknown action")
                
        except Exception as e:
            logger.error(f"Error handling alerts action: {e}")
            await query.answer("❌ Error processing action")