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

    async def cancel_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await handler.cancel(query, state)

    async def confirm_add_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await handler.confirm_add(query, state)

    async def remove_menu_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await handler.start_remove_flow(query)

    async def remove_select_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        parts = query.data.split(":")
        if len(parts) < 4:
            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        try:
            source_id = int(parts[3])
        except ValueError:
            await query.answer("❌ Invalid identifier.", show_alert=True)
            return

        await handler.prompt_remove_confirmation(query, source_id)

    async def remove_confirm_callback(query: types.CallbackQuery, state: FSMContext) -> None:
        parts = query.data.split(":")
        if len(parts) < 4:
            await query.answer("❌ Invalid selection.", show_alert=True)
            return

        try:
            source_id = int(parts[3])
        except ValueError:
            await query.answer("❌ Invalid identifier.", show_alert=True)
            return

        await handler.confirm_remove(query, source_id)

    async def chat_id_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_chat_id_input(message, state)

    async def user_id_message(message: types.Message, state: FSMContext) -> None:
        await handler.handle_user_id_input(message, state)

    # Callback query registrations
    dispatcher.callback_query.register(menu_callback, F.data == "gain_alerts:menu", admin_filter)
    dispatcher.callback_query.register(add_callback, F.data == "gain_alerts:add", admin_filter)
    dispatcher.callback_query.register(type_callback, F.data.startswith("gain_alerts:add:type:"), admin_filter)
    dispatcher.callback_query.register(cancel_callback, F.data == "gain_alerts:cancel", admin_filter)
    dispatcher.callback_query.register(confirm_add_callback, F.data == "gain_alerts:add:confirm", admin_filter)
    dispatcher.callback_query.register(remove_menu_callback, F.data == "gain_alerts:remove", admin_filter)
    dispatcher.callback_query.register(remove_select_callback, F.data.startswith("gain_alerts:remove:select:"), admin_filter)
    dispatcher.callback_query.register(remove_confirm_callback, F.data.startswith("gain_alerts:remove:confirm:"), admin_filter)

    # Message handlers for stateful input
    dispatcher.message.register(chat_id_message, StateFilter(ManagementStates.gain_alerts_add_chat_id), admin_filter)
    dispatcher.message.register(user_id_message, StateFilter(ManagementStates.gain_alerts_add_user_id), admin_filter)

    logger.info("Gain alerts router registered")
