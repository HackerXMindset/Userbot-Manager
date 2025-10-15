"""
Gain Alerts Handler - Manages monitored source configuration for gain alerts.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any, Dict, List, Optional

from aiogram import types
from aiogram.fsm.context import FSMContext

from app.models.monitored_source import MonitoredSourceModel
from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


class GainAlertsHandler:
    """Handler for managing monitored sources used by the gain alert system."""

    def __init__(self, db_pool, keyboards: Keyboards):
        self.db = db_pool
        self.keyboards = keyboards
        self.model = MonitoredSourceModel(db_pool)

    async def show_main_menu(self, query: types.CallbackQuery, state: Optional[FSMContext] = None) -> None:
        """Display the monitored source overview."""
        try:
            if state:
                await state.clear()

            sources = await self.model.get_all_with_stats()
            text = self._format_sources_overview(sources)

            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.gain_alerts_main_menu(has_sources=bool(sources))
            )
        except Exception as exc:
            logger.error("Error showing gain alerts menu: %s", exc, exc_info=True)
            await query.answer("❌ Failed to load gain alerts", show_alert=True)

    async def start_add_flow(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Begin add monitored source flow."""
        await state.clear()
        await state.set_state(ManagementStates.gain_alerts_add_type)

        text = (
            "<b>➕ Add Monitored Source</b>\n\n"
            "Choose the type of Telegram entity you want to monitor:\n\n"
            "📢 <b>Channel</b> – Track every post in a channel\n"
            "👥 <b>Group</b> – Track contract addresses from specific posters\n"
            "💬 <b>DM</b> – Track direct messages from a single account\n\n"
            "Select an option to continue."
        )

        try:
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.gain_alerts_type_selector()
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting add monitored source flow: %s", exc, exc_info=True)
            await query.answer("❌ Failed to start add flow", show_alert=True)

    async def handle_type_selected(self, query: types.CallbackQuery, state: FSMContext, chat_type: str) -> None:
        """Handle source type selection."""
        await state.update_data(chat_type=chat_type)
        await state.set_state(ManagementStates.gain_alerts_add_chat_id)

        if chat_type == "dm":
            guidance = "Enter the DM user ID to monitor (positive integer)."
        else:
            guidance = "Enter the Telegram chat ID (negative integer)."

        prompt = (
            f"<b>➕ Add {self._chat_type_label(chat_type)}</b>\n\n"
            f"{guidance}\n\n"
            "Example: <code>-1001234567890</code>\n"
            "Use the cancel button to abort."
        )

        await query.message.edit_text(
            prompt,
            reply_markup=self.keyboards.cancel_button("gain_alerts:cancel")
        )
        await query.answer()

    async def handle_chat_id_input(self, message: types.Message, state: FSMContext) -> None:
        """Validate chat ID input during add flow."""
        data = await state.get_data()
        chat_type = data.get("chat_type")

        if not chat_type:
            await message.answer("❌ Type selection expired. Please start again.")
            await state.clear()
            return

        chat_id = self._parse_int(message.text)
        if chat_id is None:
            await message.answer("❌ Invalid chat ID. Please enter a numeric value.")
            return

        if chat_type in {"group", "channel"} and chat_id >= 0:
            await message.answer("❌ Chat IDs for groups/channels must be negative (e.g., -1001234567890).")
            return

        if chat_type == "dm" and chat_id <= 0:
            await message.answer("❌ DM user IDs must be positive integers.")
            return

        # Prevent duplicate registrations
        existing = await self.model.is_monitored(chat_id, None)
        if chat_type in {"channel", "dm"} and existing:
            await message.answer("⚠️ This chat is already monitored. Remove it first if you need to reconfigure.")
            await state.clear()
            return

        await state.update_data(chat_id=chat_id)

        if chat_type == "group":
            await state.set_state(ManagementStates.gain_alerts_add_user_id)
            await message.answer(
                "<b>👥 Monitor Specific User</b>\n\n"
                "Enter the Telegram user ID of the person to monitor in this group.\n"
                "User IDs must be positive integers.",
                reply_markup=self.keyboards.cancel_button("gain_alerts:cancel")
            )
            return

        await state.update_data(user_id=None)
        await state.set_state(ManagementStates.gain_alerts_confirm_add)
        await self._show_add_confirmation(message, state)

    async def handle_user_id_input(self, message: types.Message, state: FSMContext) -> None:
        """Validate user ID input for group monitoring."""
        data = await state.get_data()
        chat_id = data.get("chat_id")
        chat_type = data.get("chat_type")

        if not chat_id or chat_type != "group":
            await message.answer("❌ Session expired. Please restart the add flow.")
            await state.clear()
            return

        user_id = self._parse_int(message.text)
        if user_id is None or user_id <= 0:
            await message.answer("❌ Invalid user ID. Please enter a positive integer.")
            return

        # Prevent duplicate registration for the same user+group pair
        existing = await self.model.is_monitored(chat_id, user_id)
        if existing:
            await message.answer("⚠️ That user is already monitored in this group.")
            await state.clear()
            return

        await state.update_data(user_id=user_id)
        await state.set_state(ManagementStates.gain_alerts_confirm_add)
        await self._show_add_confirmation(message, state)

    async def confirm_add(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Persist monitored source after confirmation."""
        data = await state.get_data()
        chat_type = data.get("chat_type")
        chat_id = data.get("chat_id")
        user_id = data.get("user_id")

        if chat_type is None or chat_id is None or (chat_type == "group" and user_id is None):
            await query.answer("❌ Missing data. Please start again.", show_alert=True)
            await state.clear()
            return

        try:
            from asyncpg import UniqueViolationError  # Lazy import to avoid mandatory dependency at module import time

            await self.model.add_source(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=user_id,
                admin_id=query.from_user.id,
            )
        except UniqueViolationError:
            await query.answer("⚠️ This source is already monitored.", show_alert=True)
            await state.clear()
            return
        except ValueError as exc:
            logger.warning("Add monitored source validation error: %s", exc)
            await query.answer(f"❌ {exc}", show_alert=True)
            await state.clear()
            return
        except Exception as exc:
            logger.error("Failed to add monitored source: %s", exc, exc_info=True)
            await query.answer("❌ Failed to add monitored source", show_alert=True)
            await state.clear()
            return

        await query.answer("✅ Monitored source added!", show_alert=False)
        await self.show_main_menu(query, state)

    async def cancel(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Cancel any in-progress workflow."""
        await state.clear()
        await self.show_main_menu(query, state=None)
        await query.answer()

    async def start_remove_flow(self, query: types.CallbackQuery) -> None:
        """Display selectable list of monitored sources for removal."""
        sources = await self.model.get_all_with_stats()
        if not sources:
            await query.answer("Nothing to remove.", show_alert=True)
            return

        text = (
            "<b>🗑️ Remove Monitored Source</b>\n\n"
            "Select an entry to delete. All gain alert tracking data for that source "
            "will be removed."
        )

        await query.message.edit_text(
            text,
            reply_markup=self.keyboards.gain_alerts_remove_menu(sources)
        )
        await query.answer()

    async def prompt_remove_confirmation(self, query: types.CallbackQuery, source_id: int) -> None:
        """Show confirmation prompt before deleting a monitored source."""
        source = await self.model.get_with_stats(source_id)
        if not source:
            await query.answer("Monitored source not found.", show_alert=True)
            return

        token_count = source.get("token_count") or 0
        chat_label = self._chat_label(source)
        user_label = f"User ID: {source['user_id']}" if source["chat_type"] == "group" else "All messages"

        text = (
            "<b>⚠️ Confirm Removal</b>\n\n"
            f"{chat_label}\n"
            f"{user_label}\n"
            f"Tracked tokens: {token_count}\n\n"
            "This will delete the monitored source and all of its per-group alert baselines.\n"
            "<b>This action cannot be undone.</b>"
        )

        await query.message.edit_text(
            text,
            reply_markup=self.keyboards.gain_alerts_remove_confirm(source_id)
        )
        await query.answer()

    async def confirm_remove(self, query: types.CallbackQuery, source_id: int) -> None:
        """Delete a monitored source."""
        deleted = await self.model.remove_source(source_id)
        if not deleted:
            await query.answer("Source already removed.", show_alert=True)
            return

        await query.answer("✅ Monitored source removed.", show_alert=False)
        await self.show_main_menu(query, state=None)

    # --------------------------------------------------------------------- #
    # Helper utilities
    # --------------------------------------------------------------------- #

    def _format_sources_overview(self, sources: List[Dict[str, Any]]) -> str:
        """Build the overview text for the monitored sources menu."""
        if not sources:
            return (
                "<b>📈 Gain Alerts – Monitored Sources</b>\n\n"
                "No chats or users are being monitored yet.\n\n"
                "Add a monitored source to start triggering gain alerts when "
                "contract addresses appear in tracked conversations."
            )

        grouped: Dict[int, Dict[str, Any]] = defaultdict(lambda: {
            "chat_type": None,
            "records": [],
            "token_sum": 0,
        })

        for row in sources:
            chat_entry = grouped[row["chat_id"]]
            chat_entry["chat_type"] = row["chat_type"]
            chat_entry["records"].append(row)
            chat_entry["token_sum"] += int(row.get("token_count") or 0)

        total_sources = len(sources)
        total_tokens = sum(entry["token_sum"] for entry in grouped.values())

        lines = [
            "<b>📈 Gain Alerts – Monitored Sources</b>",
            "",
            f"Tracking {total_sources} source(s) across {total_tokens} token baseline(s):",
            "",
        ]

        type_icons = {
            "group": "👥",
            "channel": "📢",
            "dm": "💬",
        }

        for chat_id, info in grouped.items():
            chat_type = info["chat_type"]
            icon = type_icons.get(chat_type, "❔")
            chat_label = self._chat_label({"chat_id": chat_id, "chat_type": chat_type})
            lines.append(f"{icon} {chat_label}")

            for record in info["records"]:
                if chat_type == "group":
                    lines.append(
                        f"  • User {record['user_id']} – {record.get('token_count', 0)} token(s)"
                    )
                else:
                    lines.append(
                        f"  • All messages – {record.get('token_count', 0)} token(s)"
                    )
            lines.append("")

        lines.append("Use the buttons below to add or remove monitored sources.")
        return "\n".join(lines)

    def _show_add_entry_summary(self, data: Dict[str, Any]) -> str:
        """Generate confirmation summary text."""
        chat_label = self._chat_label(data)
        user_part = ""
        if data.get("chat_type") == "group":
            user_part = f"\nMonitor User ID: <code>{data.get('user_id')}</code>"
        else:
            user_part = "\nScope: All messages"

        return (
            "<b>✅ Confirm Monitored Source</b>\n\n"
            f"{chat_label}"
            f"{user_part}\n\n"
            "Gain alerts will trigger when contract addresses are posted in this conversation."
        )

    async def _show_add_confirmation(self, message: types.Message, state: FSMContext) -> None:
        """Send confirmation prompt after collecting all inputs."""
        data = await state.get_data()
        text = self._show_add_entry_summary(data)

        await message.answer(
            text,
            reply_markup=self.keyboards.gain_alerts_add_confirm()
        )

    @staticmethod
    def _parse_int(raw: Optional[str]) -> Optional[int]:
        """Convert text to integer if possible."""
        if raw is None:
            return None
        try:
            return int(raw.strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _chat_type_label(chat_type: str) -> str:
        return {
            "group": "👥 Group Source",
            "channel": "📢 Channel Source",
            "dm": "💬 DM Source",
        }.get(chat_type, "Unknown Source")

    @staticmethod
    def _chat_label(data: Dict[str, Any]) -> str:
        chat_type = data.get("chat_type")
        chat_id = data.get("chat_id")

        if chat_type == "group":
            return f"Group ID: <code>{chat_id}</code>"
        if chat_type == "channel":
            return f"Channel ID: <code>{chat_id}</code>"
        if chat_type == "dm":
            return f"DM ID: <code>{chat_id}</code>"
        return f"Chat ID: <code>{chat_id}</code>"
