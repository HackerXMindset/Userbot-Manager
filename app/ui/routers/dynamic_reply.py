"""
Dynamic reply routing module.
"""

from aiogram import Dispatcher, F, types

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register dynamic reply handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.dynamic_reply_handler.show_menu,
        F.data == "dynamic_reply:menu",
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.dynamic_reply_handler.start_add_reply,
        F.data == "dynamic_reply:add",
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    async def show_reply_list_callback(query: types.CallbackQuery) -> None:
        parts = query.data.split(":")
        page = int(parts[2]) if len(parts) > 2 else 1
        await manager.dynamic_reply_handler.show_reply_list(query, page)

    dispatcher.callback_query.register(
        show_reply_list_callback,
        F.data.startswith("dynamic_reply:list"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    async def delete_reply_callback(query: types.CallbackQuery) -> None:
        reply_id = int(query.data.split(":")[-1])
        await manager.dynamic_reply_handler.delete_reply(query, reply_id)

    dispatcher.callback_query.register(
        delete_reply_callback,
        F.data.startswith("dynamic_reply:delete:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.dynamic_reply_handler.process_add_reply,
        ManagementStates.adding_dynamic_reply_message,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
