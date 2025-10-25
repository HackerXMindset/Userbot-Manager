import logging
from typing import Dict

from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


WIPE_CONTRACTS_CALLBACK = "cleanup:wipe_contracts"
CANCEL_WIPE_CALLBACK = "cleanup:cancel_wipe"

try:
    from asyncpg import exceptions as pg_exceptions  # type: ignore
except ImportError:  # pragma: no cover - fallback when asyncpg unavailable
    class pg_exceptions:  # type: ignore
        UndefinedTableError = Exception


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

    @staticmethod
    def _extract_deleted_count(result: str) -> int:
        """Parse row counts from ``asyncpg`` DELETE responses."""
        try:
            return int(result.split()[-1])
        except (ValueError, AttributeError, IndexError):
            return 0

    async def prompt_wipe_contracts(self, message: types.Message) -> None:
        """
        Present a confirmation dialog for wiping all contract-address data.
        """

        stats_queries = {
            "Tracked tokens": "SELECT COUNT(*) FROM tokens_tracked",
            "Call history": "SELECT COUNT(*) FROM token_call_history",
            "Call queue jobs": "SELECT COUNT(*) FROM call_queue",
            "Alert queue": "SELECT COUNT(*) FROM alert_queue",
            "Forwarded log": "SELECT COUNT(*) FROM forwarded_tokens_log",
            "Curated alpha state": "SELECT COUNT(*) FROM curated_alpha_token_state",
        }

        stats: Dict[str, int] = {}
        for label, query in stats_queries.items():
            try:
                value = await self._db.fetchval(query)
                stats[label] = int(value or 0)
            except Exception as error:  # pragma: no cover - defensive log
                self._logger.error("Failed to fetch %s count: %s", label, error)
                stats[label] = -1

        totals_lines = "\n".join(
            f"• {label}: {count if count >= 0 else 'unknown'}" for label, count in stats.items()
        )

        text = (
            "⚠️ <b>Danger Zone: Wipe All Contract Addresses</b>\n\n"
            "This action permanently removes every tracked contract address and the "
            "associated operational queues/logs. Related tables will cascade-delete downstream data.\n\n"
            "<b>Current totals:</b>\n"
            f"{totals_lines}\n\n"
            "Only proceed if you understand the impact. This cannot be undone."
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Wipe Everything",
                        callback_data=WIPE_CONTRACTS_CALLBACK,
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="❌ Cancel",
                        callback_data=CANCEL_WIPE_CALLBACK,
                    )
                ],
            ]
        )

        await message.answer(text, reply_markup=keyboard, parse_mode="HTML")

    async def confirm_wipe_contracts(self, query: types.CallbackQuery) -> None:
        """
        Execute the destructive wipe of all contract-address records.
        """

        deletion_statements = [
            ("alert_queue", "DELETE FROM alert_queue"),
            ("call_queue", "DELETE FROM call_queue"),
            ("forwarded_tokens_log", "DELETE FROM forwarded_tokens_log"),
            ("curated_alpha_token_state", "DELETE FROM curated_alpha_token_state"),
            ("token_call_history", "DELETE FROM token_call_history"),
            ("tokens_tracked", "DELETE FROM tokens_tracked"),
        ]

        results: Dict[str, int] = {}

        try:
            async with self._db.acquire() as conn:
                if conn is None:
                    await query.answer("⚠️ Database shutting down; wipe skipped.", show_alert=True)
                    return

                async with conn.transaction():
                    for label, statement in deletion_statements:
                        try:
                            result = await conn.execute(statement)
                        except pg_exceptions.UndefinedTableError:
                            self._logger.warning("Skipping wipe for missing table '%s'.", label)
                            results[label] = 0
                            continue
                        results[label] = self._extract_deleted_count(result)

            total_removed = sum(results.values())
            summary_lines = "\n".join(f"• {label}: {count}" for label, count in results.items())
            text = (
                "🧹 <b>Contract Data Cleared</b>\n\n"
                "<b>Rows deleted:</b>\n"
                f"{summary_lines}\n\n"
                f"<b>Total removed:</b> {total_removed}"
            )

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[[InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]]
            )

            await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer("✅ All contract data wiped.")

        except Exception as error:  # pragma: no cover - logging only
            self._logger.error("Error wiping contract data: %s", error, exc_info=True)
            await query.answer("❌ Failed to wipe contract data.", show_alert=True)

    async def cancel_wipe_contracts(self, query: types.CallbackQuery) -> None:
        """
        Abort the contract-address wipe workflow.
        """

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]]
        )

        try:
            await query.message.edit_text(
                "❎ Wipe cancelled. No changes were made.", reply_markup=keyboard
            )
        except Exception:  # pragma: no cover - best effort
            await query.answer("❎ Wipe cancelled.")
        else:
            await query.answer("❎ Wipe cancelled.")
