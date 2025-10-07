from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.models import TargetModel

logger = logging.getLogger(__name__)

class AlertsHandler:
    """Handles the display of the global alerts dashboard - REDESIGNED for clean UI"""

    def __init__(self, db, keyboards):
        self.db = db
        self.keyboards = keyboards
        self.target_model = TargetModel(db)
        logger.info("AlertsHandler initialized.")

    async def show_alerts_menu(self, query: types.CallbackQuery):
        """Show simplified alerts dashboard with key metrics"""
        try:
            logger.debug("Fetching global alert stats...")
            stats = await self.target_model.get_global_alert_stats()

            total_targets = stats.get('total_targets', 0)
            enabled_targets = stats.get('enabled_targets', 0)

            # Mode usage counts
            pnl_count = stats.get('pnl_mode_enabled', 0)
            threshold_count = stats.get('threshold_mode_enabled', 0)
            sensitivity_count = stats.get('sensitivity_mode_enabled', 0)
            dynamic_count = stats.get('dynamic_mode_enabled', 0)

            # Calculate coverage percentage
            coverage_pct = (enabled_targets / total_targets * 100) if total_targets > 0 else 0

            text = (
                f"🚨 <b>Alert System</b>\n\n"
                f"<b>STATUS</b>\n"
                f"🟢 {enabled_targets}/{total_targets} targets active ({coverage_pct:.0f}%)\n\n"
                f"<b>USAGE</b>\n"
                f"📈 PNL          {pnl_count} targets\n"
                f"🎚️ Threshold    {threshold_count} targets\n"
                f"⚡ Sensitivity  {sensitivity_count} targets\n"
                f"🔄 Dynamic      {dynamic_count} targets"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Configure Targets", callback_data="targets:select_for_alerts")],
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="alerts:menu")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])

            try:
                await query.message.edit_text(text, reply_markup=keyboard, parse_mode='HTML')
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    # Message content is identical, just answer the callback
                    await query.answer()
                else:
                    raise edit_error

        except Exception as e:
            logger.error(f"Error showing alerts dashboard: {e}", exc_info=True)
            await query.message.edit_text(
                "❌ Error loading alerts dashboard.",
                reply_markup=self.keyboards.back_button("menu:main")
            )

    async def handle_alerts_action(self, query: types.CallbackQuery):
        """Handle alerts configuration actions"""
        try:
            action = query.data.split(':', 1)[1]

            if action == "menu":
                await self.show_alerts_menu(query)
            else:
                await query.answer("❌ Unknown action")

        except Exception as e:
            logger.error(f"Error handling alerts action: {e}")
            await query.answer("❌ Error processing action")
