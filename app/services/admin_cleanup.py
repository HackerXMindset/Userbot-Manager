import logging
from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


class AdminCleanupService:
    """Performs admin-triggered cleanup tasks for the management bot."""

    def __init__(self, db, keyboards):
        self._db = db
        self._keyboards = keyboards
        self._logger = logging.getLogger(__name__)

    async def run_cleanup(self, query: types.CallbackQuery) -> None:
        """
        Execute the cleanup workflow and report results to the admin.

        This mirrors the legacy behaviour inside ``ManagementBot.confirm_cleanup``.
        """

        try:
            stopped_tokens = await self._db.fetchval(
                """
                SELECT COUNT(*) FROM tokens_tracked
                WHERE status = 'stopped' AND first_seen_at < NOW() - INTERVAL '1 day'
                """
            )

            old_calls = await self._db.fetchval(
                """
                SELECT COUNT(*) FROM token_call_history
                WHERE called_at < NOW() - INTERVAL '7 days'
                """
            )

            await self._db.execute(
                """
                DELETE FROM tokens_tracked
                WHERE status = 'stopped' AND first_seen_at < NOW() - INTERVAL '1 day'
                """
            )

            await self._db.execute(
                """
                DELETE FROM token_call_history
                WHERE called_at < NOW() - INTERVAL '7 days'
                """
            )

            total_cleaned = stopped_tokens + old_calls

            text = (
                "✅ <b>Cleanup Completed</b>\n\n"
                "<b>Items Removed:</b>\n"
                f"├ Stopped Tokens: {stopped_tokens}\n"
                f"├ Failed Calls: {old_calls}\n"
                f"└ Total: {total_cleaned} records\n\n"
                "Database cleanup successful!"
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]]
            )

            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Cleanup completed successfully!")

        except Exception as error:  # pragma: no cover - logging only
            self._logger.error("Error performing cleanup: %s", error)
            await query.answer("❌ Error performing cleanup")
