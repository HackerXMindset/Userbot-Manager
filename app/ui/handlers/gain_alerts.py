"""
Gain Alerts Handler - Manages monitored source configuration for gain alerts.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import html

from aiogram import Bot, types
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.config import get_gain_alert_template_text, get_chart_guardrails
from app.gain_alert_templates import (
    missing_required_placeholders,
    normalise_template,
    REQUIRED_GAIN_TEMPLATE_PLACEHOLDERS,
)
from app.models.monitored_source import MonitoredSourceModel
from app.models.chart_request_group import ChartRequestGroupModel
from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


class GainAlertsHandler:
    """Handler for managing monitored sources used by the gain alert system."""

    DEFAULT_CHART_THRESHOLD: Decimal = Decimal("100000")

    def __init__(self, db_pool, keyboards: Keyboards):
        self.db = db_pool
        self.keyboards = keyboards
        self.model = MonitoredSourceModel(db_pool)
        self.chart_group_model = ChartRequestGroupModel(db_pool)
        self._member_display_cache: Dict[Tuple[int, int], str] = {}
        self._chart_bot_cache: Dict[int, str] = {}

    async def show_main_menu(self, query: types.CallbackQuery, state: Optional[FSMContext] = None) -> None:
        """Display the monitored source overview."""
        try:
            if state:
                await state.clear()

            sources = await self.model.get_all_with_stats()
            userbots = await self.model.list_available_userbots()
            userbot_lookup = {
                record["id"]: record["label"]
                for record in userbots
            }
            known_targets = await self.model.list_known_target_chats()
            target_lookup = {
                record["chat_id"]: record["label"]
                for record in known_targets
            }

            grouped = self._group_sources(sources)
            text = self._format_sources_overview(grouped, userbot_lookup, target_lookup)
            menu_entries = self._summaries_for_menu(grouped, userbot_lookup)

            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.gain_alerts_main_menu(menu_entries),
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Error showing gain alerts menu: %s", exc, exc_info=True)
            await query.answer("❌ Failed to load gain alerts", show_alert=True)

    async def show_source_detail(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Show detail view for a specific monitored chat."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await self.show_main_menu(query, state=None)
                await query.answer("Monitored source not found.", show_alert=True)
                return

            await query.message.edit_text(
                context["text"],
                reply_markup=context["keyboard"],
                parse_mode="HTML",
            )
        except Exception as exc:
            logger.error("Error showing gain alert source detail for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to load source detail", show_alert=True)

    async def cancel(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Handle generic cancel actions from gain alerts flows."""
        try:
            data = await state.get_data()
            await state.clear()

            return_chat_id = data.get("return_to_chat_id")
            detail_chat_id = data.get("detail_chat_id") or data.get("chart_settings_chat_id")
            detail_message_id = data.get("detail_message_id") or data.get("chart_settings_message_id")
            return_view = data.get("return_view")

            if return_chat_id:
                if return_view == "tracked":
                    view = await self._build_tracked_users_view(query.bot, int(return_chat_id))
                    if view is not None and detail_chat_id is not None and detail_message_id is not None:
                        text, keyboard = view
                        try:
                            await query.bot.edit_message_text(
                                text=text,
                                chat_id=detail_chat_id,
                                message_id=detail_message_id,
                                reply_markup=keyboard,
                                parse_mode="HTML",
                            )
                        except TelegramBadRequest as exc:
                            if "message to edit not found" not in str(exc).lower():
                                logger.warning("Unable to refresh tracked users view for chat %s: %s", return_chat_id, exc)
                    await query.message.edit_text("❎ Action cancelled.", parse_mode="HTML")
                else:
                    await self.show_source_detail(query, int(return_chat_id))
            else:
                await self.show_main_menu(query, state=None)

            await query.answer("Cancelled.")
        except Exception as exc:
            logger.error("Error cancelling gain alerts flow: %s", exc, exc_info=True)
            await query.answer("❌ Failed to cancel. Please return to the main menu manually.", show_alert=True)

    async def start_edit_name(self, query: types.CallbackQuery, state: FSMContext, chat_id: int) -> None:
        """Prompt admin to set or clear a display name for the monitored source."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            current_name = entry.get("display_name") or "—"
            record_ids = sorted({int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None})

            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            await state.clear()
            await state.set_state(ManagementStates.gain_alerts_edit_name)
            await state.update_data(
                chat_id=chat_id,
                record_ids=record_ids,
                return_to_chat_id=chat_id,
                detail_chat_id=query.message.chat.id,
                detail_message_id=query.message.message_id,
                previous_display_name=entry.get("display_name"),
            )

            prompt = (
                "<b>✏️ Set Display Name</b>\n\n"
                f"Current: <code>{current_name}</code>\n\n"
                "Send a new display name (2–64 characters) to show in menus, "
                "or type <code>clear</code> to remove the alias.\n\n"
                "Use the cancel button to abort."
            )

            await query.message.edit_text(
                prompt,
                reply_markup=self.keyboards.cancel_button("gain_alerts:cancel"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting gain alert name edit for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to start name editor", show_alert=True)

    async def toggle_source_enabled(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Flip the enabled flag for all monitored source entries tied to the chat."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted({int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None})

            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            new_status = not entry.get("is_enabled", True)

            for source_id in record_ids:
                await self.model.set_enabled(source_id, new_status)

            await self.show_source_detail(query, chat_id)

            await query.answer("Alerts enabled." if new_status else "Alerts disabled.")
        except Exception as exc:
            logger.error("Error toggling gain alert source %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to toggle alerts", show_alert=True)

    async def start_sensitivity_menu(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Display preset sensitivity options for the source."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            current_value = entry.get("sensitivity_pct")
            if current_value is not None:
                try:
                    percent_text = f"+{float(current_value) * 100:.0f}%"
                except (TypeError, ValueError):
                    percent_text = "<i>invalid</i>"
            else:
                percent_text = "Using global default"

            text = (
                "<b>🎯 Gain Sensitivity</b>\n\n"
                f"Current setting: {percent_text}\n\n"
                "Choose a preset below, set a custom percentage, or revert to the global default."
            )

            keyboard = self._build_sensitivity_menu_keyboard(chat_id)
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer()
        except Exception as exc:
            logger.error("Error showing sensitivity menu for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to load sensitivity menu", show_alert=True)

    async def start_edit_template(self, query: types.CallbackQuery, state: FSMContext, chat_id: int) -> None:
        """Prompt admin to configure a template override for the monitored source."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            current_override = entry.get("template_text")
            global_template = await get_gain_alert_template_text()

            template_preview = html.escape(current_override or global_template)
            placeholder_list = [
                "{gain_emoji}",
                "{token_symbol}",
                "{multiplier}",
                "{first_market_cap}",
                "{current_market_cap}",
                "{elapsed_time}",
                "{address}",
            ]
            placeholders_text = ", ".join(placeholder_list)
            optional_note = "Use any placeholders you like; leave them out if you prefer a plain message."

            await state.clear()
            await state.set_state(ManagementStates.gain_alerts_edit_template)
            await state.update_data(
                chat_id=chat_id,
                return_to_chat_id=chat_id,
                detail_chat_id=query.message.chat.id,
                detail_message_id=query.message.message_id,
            )

            prompt_lines = [
                "<b>📝 Edit Gain Alert Template</b>",
                "",
                "Available placeholders:",
                f"<code>{placeholders_text}</code>",
                "",
                f"<i>{optional_note}</i>",
                "",
                "Send the new template text exactly as you want it to appear.",
                "Type <code>reset</code> to remove the custom override and use the global template.",
                "",
                "<b>Current template:</b>",
                f"<code>{template_preview}</code>",
            ]

            await query.message.edit_text(
                "\n".join(prompt_lines),
                reply_markup=self.keyboards.cancel_button("gain_alerts:cancel"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting template edit for chat %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to open template editor", show_alert=True)

    async def set_sensitivity_value(self, query: types.CallbackQuery, chat_id: int, raw_value: Optional[str]) -> None:
        """Apply a preset or default sensitivity value."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted({int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None})
            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            new_value: Optional[float]
            if raw_value in {None, "default", "clear"}:
                new_value = None
            else:
                try:
                    decimal_value = Decimal(raw_value)
                except (InvalidOperation, TypeError):
                    await query.answer("❌ Invalid sensitivity value", show_alert=True)
                    return

                if decimal_value <= 0:
                    await query.answer("❌ Sensitivity must be greater than 0", show_alert=True)
                    return

                # clamp to reasonable upper bound (5.0 -> 500%)
                if decimal_value > Decimal("5"):
                    await query.answer("❌ Sensitivity too high", show_alert=True)
                    return

                decimal_value = decimal_value.quantize(Decimal("0.00001"))
                new_value = float(decimal_value)

            for source_id in record_ids:
                await self.model.set_sensitivity(source_id, new_value)

            await self.show_source_detail(query, chat_id)

            if new_value is None:
                await query.answer("Sensitivity reset to default.")
            else:
                await query.answer(f"Sensitivity set to +{new_value * 100:.0f}%.")
        except Exception as exc:
            logger.error("Error setting sensitivity for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to update sensitivity", show_alert=True)

    async def start_sensitivity_custom(self, query: types.CallbackQuery, state: FSMContext, chat_id: int) -> None:
        """Prompt for a custom sensitivity percentage."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted({int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None})
            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            current_value = entry.get("sensitivity_pct")
            if current_value is not None:
                try:
                    current_display = f"Current: +{float(current_value) * 100:.0f}%"
                except (TypeError, ValueError):
                    current_display = "Current: <i>invalid</i>"
            else:
                current_display = "Currently using global default"

            await state.clear()
            await state.set_state(ManagementStates.gain_alerts_edit_sensitivity)
            await state.update_data(
                chat_id=chat_id,
                record_ids=record_ids,
                return_to_chat_id=chat_id,
                detail_chat_id=query.message.chat.id,
                detail_message_id=query.message.message_id,
                return_view="detail",
            )

            prompt = (
                "<b>🎯 Custom Sensitivity</b>\n\n"
                f"{current_display}\n\n"
                "Send a new gain increase percentage (e.g., <code>35</code> for +35%).\n"
                "Values must be between 1 and 500. Type <code>default</code> to reset."
            )

            await query.message.edit_text(
                prompt,
                reply_markup=self.keyboards.cancel_button("gain_alerts:cancel"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting custom sensitivity editor for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to start sensitivity editor", show_alert=True)

    async def start_userbot_menu(self, query: types.CallbackQuery, chat_id: int, page: int = 1) -> None:
        """Show userbot assignment options."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            current_bot_id = entry.get("assigned_userbot_id")
            userbot_records_raw = await self.model.list_available_userbots()
            userbot_records = [dict(record) for record in userbot_records_raw]

            if entry.get("use_management_bot"):
                current_display = "Management bot"
            elif current_bot_id:
                current_label = next((record["label"] for record in userbot_records if record["id"] == current_bot_id), None)
                current_display = current_label or f"Userbot {current_bot_id}"
            else:
                current_display = "Not assigned"

            lines = [
                "<b>🤖 Choose Alert Sender</b>",
                "",
                f"Current sender: {current_display}",
                "",
            ]

            if userbot_records:
                lines.append("Select a sender below. Management bot posts via the admin bot; userbots post via Telethon workers.")
            else:
                lines.append("No userbots available. Add a userbot first from the main menu or use the management bot option above.")

            text = "\n".join(lines)
            keyboard = self._build_userbot_menu_keyboard(
                chat_id,
                userbot_records,
                current_bot_id,
                bool(entry.get("use_management_bot")),
                page,
            )

            await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            await query.answer()
        except Exception as exc:
            logger.error("Error showing userbot menu for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to load userbot menu", show_alert=True)

    async def set_userbot_assignment(self, query: types.CallbackQuery, chat_id: int, raw_userbot_id: Optional[str]) -> None:
        """Assign or clear the userbot for the monitored source."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted({int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None})
            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            if raw_userbot_id == "management":
                await self.model.set_management_bot_for_chat(chat_id, True)
                for source_id in record_ids:
                    await self.model.assign_userbot(source_id, None)
                await self.show_source_detail(query, chat_id)
                await query.answer("Using management bot for alerts.")
                return

            if raw_userbot_id in {None, "clear"}:
                target_userbot_id: Optional[int] = None
            else:
                try:
                    target_userbot_id = int(raw_userbot_id)
                except (TypeError, ValueError):
                    await query.answer("❌ Invalid userbot selection", show_alert=True)
                    return

            await self.model.set_management_bot_for_chat(chat_id, False)

            for source_id in record_ids:
                await self.model.assign_userbot(source_id, target_userbot_id)

            await self.show_source_detail(query, chat_id)

            if target_userbot_id is None:
                await query.answer("Sender cleared (pooled userbot).")
            else:
                await query.answer("Userbot assigned.")
        except Exception as exc:
            logger.error("Error assigning userbot for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to assign userbot", show_alert=True)

    async def show_tracked_users_menu(self, query: types.CallbackQuery, chat_id: int, *, answer: bool = True) -> None:
        """Display tracked users with options to add or remove."""
        try:
            view = await self._build_tracked_users_view(query.bot, chat_id)
            if view is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            text, keyboard = view
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            if answer:
                await query.answer()
        except Exception as exc:
            logger.error("Error showing tracked users for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to load tracked users", show_alert=True)

    async def start_add_users_to_group(self, query: types.CallbackQuery, state: FSMContext, chat_id: int, return_view: str = "detail") -> None:
        """Prompt admin to add more monitored users for an existing group.

        The ``return_view`` flag controls whether we return to the main detail view
        or back to the tracked-users sub-menu when the flow completes.
        """
        try:
            await state.clear()
            await state.set_state(ManagementStates.gain_alerts_add_user_id)
            await state.update_data(
                chat_type="group",
                chat_id=chat_id,
                user_id=None,
                user_ids=[],
                skipped_user_ids=[],
                return_to_chat_id=chat_id,
                return_view=return_view,
            )

            prompt = (
                "<b>👥 Monitor Group Members</b>\n\n"
                f"Group ID: <code>{chat_id}</code>\n\n"
                "Enter one or more Telegram user IDs to monitor in this group.\n"
                "User IDs must be positive integers. Separate multiple IDs with commas or spaces."
            )

            await query.message.edit_text(
                prompt,
                reply_markup=self.keyboards.cancel_button("gain_alerts:cancel"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting add users flow for group %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to start add users flow", show_alert=True)

    async def remove_user_from_group(self, query: types.CallbackQuery, source_id: int) -> None:
        """Remove a specific monitored user from a group chat."""
        try:
            record = await self.model.get_by_id(source_id)
            if not record:
                await query.answer("Monitored user not found.", show_alert=True)
                return

            chat_id = record["chat_id"]
            deleted = await self.model.remove_source(source_id)
            if not deleted:
                await query.answer("Monitored user already removed.", show_alert=True)
                return

            await query.answer("✅ Monitored user removed.", show_alert=False)

            view = await self._build_tracked_users_view(query.bot, chat_id)
            if view is not None:
                text, keyboard = view
                await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            else:
                await self.show_source_detail(query, chat_id)
        except Exception as exc:
            logger.error("Error removing monitored user %s: %s", source_id, exc, exc_info=True)
            await query.answer("❌ Failed to remove monitored user", show_alert=True)

    async def start_remove_chat(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Prompt for confirmation before deleting all monitored entries for a chat."""
        try:
            records = await self.model.get_by_chat(chat_id)
            if not records:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            grouped = self._group_sources(records)
            entry = grouped.get(chat_id) or (next(iter(grouped.values()), None) if grouped else None)
            if entry is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            display_name = entry.get("display_name")
            chat_label = self._chat_label(entry)
            token_sum = entry.get("token_sum", 0)
            user_records = [record for record in entry.get("records", []) if record.get("user_id") is not None]
            tracked_user_count = len(user_records)
            scope_line = "Scope: All messages"
            if entry.get("chat_type") == "group":
                scope_line = f"Tracked members: {tracked_user_count}" if tracked_user_count else "Tracked members: none"

            lines = [
                "<b>⚠️ Delete Monitored Source</b>",
                "",
                chat_label,
            ]
            if display_name:
                lines.append(f"Alias: <code>{display_name}</code>")
            lines.extend([
                scope_line,
                f"Tracked baselines: {token_sum}",
                "",
                "This removes every monitored entry for this chat and clears all gain alert history.",
                "<b>This action cannot be undone.</b>",
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="⚠️ Confirm Delete",
                    callback_data=f"gain_alerts:view:remove_chat:confirm:{chat_id}"
                )],
                [InlineKeyboardButton(
                    text="🔙 Back to Detail",
                    callback_data=f"gain_alerts:view:{chat_id}"
                )],
            ])

            await query.message.edit_text(
                "\n".join(lines),
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error preparing delete prompt for chat %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to open delete prompt", show_alert=True)

    async def confirm_remove_chat(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Delete all monitored entries for a chat."""
        try:
            records = await self.model.get_by_chat(chat_id)
            if not records:
                await self.show_main_menu(query, state=None)
                await query.answer("Monitored source already removed.", show_alert=True)
                return

            removed = 0
            for record in records:
                source_id = record.get("id")
                if source_id is None:
                    continue
                try:
                    deleted = await self.model.remove_source(int(source_id))
                except Exception as exc:
                    logger.error("Failed to remove monitored source %s for chat %s: %s", source_id, chat_id, exc, exc_info=True)
                    continue
                if deleted:
                    removed += 1

            await self.show_main_menu(query, state=None)
            if removed:
                await query.answer("✅ Monitored source removed.", show_alert=False)
            else:
                await query.answer("Monitored source already removed.", show_alert=True)
        except Exception as exc:
            logger.error("Error removing monitored chat %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to remove monitored source", show_alert=True)

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
                reply_markup=self.keyboards.gain_alerts_type_selector(),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting add monitored source flow: %s", exc, exc_info=True)
            await query.answer("❌ Failed to start add flow", show_alert=True)

    async def handle_type_selected(self, query: types.CallbackQuery, state: FSMContext, chat_type: str) -> None:
        """Handle source type selection."""
        await state.update_data(chat_type=chat_type, return_to_chat_id=None)
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
            reply_markup=self.keyboards.cancel_button("gain_alerts:cancel"),
            parse_mode="HTML",
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

        await state.update_data(chat_id=chat_id, return_to_chat_id=None, skipped_user_ids=[])

        if chat_type == "group":
            await state.set_state(ManagementStates.gain_alerts_add_user_id)
            await message.answer(
                "<b>👥 Monitor Group Members</b>\n\n"
                "Enter one or more Telegram user IDs to monitor in this group.\n"
                "User IDs must be positive integers. Separate multiple IDs with commas or spaces.",
                reply_markup=self.keyboards.cancel_button("gain_alerts:cancel")
            )
            await state.update_data(user_ids=[])
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

        parsed_ids = self._parse_int_list(message.text)
        if not parsed_ids:
            await message.answer("❌ Invalid user ID. Please enter positive integers separated by commas or spaces.")
            return

        invalid_ids = [uid for uid in parsed_ids if uid <= 0]
        if invalid_ids:
            formatted = ", ".join(str(uid) for uid in invalid_ids)
            await message.answer(f"❌ Invalid user ID(s): {formatted}. Please provide positive integers.")
            return

        unique_ids: List[int] = []
        seen_ids = set()
        for uid in parsed_ids:
            if uid not in seen_ids:
                unique_ids.append(uid)
                seen_ids.add(uid)

        existing_ids: List[int] = []
        new_ids: List[int] = []
        for uid in unique_ids:
            if await self.model.is_monitored(chat_id, uid):
                existing_ids.append(uid)
            else:
                new_ids.append(uid)

        if not new_ids:
            duplicates = ", ".join(str(uid) for uid in existing_ids)
            await message.answer(
                f"⚠️ All provided user IDs are already monitored: {duplicates}.\n"
                "Submit different user IDs or cancel the flow."
            )
            return

        await state.update_data(user_ids=new_ids, skipped_user_ids=existing_ids)
        await state.set_state(ManagementStates.gain_alerts_confirm_add)
        await self._show_add_confirmation(message, state)

    async def handle_edit_name_input(self, message: types.Message, state: FSMContext) -> None:
        """Process display name edits for a monitored source."""
        data = await state.get_data()
        chat_id = data.get("chat_id")
        record_ids: List[int] = data.get("record_ids") or []
        detail_chat_id = data.get("detail_chat_id")
        detail_message_id = data.get("detail_message_id")

        if not chat_id or not record_ids or detail_chat_id is None or detail_message_id is None:
            await message.answer("❌ Session expired. Please restart the edit flow.")
            await state.clear()
            return

        raw_input = (message.text or "").strip()
        if not raw_input:
            await message.answer("❌ Display name cannot be empty. Send text or 'clear' to reset.")
            return

        clear_command = raw_input.lower() in {"clear", "none", "reset", "remove"}
        if clear_command:
            new_name: Optional[str] = None
        else:
            if len(raw_input) < 2 or len(raw_input) > 64:
                await message.answer("❌ Display name must be between 2 and 64 characters.")
                return
            if "\n" in raw_input:
                await message.answer("❌ Display name must be a single line of text.")
                return
            new_name = raw_input

        try:
            for source_id in record_ids:
                await self.model.set_display_name(source_id, new_name)
        except Exception as exc:
            logger.error("Failed to update display name for chat %s: %s", chat_id, exc, exc_info=True)
            await message.answer("❌ Failed to update display name. Please try again.")
            return

        await state.clear()
        confirmation = "✅ Display name cleared." if new_name is None else f"✅ Display name set to <b>{new_name}</b>."
        await message.answer(confirmation, parse_mode="HTML")

        await self._refresh_detail_message(
            message.bot,
            detail_chat_id=detail_chat_id,
            detail_message_id=detail_message_id,
            source_chat_id=int(chat_id),
        )

    async def handle_edit_sensitivity_input(self, message: types.Message, state: FSMContext) -> None:
        """Handle custom sensitivity percentage input."""
        data = await state.get_data()
        chat_id = data.get("chat_id")
        record_ids: List[int] = data.get("record_ids") or []
        detail_chat_id = data.get("detail_chat_id")
        detail_message_id = data.get("detail_message_id")

        if not chat_id or not record_ids or detail_chat_id is None or detail_message_id is None:
            await message.answer("❌ Session expired. Please restart the sensitivity editor.")
            await state.clear()
            return

        raw_input = (message.text or "").strip().lower()
        if not raw_input:
            await message.answer("❌ Please provide a number or 'default'.")
            return

        if raw_input in {"default", "clear", "reset"}:
            new_value: Optional[float] = None
            percent_display = "default"
        else:
            normalized = raw_input.replace("%", "").replace("+", "")
            try:
                decimal_value = Decimal(normalized)
            except InvalidOperation:
                await message.answer("❌ Couldn't parse that number. Try again (e.g., 35 or 0.35).")
                return

            if decimal_value <= 0:
                await message.answer("❌ Sensitivity must be greater than 0.")
                return

            # Treat values >= 1 as percentages (e.g., 35 -> 0.35). Allow up to 500%.
            if decimal_value >= 1:
                if decimal_value > Decimal("500"):
                    await message.answer("❌ Sensitivity too high (max 500%).")
                    return
                decimal_value = (decimal_value / 100).quantize(Decimal("0.00001"))
            else:
                if decimal_value > Decimal("5"):
                    await message.answer("❌ Sensitivity too high (max 500%).")
                    return
                decimal_value = decimal_value.quantize(Decimal("0.00001"))

            new_value = float(decimal_value)
            percent_display = f"+{new_value * 100:.0f}%"

        try:
            for source_id in record_ids:
                await self.model.set_sensitivity(source_id, new_value)
        except Exception as exc:
            logger.error("Failed to update sensitivity for chat %s: %s", chat_id, exc, exc_info=True)
            await message.answer("❌ Failed to update sensitivity. Please try again.")
            return

        await state.clear()
        if new_value is None:
            await message.answer("✅ Sensitivity reset to global default.")
        else:
            await message.answer(f"✅ Sensitivity set to {percent_display}.")

        await self._refresh_detail_message(
            message.bot,
            detail_chat_id=detail_chat_id,
            detail_message_id=detail_message_id,
            source_chat_id=int(chat_id),
        )

    async def handle_edit_template_input(self, message: types.Message, state: FSMContext) -> None:
        """Handle template override input for a monitored source."""
        data = await state.get_data()
        chat_id = data.get("chat_id")
        detail_chat_id = data.get("detail_chat_id")
        detail_message_id = data.get("detail_message_id")

        if chat_id is None or detail_chat_id is None or detail_message_id is None:
            await message.answer("❌ Template editor expired. Please open the source detail again.")
            await state.clear()
            return

        raw_input = message.text or ""
        command = raw_input.strip().lower()

        if not raw_input.strip():
            await message.answer("❌ Template cannot be empty. Include the required placeholders or type 'reset'.")
            return

        if command == "reset":
            try:
                await self.model.set_template_for_chat(int(chat_id), None)
            except Exception as exc:
                logger.error("Failed to reset template for chat %s: %s", chat_id, exc, exc_info=True)
                await message.answer("❌ Failed to reset template. Please try again.")
                return

            await message.answer("✅ Template reset to global default.")
        else:
            cleaned = normalise_template(raw_input)
            try:
                await self.model.set_template_for_chat(int(chat_id), cleaned)
            except Exception as exc:
                logger.error("Failed to set template for chat %s: %s", chat_id, exc, exc_info=True)
                await message.answer("❌ Failed to save template. Please try again.")
                return

            await message.answer("✅ Template updated.")

        await state.clear()
        await self._refresh_detail_message(
            message.bot,
            detail_chat_id=detail_chat_id,
            detail_message_id=detail_message_id,
            source_chat_id=int(chat_id),
        )

    async def confirm_add(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Persist monitored source after confirmation."""
        data = await state.get_data()
        chat_type = data.get("chat_type")
        chat_id = data.get("chat_id")
        user_id = data.get("user_id")

        user_ids: List[Optional[int]] = []
        if chat_type == "group":
            stored_ids = data.get("user_ids")
            if stored_ids:
                user_ids = [int(uid) for uid in stored_ids]
            elif user_id is not None:
                user_ids = [int(user_id)]
            else:
                user_ids = []
        else:
            user_ids = [None]

        if chat_type is None or chat_id is None or (chat_type == "group" and not user_ids):
            await query.answer("❌ Missing data. Please start again.", show_alert=True)
            await state.clear()
            return

        try:
            from asyncpg import UniqueViolationError  # Lazy import to avoid mandatory dependency at module import time

            added_ids: List[Optional[int]] = []
            skipped_ids: List[Optional[int]] = []

            for uid in user_ids:
                try:
                    await self.model.add_source(
                        chat_id=chat_id,
                        chat_type=chat_type,
                        user_id=uid,
                        admin_id=query.from_user.id,
                    )
                    added_ids.append(uid)
                except UniqueViolationError:
                    skipped_ids.append(uid)

            if not added_ids:
                # All entries failed due to duplicates
                await query.answer("⚠️ This source is already monitored.", show_alert=True)
                await state.clear()
                return

            skip_note = ""
            if skipped_ids:
                formatted = ", ".join(str(uid) for uid in skipped_ids if uid is not None)
                if formatted:
                    skip_note = f" (skipped existing IDs: {formatted})"

            await query.answer(f"✅ Monitored source added{skip_note}", show_alert=bool(skip_note))
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

        return_chat_id = data.get("return_to_chat_id")
        detail_chat_id = data.get("detail_chat_id")
        detail_message_id = data.get("detail_message_id")
        return_view = data.get("return_view")
        await state.clear()

        if return_chat_id:
            if return_view == "tracked":
                view = await self._build_tracked_users_view(query.bot, int(return_chat_id))
                if view is not None and detail_chat_id is not None and detail_message_id is not None:
                    text, keyboard = view
                    try:
                        await query.bot.edit_message_text(
                            text=text,
                            chat_id=detail_chat_id,
                            message_id=detail_message_id,
                            reply_markup=keyboard,
                            parse_mode="HTML",
                        )
                    except TelegramBadRequest as exc:
                        if "message to edit not found" not in str(exc).lower():
                            logger.warning("Unable to refresh tracked users view for chat %s: %s", return_chat_id, exc)
                await query.message.edit_text("✅ Tracked users updated.", parse_mode="HTML")
            else:
                await self.show_source_detail(query, int(return_chat_id))
        else:
            await self.show_main_menu(query, state=None)
        await query.answer()

    # --------------------------------------------------------------------- #
    # Chart Settings Management
    # --------------------------------------------------------------------- #

    async def show_chart_settings_menu(self, query: types.CallbackQuery, chat_id: int, *, answer: bool = True) -> None:
        """Display per-source chart configuration."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            text, keyboard = await self._build_chart_settings_view(
                context["entry"],
                context.get("chart_bot_display"),
            )
            await query.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            if answer:
                await query.answer()
        except Exception as exc:
            logger.error("Error showing chart settings for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to load chart settings", show_alert=True)

    async def toggle_chart_enabled(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Flip chart_enabled flag for all monitored entries tied to the chat."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted(
                {int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None}
            )
            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            new_status = not bool(entry.get("chart_enabled"))
            for source_id in record_ids:
                await self.model.set_chart_enabled(source_id, new_status)

            await self.show_chart_settings_menu(query, chat_id, answer=False)
            await query.answer("Chart alerts enabled." if new_status else "Chart alerts disabled.")
        except Exception as exc:
            logger.error("Error toggling chart alerts for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to toggle chart alerts", show_alert=True)

    async def start_edit_chart_threshold(self, query: types.CallbackQuery, state: FSMContext, chat_id: int) -> None:
        """Prompt for MC threshold input."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted(
                {int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None}
            )
            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            current_threshold = entry.get("chart_mc_threshold")
            if current_threshold is None:
                current_display = f"Current: {self._format_chart_threshold(self.DEFAULT_CHART_THRESHOLD)} (default)"
            else:
                current_display = f"Current: {self._format_chart_threshold(current_threshold)}"

            await state.clear()
            await state.set_state(ManagementStates.gain_alerts_edit_chart_threshold)
            await state.update_data(
                chat_id=chat_id,
                record_ids=record_ids,
                chart_settings_chat_id=query.message.chat.id,
                chart_settings_message_id=query.message.message_id,
            )

            prompt = (
                "<b>💰 Set Chart MC Threshold</b>\n\n"
                f"{current_display}\n\n"
                "Enter the minimum market cap required to request a chart.\n"
                "Accepted formats: <code>100000</code>, <code>100k</code>, <code>1.5m</code>, or <code>default</code>."
            )

            await query.message.edit_text(
                prompt,
                reply_markup=self.keyboards.cancel_button(f"gain_alerts:chart_settings:cancel:{chat_id}"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting chart threshold editor for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to start threshold editor", show_alert=True)

    async def handle_chart_threshold_input(self, message: types.Message, state: FSMContext) -> None:
        """Validate and persist MC threshold input."""
        data = await state.get_data()
        chat_id = data.get("chat_id")
        record_ids = data.get("record_ids") or []
        detail_chat_id = data.get("chart_settings_chat_id")
        detail_message_id = data.get("chart_settings_message_id")

        if chat_id is None or not record_ids or detail_chat_id is None or detail_message_id is None:
            await message.answer("❌ Threshold editor expired. Please reopen chart settings.")
            await state.clear()
            return

        raw_text = (message.text or "").strip()
        if not raw_text:
            await message.answer("❌ Please enter a threshold value.")
            return

        normalized = raw_text.lower().strip()
        threshold_value: Optional[float]
        threshold_display: str

        if normalized in {"default", "reset"}:
            threshold_value = None
            threshold_display = f"{self._format_chart_threshold(self.DEFAULT_CHART_THRESHOLD)} (default)"
        else:
            cleaned = normalized.replace(",", "").replace("_", "")
            multiplier = Decimal("1")
            if cleaned.endswith("k"):
                multiplier = Decimal("1000")
                cleaned = cleaned[:-1]
            elif cleaned.endswith("m"):
                multiplier = Decimal("1000000")
                cleaned = cleaned[:-1]
            elif cleaned.endswith("b"):
                multiplier = Decimal("1000000000")
                cleaned = cleaned[:-1]

            cleaned = cleaned.strip()
            if cleaned.startswith("$"):
                cleaned = cleaned[1:]

            try:
                decimal_value = Decimal(cleaned)
            except (InvalidOperation, ValueError):
                await message.answer("❌ Couldn't parse that amount. Try values like 100000, 100k, or 1.5m.")
                return

            decimal_value = (decimal_value * multiplier).quantize(Decimal("0.01"))
            if decimal_value <= 0:
                await message.answer("❌ Threshold must be greater than zero.")
                return

            threshold_value = float(decimal_value)
            threshold_display = self._format_chart_threshold(decimal_value)

        try:
            for source_id in record_ids:
                await self.model.set_chart_mc_threshold(int(source_id), threshold_value)
        except Exception as exc:
            logger.error("Failed to update chart threshold for chat %s: %s", chat_id, exc, exc_info=True)
            await message.answer("❌ Failed to update threshold. Please try again.")
            return

        await state.clear()
        if threshold_value is None:
            await message.answer("✅ Chart threshold reset to default.")
        else:
            await message.answer(f"✅ Chart threshold set to {threshold_display}.")

        await self._render_chart_settings_view(
            message.bot,
            source_chat_id=int(chat_id),
            detail_chat_id=int(detail_chat_id),
            detail_message_id=int(detail_message_id),
        )

    async def start_edit_chart_bot(self, query: types.CallbackQuery, state: FSMContext, chat_id: int) -> None:
        """Prompt for chart bot ID input."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]
            record_ids = sorted(
                {int(record["id"]) for record in entry.get("records", []) if record.get("id") is not None}
            )
            if not record_ids:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            chart_bot_id = entry.get("chart_bot_id")
            chart_bot_display = context.get("chart_bot_display")

            if chart_bot_id:
                current_display = f"Current: {chart_bot_display or f'ID {int(chart_bot_id)}'}"
            else:
                current_display = "Current: Not configured"

            await state.clear()
            await state.set_state(ManagementStates.gain_alerts_edit_chart_bot)
            await state.update_data(
                chat_id=chat_id,
                record_ids=record_ids,
                chart_settings_chat_id=query.message.chat.id,
                chart_settings_message_id=query.message.message_id,
            )

            prompt = (
                "<b>🤖 Set Chart Bot</b>\n\n"
                f"{current_display}\n\n"
                "Enter the Telegram user ID of the chart bot (positive integer).\n"
                "Type <code>clear</code> to remove the configured bot."
            )

            await query.message.edit_text(
                prompt,
                reply_markup=self.keyboards.cancel_button(f"gain_alerts:chart_settings:cancel:{chat_id}"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting chart bot editor for %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to start chart bot editor", show_alert=True)

    async def handle_chart_bot_input(self, message: types.Message, state: FSMContext) -> None:
        """Validate and persist chart bot ID input."""
        data = await state.get_data()
        chat_id = data.get("chat_id")
        record_ids = data.get("record_ids") or []
        detail_chat_id = data.get("chart_settings_chat_id")
        detail_message_id = data.get("chart_settings_message_id")

        if chat_id is None or not record_ids or detail_chat_id is None or detail_message_id is None:
            await message.answer("❌ Chart bot editor expired. Please reopen chart settings.")
            await state.clear()
            return

        raw_text = (message.text or "").strip()
        if not raw_text:
            await message.answer("❌ Please enter a bot ID or type 'clear'.")
            return

        normalized = raw_text.lower()
        bot_id_value: Optional[int]

        if normalized in {"clear", "reset", "none"}:
            bot_id_value = None
        else:
            try:
                bot_id_value = int(raw_text)
            except ValueError:
                await message.answer("❌ Invalid ID. Provide a numeric Telegram user ID or type 'clear'.")
                return

            if bot_id_value <= 0:
                await message.answer("❌ Bot ID must be a positive integer.")
                return

        if bot_id_value is not None:
            self._chart_bot_cache.pop(bot_id_value, None)

        try:
            for source_id in record_ids:
                await self.model.set_chart_bot_id(int(source_id), bot_id_value)
        except Exception as exc:
            logger.error("Failed to update chart bot for chat %s: %s", chat_id, exc, exc_info=True)
            await message.answer("❌ Failed to update chart bot. Please try again.")
            return

        if bot_id_value is None:
            await message.answer("✅ Chart bot cleared.")
        else:
            await message.answer(f"✅ Chart bot set to ID {bot_id_value}.")

        await state.clear()
        await self._render_chart_settings_view(
            message.bot,
            source_chat_id=int(chat_id),
            detail_chat_id=int(detail_chat_id),
            detail_message_id=int(detail_message_id),
        )

    async def cancel_chart_settings(self, query: types.CallbackQuery, state: FSMContext, chat_id: int) -> None:
        """Abort chart settings edit flow and return to the chart settings menu."""
        await state.clear()
        await self.show_chart_settings_menu(query, chat_id)

    # --------------------------------------------------------------------- #
    # Chart Request Groups Management
    # --------------------------------------------------------------------- #

    async def show_chart_groups_menu(self, query: types.CallbackQuery) -> None:
        """Display list of chart request groups with add/remove options."""
        try:
            groups = await self.chart_group_model.list_all()

            lines = [
                "<b>📊 Chart Request Groups</b>",
                "",
                "Groups where bot can post CA to fetch charts:",
                "",
            ]

            if groups:
                for group in groups:
                    chat_id = group['chat_id']
                    label = group.get('label')
                    if label:
                        lines.append(f"• Group <code>{chat_id}</code> ({label})")
                    else:
                        lines.append(f"• Group <code>{chat_id}</code>")
            else:
                lines.append("No chart request groups configured yet.")

            text = "\n".join(lines)
            keyboard = self.keyboards.chart_groups_menu(groups)

            await query.message.edit_text(
                text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error showing chart groups menu: %s", exc, exc_info=True)
            await query.answer("❌ Failed to load chart groups menu", show_alert=True)

    async def start_add_chart_group(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Prompt for chat_id input."""
        try:
            await state.clear()
            await state.set_state(ManagementStates.chart_groups_add_chat_id)

            prompt = (
                "<b>➕ Add Chart Request Group</b>\n\n"
                "Enter the Telegram group chat ID where the bot can post contract addresses "
                "to request charts.\n\n"
                "Chat ID must be a negative integer (e.g., <code>-1001234567890</code>).\n\n"
                "Use the cancel button to abort."
            )

            await query.message.edit_text(
                prompt,
                reply_markup=self.keyboards.cancel_button("gain_alerts:chart_groups:cancel"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting add chart group flow: %s", exc, exc_info=True)
            await query.answer("❌ Failed to start add chart group flow", show_alert=True)

    async def handle_chart_group_input(self, message: types.Message, state: FSMContext) -> None:
        """Validate and add chat_id."""
        try:
            raw_input = (message.text or "").strip()
            if not raw_input:
                await message.answer("❌ Please enter a valid chat ID.")
                return

            try:
                chat_id = int(raw_input)
            except ValueError:
                await message.answer("❌ Invalid chat ID. Please enter a numeric value.")
                return

            if chat_id >= 0:
                await message.answer("❌ Chat ID must be negative (e.g., -1001234567890).")
                return

            # Check if already exists
            existing = await self.chart_group_model.get_by_chat_id(chat_id)
            if existing:
                await message.answer("⚠️ This chat is already configured as a chart request group.")
                await state.clear()
                return

            # Add the group
            from asyncpg import UniqueViolationError
            try:
                await self.chart_group_model.add_group(chat_id, label=None)
                await message.answer(
                    f"✅ Chart request group added: <code>{chat_id}</code>",
                    parse_mode="HTML"
                )
            except UniqueViolationError:
                await message.answer("⚠️ This chat is already configured as a chart request group.")

            await state.clear()
        except Exception as exc:
            logger.error("Error handling chart group input: %s", exc, exc_info=True)
            await message.answer("❌ Failed to add chart request group. Please try again.")
            await state.clear()

    async def remove_chart_group(self, query: types.CallbackQuery, chat_id: int) -> None:
        """Remove group with confirmation."""
        try:
            removed = await self.chart_group_model.remove_group(chat_id)

            if removed:
                await query.answer("✅ Chart request group removed.", show_alert=False)
            else:
                await query.answer("⚠️ Chart request group not found.", show_alert=True)

            # Refresh the menu
            await self.show_chart_groups_menu(query)
        except Exception as exc:
            logger.error("Error removing chart group %s: %s", chat_id, exc, exc_info=True)
            await query.answer("❌ Failed to remove chart request group", show_alert=True)

    async def cancel_chart_groups(self, query: types.CallbackQuery, state: FSMContext) -> None:
        """Cancel chart groups workflow and return to menu."""
        await state.clear()
        await self.show_chart_groups_menu(query)

    # --------------------------------------------------------------------- #

    GUARDRAIL_METRICS = (
        "min_age_minutes",
        "min_liquidity_usd",
        "min_volume_usd",
        "min_multiplier",
        "max_price_change_pct",
        "checks_required",
    )

    def _format_guardrail_value(self, entry: Dict[str, Any], global_guardrails: Dict[str, Any], metric: str) -> str:
        """Format a single guardrail value, showing if it's an override."""
        override = entry.get(f"chart_{metric}")
        global_value = global_guardrails.get(metric, 0)

        if override is None:
            value = global_value
            label = "<i>(global)</i>"
        else:
            value = override
            label = "<b>✏️ override</b>"

        if metric == "min_age_minutes":
            return f"<code>{int(value)} min</code> {label}"
        if metric in ("min_liquidity_usd", "min_volume_usd"):
            return f"<code>{self._format_guardrail_currency(value)}</code> {label}"
        if metric == "min_multiplier":
            return f"<code>x{value:.2f}</code> {label}"
        if metric == "max_price_change_pct":
            return f"<code>{value:.1f}%</code> {label}"
        if metric == "checks_required":
            total_checks = len(self.GUARDRAIL_METRICS)
            strategy = self._describe_guardrail_strategy(int(value), total_checks)
            return f"<code>{int(value)}/{total_checks}</code> {label}"
        return f"<code>{value}</code> {label}"

    def _describe_guardrail_strategy(self, checks_required: int, total_checks: int) -> str:
        """Generate guardrail strategy description."""
        if checks_required <= 0 or checks_required >= total_checks:
            return "All checks must pass"
        return f"Require any {checks_required} of {total_checks} checks"

    @staticmethod
    def _format_guardrail_currency(value: float) -> str:
        """Format a guardrail USD threshold."""
        try:
            decimal_value = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return "$0"
        
        quantised = decimal_value.quantize(Decimal("0.01"))
        formatted = format(quantised, ",.2f")
        if formatted.endswith(".00"):
            formatted = formatted[:-3]
        return f"${formatted}"

    # --------------------------------------------------------------------- #

    def _group_sources(self, sources: List[Dict[str, Any]]) -> OrderedDict[int, Dict[str, Any]]:
        """Group monitored sources by chat ID with aggregated stats."""
        grouped: OrderedDict[int, Dict[str, Any]] = OrderedDict()

        for row in sources or []:
            chat_id = int(row["chat_id"])
            entry = grouped.setdefault(chat_id, {
                "chat_id": chat_id,
                "chat_type": row["chat_type"],
                "records": [],
                "token_sum": 0,
                "target_count": 0,
                "target_chat_ids": [],
                "display_name": row.get("display_name"),
                "is_enabled": row.get("is_enabled", True),
                "sensitivity_pct": row.get("sensitivity_pct"),
                "assigned_userbot_id": row.get("assigned_userbot_id"),
                "created_at": row.get("created_at"),
                "template_text": row.get("template_text"),
                "use_management_bot": bool(row.get("use_management_bot")) if row.get("use_management_bot") is not None else False,
                "chart_enabled": bool(row.get("chart_enabled")) if row.get("chart_enabled") is not None else False,
                "chart_bot_id": row.get("chart_bot_id"),
                "chart_mc_threshold": row.get("chart_mc_threshold"),
                "chart_min_age_minutes": row.get("chart_min_age_minutes"),
                "chart_min_liquidity_usd": row.get("chart_min_liquidity_usd"),
                "chart_min_volume_usd": row.get("chart_min_volume_usd"),
                "chart_min_multiplier": row.get("chart_min_multiplier"),
                "chart_max_price_change_pct": row.get("chart_max_price_change_pct"),
                "chart_checks_required": row.get("chart_checks_required"),
            })
            entry["records"].append(row)
            entry["token_sum"] += int(row.get("token_count") or 0)

            if entry["display_name"] is None and row.get("display_name"):
                entry["display_name"] = row.get("display_name")
            if row.get("is_enabled") is not None:
                entry["is_enabled"] = bool(row.get("is_enabled"))
            if row.get("sensitivity_pct") is not None:
                entry["sensitivity_pct"] = row.get("sensitivity_pct")
            if row.get("assigned_userbot_id") is not None:
                entry["assigned_userbot_id"] = row.get("assigned_userbot_id")
            if row.get("created_at"):
                entry["created_at"] = row.get("created_at")
            if row.get("template_text"):
                entry["template_text"] = row.get("template_text")
            if row.get("use_management_bot") is not None:
                entry["use_management_bot"] = bool(row.get("use_management_bot"))
            if row.get("chart_enabled") is not None:
                entry["chart_enabled"] = bool(row.get("chart_enabled"))
            if "chart_bot_id" in row:
                entry["chart_bot_id"] = row.get("chart_bot_id")
            if "chart_mc_threshold" in row:
                entry["chart_mc_threshold"] = row.get("chart_mc_threshold")

            # Guardrail overrides
            if row.get("chart_min_age_minutes") is not None:
                entry["chart_min_age_minutes"] = row.get("chart_min_age_minutes")
            if row.get("chart_min_liquidity_usd") is not None:
                entry["chart_min_liquidity_usd"] = row.get("chart_min_liquidity_usd")
            if row.get("chart_min_volume_usd") is not None:
                entry["chart_min_volume_usd"] = row.get("chart_min_volume_usd")
            if row.get("chart_min_multiplier") is not None:
                entry["chart_min_multiplier"] = row.get("chart_min_multiplier")
            if row.get("chart_max_price_change_pct") is not None:
                entry["chart_max_price_change_pct"] = row.get("chart_max_price_change_pct")
            if row.get("chart_checks_required") is not None:
                entry["chart_checks_required"] = row.get("chart_checks_required")

            if row.get("target_count") is not None:
                entry["target_count"] = int(row.get("target_count") or 0)

            targets = row.get("target_chat_ids") or []
            if targets:
                existing = set(entry["target_chat_ids"] or [])
                entry["target_chat_ids"] = sorted(existing.union(set(targets)))
                entry["target_count"] = len(entry["target_chat_ids"])

        return grouped

    async def _build_detail_context(self, source_chat_id: int, bot: Optional[Bot] = None) -> Optional[Dict[str, Any]]:
        """Load source entry plus derived text/keyboard for detail view."""
        records = await self.model.get_by_chat(source_chat_id)
        if not records:
            return None

        userbots = await self.model.list_available_userbots()
        userbot_lookup = {record["id"]: record["label"] for record in userbots}

        known_targets = await self.model.list_known_target_chats()
        target_lookup = {record["chat_id"]: record["label"] for record in known_targets}

        grouped = self._group_sources(records)
        entry = grouped.get(source_chat_id)
        if entry is None and grouped:
            entry = next(iter(grouped.values()))

        if entry is None:
            return None

        user_display_map: Dict[int, str] = {}
        if bot and entry.get("chat_type") == "group":
            user_ids = [int(record["user_id"]) for record in entry.get("records", []) if record.get("user_id") is not None]
            user_display_map = await self._resolve_user_display_names(bot, source_chat_id, user_ids)

        chart_bot_display = None
        chart_bot_id = entry.get("chart_bot_id")
        if bot and chart_bot_id:
            chart_bot_display = await self._resolve_chart_bot_display(bot, int(chart_bot_id))

        text = self._format_source_detail(
            entry,
            userbot_lookup,
            target_lookup,
            user_display_map,
            chart_bot_display,
        )
        keyboard = self._build_source_detail_keyboard(entry, userbot_lookup)

        return {
            "entry": entry,
            "text": text,
            "keyboard": keyboard,
            "userbot_lookup": userbot_lookup,
            "target_lookup": target_lookup,
            "user_display_map": user_display_map,
            "chart_bot_display": chart_bot_display,
        }

    async def _resolve_user_display_names(self, bot: Bot, chat_id: int, user_ids: List[int]) -> Dict[int, str]:
        """Resolve Telegram display names for a list of user IDs with caching."""
        if not user_ids:
            return {}

        unique_ids = list(dict.fromkeys(user_ids))
        results: Dict[int, str] = {}
        to_fetch: List[int] = []

        for user_id in unique_ids:
            cache_key = (chat_id, user_id)
            cached = self._member_display_cache.get(cache_key)
            if cached is not None:
                results[user_id] = cached
            else:
                to_fetch.append(user_id)

        fetch_tasks = []
        for user_id in to_fetch:
            fetch_tasks.append(self._fetch_user_display(bot, chat_id, user_id))

        if fetch_tasks:
            fetch_results = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            for user_id, fetch_result in zip(to_fetch, fetch_results):
                if isinstance(fetch_result, Exception):
                    logger.debug("Failed to resolve user %s in chat %s: %s", user_id, chat_id, fetch_result)
                    display = str(user_id)
                else:
                    display = fetch_result
                results[user_id] = display
                self._member_display_cache[(chat_id, user_id)] = display

        return results

    async def _fetch_user_display(self, bot: Bot, chat_id: int, user_id: int) -> str:
        """Fetch a display string for a user, falling back gracefully."""
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            tg_user = member.user
            display_name = tg_user.full_name or tg_user.username or str(user_id)
            if tg_user.username:
                display_name = f"{tg_user.full_name or tg_user.username} (@{tg_user.username})"
            return display_name
        except TelegramBadRequest:
            pass

        try:
            chat = await bot.get_chat(user_id)
            display_name = chat.full_name or getattr(chat, "username", None) or str(user_id)
            username = getattr(chat, "username", None)
            if username:
                display_name = f"{chat.full_name or username} (@{username})"
            return display_name
        except TelegramBadRequest:
            return str(user_id)

    async def _resolve_chart_bot_display(self, bot: Bot, user_id: int) -> Optional[str]:
        """Resolve a readable label for the configured chart bot."""
        cached = self._chart_bot_cache.get(user_id)
        if cached is not None:
            return cached

        try:
            chat = await bot.get_chat(user_id)
        except TelegramBadRequest as exc:
            logger.debug("Unable to resolve chart bot %s: %s", user_id, exc)
            self._chart_bot_cache[user_id] = None  # cache miss to avoid repeated calls
            return None

        username = getattr(chat, "username", None)
        full_name = getattr(chat, "full_name", None)
        if username:
            display = f"@{username}"
        elif full_name:
            display = full_name
        else:
            display = str(user_id)

        self._chart_bot_cache[user_id] = display
        return display

    def _summaries_for_menu(self, grouped: OrderedDict[int, Dict[str, Any]], userbot_lookup: Dict[int, str]) -> List[Dict[str, Any]]:
        """Prepare condensed entries for the main menu keyboard."""
        entries: List[Dict[str, Any]] = []
        for entry in grouped.values():
            user_count = sum(1 for record in entry["records"] if record.get("user_id") is not None)
            token_sum = entry.get("token_sum", 0)
            userbot_id = entry.get("assigned_userbot_id")
            userbot_label = userbot_lookup.get(userbot_id) if userbot_id else None
            sensitivity_pct = entry.get("sensitivity_pct")
            is_enabled = entry.get("is_enabled", True)
            use_management_bot = entry.get("use_management_bot", False)

            status_icon = "🟢" if is_enabled else "⛔️"
            name = entry.get("display_name") or f"{entry['chat_type'].upper()} {entry['chat_id']}"

            meta_parts: List[str] = []
            if token_sum:
                meta_parts.append(f"{token_sum} tok")
            if entry["chat_type"] == "group":
                meta_parts.append(f"{user_count} user" + ("s" if user_count != 1 else ""))
            if use_management_bot:
                meta_parts.append("🛰 mgmt")
            elif userbot_label:
                meta_parts.append(f"🤖 {userbot_label}")
            if sensitivity_pct is not None:
                try:
                    pct_value = float(sensitivity_pct) * 100
                    meta_parts.append(f"+{pct_value:.0f}%")
                except (TypeError, ValueError):
                    pass

            button_text = f"{status_icon} {name}"
            if meta_parts:
                button_text = f"{button_text} | {' | '.join(meta_parts)}"

            entries.append({
                "chat_id": entry["chat_id"],
                "chat_type": entry["chat_type"],
                "token_sum": token_sum,
                "user_count": user_count,
                "userbot_label": userbot_label,
                "sensitivity_pct": sensitivity_pct,
                "is_enabled": is_enabled,
                "use_management_bot": use_management_bot,
                "button_text": button_text[:64] if len(button_text) > 64 else button_text,
            })
        return entries

    def _format_sources_overview(
        self,
        grouped: OrderedDict[int, Dict[str, Any]],
        userbot_lookup: Dict[int, str],
        target_lookup: Dict[int, str],
    ) -> str:
        """Build the overview text for the monitored sources menu."""
        if not grouped:
            return (
                "<b>📈 Gain Alerts – Monitored Sources</b>\n\n"
                "No chats or users are being monitored yet.\n\n"
                "Add a monitored source to start triggering gain alerts when "
                "contract addresses appear in tracked conversations."
            )

        total_sources = sum(len(entry["records"]) for entry in grouped.values())
        total_tokens = sum(entry["token_sum"] for entry in grouped.values())
        disabled_count = sum(1 for entry in grouped.values() if not entry.get("is_enabled", True))

        lines = [
            "<b>📈 Gain Alerts – Monitored Sources</b>",
            "",
            f"Tracking {total_sources} source(s) across {total_tokens} token baseline(s):",
            "",
        ]
        if disabled_count:
            lines.append(f"⚠️ {disabled_count} source(s) currently disabled.")
            lines.append("")

        type_icons = {
            "group": "👥",
            "channel": "📢",
            "dm": "💬",
        }

        for info in grouped.values():
            chat_id = info["chat_id"]
            chat_type = info["chat_type"]
            is_enabled = info.get("is_enabled", True)
            icon = type_icons.get(chat_type, "❔")
            chat_label = self._chat_label({"chat_id": chat_id, "chat_type": chat_type})
            status = "✅ Enabled" if is_enabled else "⛔️ Disabled"
            name = info.get("display_name")
            if name:
                lines.append(f"{icon} {chat_label} — <b>{name}</b>")
            else:
                lines.append(f"{icon} {chat_label}")
            lines.append(f"  • {status}")

            sensitivity_pct = info.get("sensitivity_pct")
            if sensitivity_pct is not None:
                try:
                    pct_value = float(sensitivity_pct) * 100
                    lines.append(f"  • Gain sensitivity: +{pct_value:.0f}%")
                except (TypeError, ValueError):
                    pass

            userbot_id = info.get("assigned_userbot_id")
            if userbot_id:
                userbot_label = userbot_lookup.get(userbot_id, f"Userbot {userbot_id}")
                lines.append(f"  • Userbot: {userbot_label}")

            target_ids = info.get("target_chat_ids") or []
            if target_ids:
                target_display_parts = []
                for tid in target_ids[:5]:
                    label = target_lookup.get(tid, str(tid))
                    target_display_parts.append(label)
                target_display = ", ".join(target_display_parts)
                if len(target_ids) > 5:
                    target_display += f", +{len(target_ids) - 5} more"
                lines.append(f"  • Targets: {target_display}")

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

        lines.append("Use the buttons below to add or manage monitored sources.")
        return "\n".join(lines)

    def _format_source_detail(
        self,
        entry: Dict[str, Any],
        userbot_lookup: Dict[int, str],
        target_lookup: Dict[int, str],
        user_display_map: Optional[Dict[int, str]] = None,
        chart_bot_display: Optional[str] = None,
    ) -> str:
        """Render detailed information for a single monitored chat."""
        _ = target_lookup  # maintained for backward compatibility
        chat_type = entry["chat_type"]
        chat_label = self._chat_label(entry)
        token_sum = entry.get("token_sum", 0)
        is_enabled = entry.get("is_enabled", True)
        display_name = entry.get("display_name")
        sensitivity_pct = entry.get("sensitivity_pct")
        userbot_id = entry.get("assigned_userbot_id")

        type_icons = {
            "group": "👥",
            "channel": "📢",
            "dm": "💬",
        }
        icon = type_icons.get(chat_type, "❔")

        lines: List[str] = [
            "<b>🌙 Gain Alerts – Source Detail</b>",
            "",
            f"{icon} {chat_label}",
        ]
        if display_name:
            lines.append(f"Alias: <b>{display_name}</b>")
        lines.append("")

        lines.append("<b>Status</b>")
        lines.append(f"• {'✅ Enabled' if is_enabled else '⛔️ Disabled'}")
        lines.append(f"• Tracked tokens: {token_sum}")
        lines.append("")

        lines.append("<b>Gain Settings</b>")
        if sensitivity_pct is not None:
            try:
                pct_value = float(sensitivity_pct) * 100
                lines.append(f"• Custom sensitivity: +{pct_value:.0f}%")
            except (TypeError, ValueError):
                lines.append("• Custom sensitivity: <i>invalid value</i>")
        else:
            lines.append("• Using global gain sensitivity")
        lines.append("")

        lines.append("<b>Sender</b>")
        if entry.get("use_management_bot"):
            lines.append("• Management bot")
        elif userbot_id:
            userbot_label = userbot_lookup.get(userbot_id, f"Userbot {userbot_id}")
            lines.append(f"• Userbot: {userbot_label}")
        else:
            lines.append("• Pooled userbot (first available)")
        lines.append("")

        chart_enabled = bool(entry.get("chart_enabled"))
        chart_bot_id = entry.get("chart_bot_id")
        chart_threshold = entry.get("chart_mc_threshold")

        lines.append("<b>Chart Alerts</b>")
        lines.append(f"• Status: {'✅ Enabled' if chart_enabled else '⛔️ Disabled'}")
        if chart_threshold is None:
            lines.append(f"• MC Threshold: {self._format_chart_threshold(self.DEFAULT_CHART_THRESHOLD)} (default)")
        else:
            lines.append(f"• MC Threshold: {self._format_chart_threshold(chart_threshold)}")

        if chart_bot_id:
            bot_id_int = int(chart_bot_id)
            if chart_bot_display:
                lines.append(f"• Chart Bot: {chart_bot_display} (ID: {bot_id_int})")
            else:
                lines.append(f"• Chart Bot ID: {bot_id_int}")
        else:
            lines.append("• Chart Bot: Not configured")
        
        # Display the last guardrail evaluation result
        last_guardrail_result = entry.get("last_guardrail_result")
        if last_guardrail_result:
            passed = last_guardrail_result.get("passed", False)
            checks_passed = last_guardrail_result.get("checks_passed", 0)
            total_checks = last_guardrail_result.get("total_checks", 0)
            lines.append(f"• Last Guardrail Eval: {'✅ PASS' if passed else '❌ FAIL'} ({checks_passed}/{total_checks} checks passed)")
        else:
            lines.append("• Last Guardrail Eval: N/A (no evaluations yet)")
        lines.append("")

        template_text = entry.get("template_text")
        preview = html.escape(template_text) if template_text else None
        lines.append("<b>Alert Template</b>")
        if template_text:
            lines.append("• Custom override in use")
            lines.append("")
            lines.append("<b>Preview</b>")
            lines.append(f"<code>{preview}</code>")
        else:
            lines.append("• Using global template")
        lines.append("")

        if chat_type == "group":
            lines.append("<b>Monitored Users</b>")
            records = entry.get("records", [])
            if records:
                for record in records[:10]:
                    user_id = int(record.get("user_id") or 0)
                    token_count = int(record.get("token_count") or 0)
                    display = user_display_map.get(user_id) if user_display_map else None
                    if not display:
                        display = str(user_id)
                    lines.append(f"• {display} <code>{user_id}</code> – {token_count} token(s)")
                if len(records) > 10:
                    lines.append(f"• …and {len(records) - 10} more")
            else:
                lines.append("• None configured yet")
            lines.append("")
            lines.append("Use the buttons below to manage monitored users.")
        else:
            scope = "All messages" if chat_type in {"channel", "dm"} else "Custom scope"
            lines.append("<b>Scope</b>")
            lines.append(f"• {scope}")
            lines.append("")
            lines.append("Use the button below to remove this monitored source.")

        return "\n".join(lines)

    def _format_chart_threshold(self, raw_value: Any) -> str:
        """Format a market-cap threshold with thousands separators."""
        try:
            decimal_value = Decimal(str(raw_value))
        except (InvalidOperation, TypeError, ValueError):
            return f"${raw_value}"

        decimal_value = decimal_value.quantize(Decimal("0.01"))
        formatted = format(decimal_value, ",.2f")
        if formatted.endswith(".00"):
            formatted = formatted[:-3]
        return f"${formatted}"

    async def _build_chart_settings_view(
        self,
        entry: Dict[str, Any],
        chart_bot_display: Optional[str],
    ) -> Tuple[str, InlineKeyboardMarkup]:
        """Construct text and keyboard for the chart settings menu."""
        chat_id = entry["chat_id"]
        chart_enabled = bool(entry.get("chart_enabled"))
        threshold = entry.get("chart_mc_threshold")
        chart_bot_id = entry.get("chart_bot_id")

        threshold_text = (
            f"{self._format_chart_threshold(self.DEFAULT_CHART_THRESHOLD)} <i>(default)</i>"
            if threshold is None
            else self._format_chart_threshold(threshold)
        )

        # Basic settings section
        lines = [
            "<b>📊 Chart Alert Settings</b>",
            "━━━━━━━━━━━━━━━━━━━━",
            "",
            f"<b>Status:</b> {'✅ Enabled' if chart_enabled else '⛔️ Disabled'}",
            f"<b>MC Threshold:</b> {threshold_text}",
        ]

        if chart_bot_id:
            bot_id_int = int(chart_bot_id)
            if chart_bot_display:
                lines.append(f"<b>Chart Bot:</b> {chart_bot_display}")
            else:
                lines.append(f"<b>Chart Bot:</b> ID {bot_id_int}")
        else:
            lines.append("<b>Chart Bot:</b> <i>Not configured</i>")

        # Guardrails section
        lines.extend([
            "",
            "<b>🛡️ Chart Guardrails</b>",
            "━━━━━━━━━━━━━━━━━━━━",
        ])

        global_guardrails = await get_chart_guardrails()

        # Metric display names with emojis
        metric_labels = {
            "min_age_minutes": "⏰ Token Age",
            "min_liquidity_usd": "💧 Liquidity",
            "min_volume_usd": "📊 Volume",
            "min_multiplier": "📈 Multiplier",
            "max_price_change_pct": "⚡ Price Stability",
            "checks_required": "✅ Checks Required",
        }

        # Parse last guardrail result for per-metric status
        last_result = entry.get("last_guardrail_result")
        metric_status = {}
        if last_result and isinstance(last_result, dict):
            checks = last_result.get("checks", [])
            for check in checks:
                metric_name = check.get("name")
                if metric_name:
                    metric_status[metric_name] = {
                        "passed": check.get("passed", False),
                        "actual": check.get("actual_value"),
                        "threshold": check.get("threshold_value"),
                        "reason": check.get("reason")
                    }

        for metric in self.GUARDRAIL_METRICS:
            metric_label = metric_labels.get(metric, metric.replace("_", " ").title())
            value_str = self._format_guardrail_value(entry, global_guardrails, metric)
            lines.append(f"  {metric_label}: {value_str}")

            # Add last check result if available
            if metric in metric_status:
                status = metric_status[metric]
                if status["passed"]:
                    lines.append(f"     └ 🟢 Last check passed")
                else:
                    reason = status.get("reason", "Failed")
                    lines.append(f"     └ 🔴 {reason}")

        lines.extend([
            "",
            "<i>💡 Tip: Set overrides to customize this source</i>",
        ])

        keyboard = self._build_chart_settings_keyboard(chat_id, chart_enabled, entry, global_guardrails)
        return "\n".join(lines), keyboard

    def _build_chart_settings_keyboard(self, chat_id: int, enabled: bool, entry: Dict[str, Any], global_guardrails: Dict[str, Any]) -> InlineKeyboardMarkup:
        """Inline keyboard for chart settings menu."""
        # Basic settings row
        toggle_text = "⛔️ Disable" if enabled else "✅ Enable"
        keyboard = [
            [
                InlineKeyboardButton(
                    text=toggle_text,
                    callback_data=f"gain_alerts:view:chart_toggle:{chat_id}"
                ),
                InlineKeyboardButton(
                    text="💰 MC Threshold",
                    callback_data=f"gain_alerts:view:chart_threshold:{chat_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Chart Bot ID",
                    callback_data=f"gain_alerts:view:chart_bot:{chat_id}"
                )
            ],
        ]

        # Guardrails section with compact labels
        metric_labels = {
            "min_age_minutes": "⏰ Token Age",
            "min_liquidity_usd": "💧 Liquidity",
            "min_volume_usd": "📊 Volume",
            "min_multiplier": "📈 Multiplier",
            "max_price_change_pct": "⚡ Stability",
            "checks_required": "✅ Checks",
        }

        for metric in self.GUARDRAIL_METRICS:
            metric_label = metric_labels.get(metric, metric.replace("_", " ").title())
            override = entry.get(f"chart_{metric}")

            # Show ✏️ if has override, otherwise just the label
            edit_text = f"{metric_label} ✏️" if override is not None else metric_label

            keyboard.append([
                InlineKeyboardButton(
                    text=edit_text,
                    callback_data=f"gain_alerts:edit_override:{chat_id}:{metric}"
                ),
                InlineKeyboardButton(
                    text="↩️ Reset",
                    callback_data=f"gain_alerts:reset_override:{chat_id}:{metric}"
                ) if override is not None else InlineKeyboardButton(text="—", callback_data="noop")
            ])

        keyboard.append([InlineKeyboardButton(
            text="🔙 Back",
            callback_data=f"gain_alerts:view:{chat_id}"
        )])

        return InlineKeyboardMarkup(inline_keyboard=keyboard)

    def _build_source_detail_keyboard(self, entry: Dict[str, Any], userbot_lookup: Dict[int, str]) -> InlineKeyboardMarkup:
        """Construct inline keyboard for source detail view."""
        rows: List[List[InlineKeyboardButton]] = []
        chat_id = entry["chat_id"]
        chat_type = entry["chat_type"]
        is_enabled = entry.get("is_enabled", True)
        userbot_id = entry.get("assigned_userbot_id")
        userbot_label = userbot_lookup.get(userbot_id) if userbot_id else None
        use_management_bot = entry.get("use_management_bot", False)
        rows.append([
            InlineKeyboardButton(
                text="✏️ Edit Name",
                callback_data=f"gain_alerts:view:edit_name:{chat_id}"
            ),
            InlineKeyboardButton(
                text="⏸ Disable Alerts" if is_enabled else "▶️ Enable Alerts",
                callback_data=f"gain_alerts:view:toggle:{chat_id}"
            )
        ])

        rows.append([
            InlineKeyboardButton(
                text="🎯 Edit Sensitivity",
                callback_data=f"gain_alerts:view:sensitivity:{chat_id}"
            )
        ])

        rows.append([
            InlineKeyboardButton(
                text="📝 Edit Template",
                callback_data=f"gain_alerts:view:template:{chat_id}"
            )
        ])

        rows.append([
            InlineKeyboardButton(
                text="📊 Chart Settings",
                callback_data=f"gain_alerts:view:chart_settings:{chat_id}"
            )
        ])

        if use_management_bot:
            sender_label = "🛰 Sender: Management Bot"
        elif userbot_label:
            sender_label = f"🤖 Sender: {userbot_label}"
        else:
            sender_label = "🤖 Assign Sender"

        rows.append([
            InlineKeyboardButton(
                text=sender_label,
                callback_data=f"gain_alerts:view:userbot:{chat_id}"
            )
        ])

        if chat_type == "group":
            rows.append([
                InlineKeyboardButton(
                    text="👥 View Tracked Users",
                    callback_data=f"gain_alerts:view:tracked:{chat_id}"
                )
            ])

        rows.append([
            InlineKeyboardButton(
                text="🗑️ Delete Source",
                callback_data=f"gain_alerts:view:remove_chat:{chat_id}"
            )
        ])

        rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="gain_alerts:menu")])
        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _build_sensitivity_menu_keyboard(self, chat_id: int) -> InlineKeyboardMarkup:
        """Inline keyboard presenting preset sensitivity overrides."""
        presets = [Decimal("0.20"), Decimal("0.40"), Decimal("0.60")]
        rows: List[List[InlineKeyboardButton]] = []

        for preset in presets:
            percent = int(preset * 100)
            value_str = format(preset.normalize(), "f")
            rows.append([
                InlineKeyboardButton(
                    text=f"+{percent}%",
                    callback_data=f"gain_alerts:view:sensitivity:set:{chat_id}:{value_str}"
                )
            ])

        rows.append([
            InlineKeyboardButton(
                text="♻️ Use Global Default",
                callback_data=f"gain_alerts:view:sensitivity:set:{chat_id}:default"
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="✏️ Custom Percentage",
                callback_data=f"gain_alerts:view:sensitivity:custom:{chat_id}"
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="🔙 Back to Detail",
                callback_data=f"gain_alerts:view:{chat_id}"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _build_userbot_menu_keyboard(
        self,
        chat_id: int,
        userbots: List[Dict[str, Any]],
        current_bot_id: Optional[int],
        use_management_bot: bool,
        page: int,
    ) -> InlineKeyboardMarkup:
        """Build keyboard listing sender options plus reset/back controls with pagination."""
        rows: List[List[InlineKeyboardButton]] = []

        total_userbots = len(userbots)
        page_size = 9
        total_pages = max(1, (total_userbots + page_size - 1) // page_size)
        page = max(1, min(page, total_pages))

        mgmt_prefix = "✅" if use_management_bot else "🛰"
        rows.append([
            InlineKeyboardButton(
                text=f"{mgmt_prefix} Management Bot",
                callback_data=f"gain_alerts:view:userbot:set:{chat_id}:management"
            )
        ])

        status_icons = {
            "active": "🟢",
            "running": "🟢",
            "idle": "🟡",
            "error": "🔴",
        }

        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        for record in userbots[start_index:end_index]:
            bot_id = int(record.get("id"))
            label = record.get("label") or f"Userbot {bot_id}"
            status = (record.get("status") or "").lower()
            icon = status_icons.get(status, "⚪️")
            button_text = f"{icon} {label}"
            if not use_management_bot and current_bot_id == bot_id:
                button_text = f"✅ {label}"

            rows.append([
                InlineKeyboardButton(
                    text=button_text,
                    callback_data=f"gain_alerts:view:userbot:set:{chat_id}:{bot_id}"
                )
            ])

        if use_management_bot:
            rows.append([
                InlineKeyboardButton(
                    text="♻️ Use pooled userbot",
                    callback_data=f"gain_alerts:view:userbot:set:{chat_id}:clear"
                )
            ])
        elif current_bot_id:
            rows.append([
                InlineKeyboardButton(
                    text="♻️ Use pooled userbot",
                    callback_data=f"gain_alerts:view:userbot:set:{chat_id}:clear"
                )
            ])

        if total_pages > 1:
            nav_buttons: List[InlineKeyboardButton] = []
            if page > 1:
                nav_buttons.append(
                    InlineKeyboardButton(
                        text="⬅️ Prev",
                        callback_data=f"gain_alerts:view:userbot:page:{chat_id}:{page-1}"
                    )
                )
            nav_buttons.append(
                InlineKeyboardButton(
                    text=f"{page}/{total_pages}",
                    callback_data="noop"
                )
            )
            if page < total_pages:
                nav_buttons.append(
                    InlineKeyboardButton(
                        text="Next ➡️",
                        callback_data=f"gain_alerts:view:userbot:page:{chat_id}:{page+1}"
                    )
                )
            rows.append(nav_buttons)

        rows.append([
            InlineKeyboardButton(
                text="🔙 Back to Detail",
                callback_data=f"gain_alerts:view:{chat_id}"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=rows)

    def _build_tracked_users_keyboard(
        self,
        chat_id: int,
        records: List[Dict[str, Any]],
        user_display_map: Dict[int, str],
    ) -> InlineKeyboardMarkup:
        """Keyboard for tracked user management."""
        rows: List[List[InlineKeyboardButton]] = []

        for record in records:
            source_id = record.get("id")
            user_id = record.get("user_id")
            if source_id is None or user_id is None:
                continue

            user_id_int = int(user_id)
            display = user_display_map.get(user_id_int, str(user_id_int))
            rows.append([
                InlineKeyboardButton(
                    text=f"🗑️ Remove {display}",
                    callback_data=f"gain_alerts:view:tracked:remove:{source_id}"
                )
            ])

        rows.append([
            InlineKeyboardButton(
                text="➕ Add Monitored User(s)",
                callback_data=f"gain_alerts:view:tracked:add:{chat_id}"
            )
        ])
        rows.append([
            InlineKeyboardButton(
                text="🔙 Back to Detail",
                callback_data=f"gain_alerts:view:{chat_id}"
            )
        ])

        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def _build_tracked_users_view(
        self,
        bot: Optional[Bot],
        chat_id: int,
    ) -> Optional[Tuple[str, InlineKeyboardMarkup]]:
        if bot is None:
            return None

        context = await self._build_detail_context(chat_id, bot)
        if context is None:
            return None

        entry = context["entry"]
        if entry.get("chat_type") != "group":
            return None

        user_map = context.get("user_display_map") or {}
        records_raw = entry.get("records", [])
        records = [dict(record) for record in records_raw]

        lines = [
            "<b>👥 Tracked Users</b>",
            "",
        ]

        if records:
            lines.append("Gain alerts will fire when these members post contract addresses:")
            for record in records:
                user_id = int(record.get("user_id") or 0)
                display = user_map.get(user_id, str(user_id))
                lines.append(f"• {display} <code>{user_id}</code>")
        else:
            lines.append("No specific members are being tracked yet.")

        text = "\n".join(lines)
        keyboard = self._build_tracked_users_keyboard(chat_id, records, user_map)
        return text, keyboard

    async def _render_chart_settings_view(
        self,
        bot: Bot,
        source_chat_id: int,
        detail_chat_id: int,
        detail_message_id: int,
    ) -> None:
        """Re-render the chart settings menu after inline edits."""
        context = await self._build_detail_context(source_chat_id, bot)
        if context is None:
            await bot.edit_message_text(
                text="<b>📊 Chart Alert Settings</b>\n\nMonitored source not found.",
                chat_id=detail_chat_id,
                message_id=detail_message_id,
                parse_mode="HTML",
            )
            return

        text, keyboard = await self._build_chart_settings_view(
            context["entry"],
            context.get("chart_bot_display"),
        )

        try:
            await bot.edit_message_text(
                text=text,
                chat_id=detail_chat_id,
                message_id=detail_message_id,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
        except TelegramBadRequest as exc:
            message = str(exc).lower()
            if "message is not modified" in message:
                logger.debug(
                    "Chart settings for chat %s unchanged; suppressing TelegramBadRequest.",
                    source_chat_id,
                )
                return
            if "message to edit not found" in message:
                logger.debug(
                    "Chart settings message for chat %s no longer exists; treating as refreshed.",
                    source_chat_id,
                )
                return
            logger.warning(
                "Failed to refresh chart settings message for chat %s: %s",
                source_chat_id,
                exc,
            )
            raise

    async def _refresh_detail_message(self, bot, detail_chat_id: int, detail_message_id: int, source_chat_id: int) -> None:
        """Re-render the detail view message after inline edits."""
        context = await self._build_detail_context(source_chat_id, bot)

        try:
            if context is None:
                await bot.edit_message_text(
                    text="<b>📈 Gain Alerts – Monitored Sources</b>\n\nMonitored source not found.",
                    chat_id=detail_chat_id,
                    message_id=detail_message_id,
                    reply_markup=self.keyboards.gain_alerts_main_menu([]),
                    parse_mode="HTML",
                )
                return

            await bot.edit_message_text(
                text=context["text"],
                chat_id=detail_chat_id,
                message_id=detail_message_id,
                reply_markup=context["keyboard"],
                parse_mode="HTML",
            )
        except TelegramBadRequest as exc:
            message = str(exc).lower()
            if "message is not modified" in message:
                logger.debug(
                    "Detail message for chat %s unchanged; suppressing TelegramBadRequest.",
                    source_chat_id,
                )
                return
            if "message to edit not found" in message:
                logger.debug(
                    "Detail message for chat %s no longer exists; treating as refreshed.",
                    source_chat_id,
                )
                return
            logger.warning("Failed to refresh detail message for chat %s: %s", source_chat_id, exc)
            raise

    async def prompt_edit_source_guardrail(self, query: types.CallbackQuery, state: FSMContext, chat_id: int, metric: str) -> None:
        """Prompt admin to set a new value for a specific chart guardrail override."""
        try:
            context = await self._build_detail_context(chat_id, query.bot)
            if context is None:
                await query.answer("Monitored source not found.", show_alert=True)
                return

            entry = context["entry"]

            # Get current value - from either the override or global default
            current_override = entry.get(f"chart_{metric}")
            global_guardrails = await get_chart_guardrails()
            global_value = global_guardrails.get(metric, 0)

            # Build prompt based on metric (matching global settings style)
            if metric == "min_age_minutes":
                current_val = int(current_override) if current_override is not None else int(global_value)
                override_note = " <i>(override)</i>" if current_override is not None else " <i>(global)</i>"
                prompt = f"Enter new minimum age in minutes (e.g., 30 for 30 minutes):\n\nCurrent: {current_val} minutes{override_note}"
            elif metric == "min_liquidity_usd":
                current_val = current_override if current_override is not None else global_value
                override_note = " <i>(override)</i>" if current_override is not None else " <i>(global)</i>"
                prompt = f"Enter new minimum liquidity in USD (e.g., 5000 for $5,000):\n\nCurrent: {self._format_guardrail_currency(current_val)}{override_note}"
            elif metric == "min_volume_usd":
                current_val = current_override if current_override is not None else global_value
                override_note = " <i>(override)</i>" if current_override is not None else " <i>(global)</i>"
                prompt = f"Enter new minimum 24h volume in USD (e.g., 10000 for $10,000):\n\nCurrent: {self._format_guardrail_currency(current_val)}{override_note}"
            elif metric == "min_multiplier":
                current_val = current_override if current_override is not None else global_value
                override_note = " <i>(override)</i>" if current_override is not None else " <i>(global)</i>"
                prompt = f"Enter new minimum multiplier (e.g., 1.5 for 1.5x):\n\nCurrent: x{current_val:.2f}{override_note}"
            elif metric == "max_price_change_pct":
                current_val = current_override if current_override is not None else global_value
                override_note = " <i>(override)</i>" if current_override is not None else " <i>(global)</i>"
                prompt = f"Enter new max price change percentage (e.g., 50 for 50%):\n\nCurrent: {current_val:.1f}%{override_note}"
            elif metric == "checks_required":
                total_checks = len(self.GUARDRAIL_METRICS)
                current_val = int(current_override) if current_override is not None else int(global_value)
                override_note = " <i>(override)</i>" if current_override is not None else " <i>(global)</i>"
                prompt = f"Enter how many checks must pass (1 to {total_checks}):\n\n0 or {total_checks} = All must pass\n\nCurrent: {self._describe_guardrail_strategy(current_val, total_checks)}{override_note}"
            else:
                await query.answer("Unknown metric.", show_alert=True)
                return

            # Setup state for the edit operation
            await state.clear()
            await state.set_state(ManagementStates.awaiting_source_guardrail_override)
            await state.update_data(
                chat_id=chat_id,
                metric=metric,
                detail_chat_id=query.message.chat.id,
                detail_message_id=query.message.message_id,
            )

            await query.message.edit_text(
                f"<b>📊 Edit Chart Guardrail Override</b>\n\n{prompt}\n\n<i>Type 'clear' to remove override</i>",
                reply_markup=self.keyboards.cancel_button(f"gain_alerts:chart_settings:cancel:{chat_id}"),
                parse_mode="HTML",
            )
            await query.answer()
        except Exception as exc:
            logger.error("Error starting guardrail override editor for %s metric %s: %s", chat_id, metric, exc, exc_info=True)
            await query.answer("❌ Failed to start guardrail editor", show_alert=True)

    async def save_source_guardrail(self, message: types.Message, state: FSMContext) -> None:
        """Validate and save the new guardrail override value."""
        try:
            data = await state.get_data()
            chat_id = data.get("chat_id")
            metric = data.get("metric")

            if not chat_id or not metric:
                await message.answer("Error: Could not determine which setting to update.")
                await state.clear()
                return

            raw_value = message.text.strip() if message.text else ""

            # Check for clear command
            if raw_value.lower() == "clear":
                await self.db.execute(
                    f"UPDATE monitored_sources SET chart_{metric} = NULL WHERE chat_id = $1",
                    chat_id
                )
                await message.answer(f"✅ Guardrail '{metric.replace('_', ' ').title()}' override cleared.")
            else:
                # Validate and parse value (matching settings handler logic)
                if metric in ("min_age_minutes", "checks_required"):
                    value = int(raw_value)
                else:
                    value = float(raw_value.replace("$", "").replace(",", ""))

                # Save the override
                await self.db.execute(
                    f"UPDATE monitored_sources SET chart_{metric} = $1 WHERE chat_id = $2",
                    value,
                    chat_id
                )
                await message.answer(f"✅ Guardrail '{metric.replace('_', ' ').title()}' override updated.")

            await state.clear()

            # Refresh chart settings view
            detail_chat_id = data.get("detail_chat_id")
            detail_message_id = data.get("detail_message_id")
            if detail_chat_id and detail_message_id:
                await self._render_chart_settings_view(
                    message.bot,
                    source_chat_id=chat_id,
                    detail_chat_id=detail_chat_id,
                    detail_message_id=detail_message_id,
                )

        except (ValueError, TypeError):
            await message.answer("❌ Invalid input. Please enter a valid number.")
        except Exception as exc:
            logger.error("Error saving guardrail override: %s", exc, exc_info=True)
            await message.answer("❌ Error saving setting.")

    async def reset_source_guardrail(self, query: types.CallbackQuery, chat_id: int, metric: str) -> None:
        """Clear the override value for a specific chart guardrail."""
        try:
            # Clear the override by setting it to NULL
            await self.db.execute(
                f"UPDATE monitored_sources SET chart_{metric} = NULL WHERE chat_id = $1",
                chat_id
            )

            await query.answer(f"✅ Override cleared", show_alert=False)

            # Refresh the chart settings view
            context = await self._build_detail_context(chat_id, query.bot)
            if context is not None:
                text, keyboard = await self._build_chart_settings_view(
                    context["entry"],
                    context.get("chart_bot_display"),
                )

                await query.message.edit_text(
                    text,
                    reply_markup=keyboard,
                    parse_mode="HTML",
                )
        except Exception as exc:
            logger.error("Error resetting guardrail override for %s metric %s: %s", chat_id, metric, exc, exc_info=True)
            await query.answer("❌ Failed to reset override", show_alert=True)

    def _format_guardrail_value_for_input(self, metric: str, value: Any, is_override: bool = True) -> str:
        """Format a guardrail value for display in prompts."""
        try:
            if metric == "min_age_minutes":
                return f"{int(value)} min"
            elif metric in ("min_liquidity_usd", "min_volume_usd"):
                try:
                    decimal_value = Decimal(str(value))
                except (InvalidOperation, TypeError, ValueError):
                    return f"${value}"
                
                decimal_value = decimal_value.quantize(Decimal("0.01"))
                formatted = format(decimal_value, ",.2f")
                if formatted.endswith(".00"):
                    formatted = formatted[:-3]
                return f"${formatted}"
            elif metric == "min_multiplier":
                return f"x{float(value):.2f}"
            elif metric == "max_price_change_pct":
                return f"{float(value):.1f}%"
            elif metric == "checks_required":
                if value == 0:
                    return "All checks (0)"
                else:
                    total_checks = len(self.GUARDRAIL_METRICS)
                    return f"Any {int(value)} of {total_checks}"
            else:
                return str(value)
        except:
            return str(value)

    async def parse_guardrail_value(self, metric: str, raw_input: str) -> Optional[Any]:
        """Parse a raw input string into the appropriate guardrail value type."""
        try:
            raw_input = raw_input.strip()
            
            if metric == "min_age_minutes":
                # Parse as integer (minutes)
                return int(float(raw_input))  # Convert through float to handle decimal inputs like "5.0"
            elif metric in ("min_liquidity_usd", "min_volume_usd"):
                # Parse as numeric value, allow k/m/b suffixes
                cleaned = raw_input.lower().replace(",", "").replace("_", "")
                multiplier = Decimal("1")
                
                if cleaned.endswith("k"):
                    multiplier = Decimal("1000")
                    cleaned = cleaned[:-1]
                elif cleaned.endswith("m"):
                    multiplier = Decimal("1000000")
                    cleaned = cleaned[:-1]
                elif cleaned.endswith("b"):
                    multiplier = Decimal("1000000000")
                    cleaned = cleaned[:-1]
                
                cleaned = cleaned.strip()
                if cleaned.startswith("$"):
                    cleaned = cleaned[1:]
                
                decimal_value = Decimal(cleaned) * multiplier
                return float(decimal_value)
            elif metric == "min_multiplier":
                # Parse as float
                return float(raw_input)
            elif metric == "max_price_change_pct":
                # Parse as float, remove % if present
                cleaned = raw_input.replace("%", "").strip()
                return float(cleaned)
            elif metric == "checks_required":
                # Parse as integer
                value = int(float(raw_input))
                # Validate it's between 0 and 5 (the actual number of checks)
                if value < 0 or value > 5:
                    return None
                return value
            else:
                return None
        except (ValueError, InvalidOperation):
            return None

    async def validate_guardrail_value(self, metric: str, value: Any) -> bool:
        """Validate a guardrail value against business rules."""
        try:
            if metric == "min_age_minutes":
                return value >= 0
            elif metric in ("min_liquidity_usd", "min_volume_usd"):
                return value >= 0
            elif metric == "min_multiplier":
                return value >= 1.0
            elif metric == "max_price_change_pct":
                return 0 <= value <= 100
            elif metric == "checks_required":
                # 0 means all checks, 1-5 means number of checks that must pass
                return 0 <= value <= 5
            else:
                return False
        except (TypeError, ValueError):
            return False

    async def save_guardrail_override(self, chat_id: int, metric: str, value: Optional[Any]) -> None:
        """Save a guardrail override to the database."""
        # Map the metric name to the database column name
        column_name = f"chart_{metric}"
        
        # Update all source records for this chat ID
        query = f"""
            UPDATE monitored_sources 
            SET {column_name} = $1 
            WHERE chat_id = $2
        """
        async with self.db.acquire() as conn:
            await conn.execute(query, value, chat_id)

    def _show_add_entry_summary(self, data: Dict[str, Any]) -> str:
        """Generate confirmation summary text."""
        chat_label = self._chat_label(data)
        user_part = ""
        if data.get("chat_type") == "group":
            user_ids: List[int] = []
            if data.get("user_ids"):
                user_ids = [int(uid) for uid in data["user_ids"]]
            elif data.get("user_id") is not None:
                user_ids = [int(data["user_id"])]

            if len(user_ids) == 1:
                user_part = f"\nMonitor User ID: <code>{user_ids[0]}</code>"
            else:
                formatted_ids = "\n".join(f"• <code>{uid}</code>" for uid in user_ids)
                user_part = "\nMonitor User IDs:\n" + formatted_ids

            skipped: List[int] = [int(uid) for uid in data.get("skipped_user_ids") or []]
            if skipped:
                skipped_lines = "\n".join(f"• <code>{uid}</code>" for uid in skipped)
                user_part += "\n\n⚠️ Skipping already monitored IDs:\n" + skipped_lines
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
    def _parse_int_list(raw: Optional[str]) -> List[int]:
        """Convert text containing integers into a list."""
        if raw is None:
            return []

        parts = [part.strip() for part in re.split(r"[,\s]+", raw) if part.strip()]
        values: List[int] = []
        for part in parts:
            if not part:
                continue
            try:
                values.append(int(part))
            except ValueError:
                return []
        return values

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
