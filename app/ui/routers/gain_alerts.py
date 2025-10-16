"""
Router bindings for gain alerts management UI.
"""

from __future__ import annotations

import logging

from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

from .context import ManagementRouterContext
from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register gain alert routes with the dispatcher."""
    manager = context.manager
    handler = getattr(manager, "gain_alerts_handler", None)

    if handler is None:
        logger.warning("GainAlertsHandler not available; skipping gain alerts router registration")
        return

    admin_filter = F.from_user.id.in_(context.settings.admin_telegram_ids_list)

    async def menu_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await handler.show_main_menu(query, state)
        await query.answer()

    async def add_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await handler.start_add_flow(query, state)

    async def type_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        parts = query.data.split(":")
        if len(parts) < 4:
            await query.answer("❌ Invalid selection.", show_alert=True)
            return
        chat_type = parts[3]
        await handler.handle_type_selected(query, state, chat_type)

    async def view_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        parts = query.data.split(":")
        if len(parts) < 3:
            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        if len(parts) == 3:
            try:
                chat_id = int(parts[2])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await state.clear()
            await handler.show_source_detail(query, chat_id)
            await query.answer()
            return

        action = parts[2]
        if action == "edit_name":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.start_edit_name(query, state, chat_id)
            return

        if action == "add_users":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.start_add_users_to_group(query, state, chat_id)
            return

        if action == "sensitivity":
            if len(parts) == 4:
                try:
                    chat_id = int(parts[3])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.start_sensitivity_menu(query, chat_id)
                return

            if len(parts) >= 5 and parts[3] == "set":
                try:
                    chat_id = int(parts[4])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                raw_value = parts[5] if len(parts) >= 6 else None
                await handler.set_sensitivity_value(query, chat_id, raw_value)
                return

            if len(parts) >= 5 and parts[3] == "custom":
                try:
                    chat_id = int(parts[4])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.start_sensitivity_custom(query, state, chat_id)
                return

            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        if action == "toggle":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.toggle_source_enabled(query, chat_id)
            return

        if action == "userbot":
            if len(parts) == 4:
                try:
                    chat_id = int(parts[3])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.start_userbot_menu(query, chat_id, page=1)
                return

            if len(parts) >= 5 and parts[3] == "set":
                try:
                    chat_id = int(parts[4])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                raw_bot_id = parts[5] if len(parts) >= 6 else None
                await handler.set_userbot_assignment(query, chat_id, raw_bot_id)
                return

            if len(parts) >= 6 and parts[3] == "page":
                try:
                    chat_id = int(parts[4])
                    page = int(parts[5])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.start_userbot_menu(query, chat_id, page=page)
                return

            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        if action == "template":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.start_edit_template(query, state, chat_id)
            return

        if action == "chart_settings":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.show_chart_settings_menu(query, chat_id)
            return

        if action == "chart_toggle":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.toggle_chart_enabled(query, chat_id)
            return

        if action == "chart_threshold":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.start_edit_chart_threshold(query, state, chat_id)
            return

        if action == "chart_bot":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await handler.start_edit_chart_bot(query, state, chat_id)
            return

        if action == "tracked":
            if len(parts) == 4:
                try:
                    chat_id = int(parts[3])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await state.clear()
                await handler.show_tracked_users_menu(query, chat_id)
                return

            if len(parts) >= 5 and parts[3] == "add":
                try:
                    chat_id = int(parts[4])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.start_add_users_to_group(query, state, chat_id, return_view="tracked")
                return

            if len(parts) >= 5 and parts[3] == "remove":
                try:
                    source_id = int(parts[4])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await state.clear()
                await handler.remove_user_from_group(query, source_id)
                return

            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        if action == "remove_user":
            if len(parts) < 4:
                await query.answer("❌ Invalid selection.", show_alert=True)
                return
            try:
                source_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return

            await state.clear()
            await handler.remove_user_from_group(query, source_id)
            return

        if action == "remove_chat":
            if len(parts) == 4:
                try:
                    chat_id = int(parts[3])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.start_remove_chat(query, chat_id)
                return

            if len(parts) >= 5 and parts[3] == "confirm":
                try:
                    chat_id = int(parts[4])
                except ValueError:
                    await query.answer("❌ Invalid identifier.", show_alert=True)
                    return

                await handler.confirm_remove_chat(query, chat_id)
                return

            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        await query.answer("❌ Invalid selection.", show_alert=True)

    async def cancel_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await handler.cancel(query, state)

    async def confirm_add_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await handler.confirm_add(query, state)

    async def chat_id_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_chat_id_input(message, state)

    async def user_id_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_user_id_input(message, state)

    async def edit_name_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_edit_name_input(message, state)

    async def edit_sensitivity_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_edit_sensitivity_input(message, state)

    async def edit_template_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_edit_template_input(message, state)

    async def chart_groups_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        """Handle chart groups menu callbacks."""
        parts = query.data.split(":")

        if len(parts) == 3 and parts[2] == "menu":
            await handler.show_chart_groups_menu(query)
            return

        if len(parts) == 3 and parts[2] == "add":
            await handler.start_add_chart_group(query, state)
            return

        if len(parts) == 3 and parts[2] == "cancel":
            await handler.cancel_chart_groups(query, state)
            return

        if len(parts) == 4 and parts[2] == "remove":
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid chat ID.", show_alert=True)
                return
            await handler.remove_chart_group(query, chat_id)
            return

        await query.answer("❌ Invalid selection.", show_alert=True)

    async def chart_group_input_message(message: types.Message, state: FSMContext) -> None:
        """Handle chart group chat ID input."""
        await handler.handle_chart_group_input(message, state)

    async def chart_settings_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        """Handle chart settings auxiliary callbacks (e.g., cancel)."""
        parts = query.data.split(":")
        if len(parts) == 4 and parts[2] == "cancel":
            try:
                chat_id = int(parts[3])
            except ValueError:
                await query.answer("❌ Invalid identifier.", show_alert=True)
                return
            await handler.cancel_chart_settings(query, state, chat_id)
            return

        await query.answer("❌ Invalid selection.", show_alert=True)

    async def edit_override_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        """Handle edit override callbacks."""
        parts = query.data.split(":")
        if len(parts) < 4 or parts[1] != "edit_override":
            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        try:
            chat_id = int(parts[2])
            metric = parts[3]
        except (ValueError, IndexError):
            await query.answer("❌ Invalid identifier.", show_alert=True)
            return

        await handler.prompt_edit_source_guardrail(query, state, chat_id, metric)

    async def reset_override_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        """Handle reset override callbacks."""
        parts = query.data.split(":")
        if len(parts) < 4 or parts[1] != "reset_override":
            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        try:
            chat_id = int(parts[2])
            metric = parts[3]
        except (ValueError, IndexError):
            await query.answer("❌ Invalid identifier.", show_alert=True)
            return

        await handler.reset_source_guardrail(query, chat_id, metric)

    async def chart_threshold_message(message: types.Message, state: FSMContext) -> None:
        """Handle chart MC threshold input."""
        await handler.handle_chart_threshold_input(message, state)

    async def chart_bot_message(message: types.Message, state: FSMContext) -> None:
        """Handle chart bot ID input."""
        await handler.handle_chart_bot_input(message, state)

    # Callback query registrations
    dispatcher.callback_query.register(menu_callback, F.data == "gain_alerts:menu", admin_filter)
    dispatcher.callback_query.register(add_callback, F.data == "gain_alerts:add", admin_filter)
    dispatcher.callback_query.register(type_callback, F.data.startswith("gain_alerts:add:type:"), admin_filter)
    dispatcher.callback_query.register(view_callback, F.data.startswith("gain_alerts:view"), admin_filter)
    dispatcher.callback_query.register(cancel_callback, F.data == "gain_alerts:cancel", admin_filter)
    dispatcher.callback_query.register(confirm_add_callback, F.data == "gain_alerts:add:confirm", admin_filter)
    dispatcher.callback_query.register(chart_groups_callback, F.data.startswith("gain_alerts:chart_groups:"), admin_filter)
    dispatcher.callback_query.register(chart_settings_callback, F.data.startswith("gain_alerts:chart_settings:"), admin_filter)
    dispatcher.callback_query.register(edit_override_callback, F.data.startswith("gain_alerts:edit_override:"), admin_filter)
    dispatcher.callback_query.register(reset_override_callback, F.data.startswith("gain_alerts:reset_override:"), admin_filter)

    # Message handlers for stateful input
    dispatcher.message.register(chat_id_message, StateFilter(ManagementStates.gain_alerts_add_chat_id), admin_filter)
    dispatcher.message.register(user_id_message, StateFilter(ManagementStates.gain_alerts_add_user_id), admin_filter)
    dispatcher.message.register(edit_name_message, StateFilter(ManagementStates.gain_alerts_edit_name), admin_filter)
    dispatcher.message.register(edit_sensitivity_message, StateFilter(ManagementStates.gain_alerts_edit_sensitivity), admin_filter)
    dispatcher.message.register(edit_template_message, StateFilter(ManagementStates.gain_alerts_edit_template), admin_filter)
    dispatcher.message.register(chart_group_input_message, StateFilter(ManagementStates.chart_groups_add_chat_id), admin_filter)
    dispatcher.message.register(chart_threshold_message, StateFilter(ManagementStates.gain_alerts_edit_chart_threshold), admin_filter)
    async def save_source_guardrail_message(message: types.Message, state: FSMContext) -> None:
        """Handle guardrail override value input."""
        await handler.save_source_guardrail(message, state)

    dispatcher.message.register(chart_bot_message, StateFilter(ManagementStates.gain_alerts_edit_chart_bot), admin_filter)
    dispatcher.message.register(save_source_guardrail_message, StateFilter(ManagementStates.awaiting_source_guardrail_override), admin_filter)

    logger.info("Gain alerts router registered")
