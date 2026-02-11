"""
Userbot assignment routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register userbot handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.userbots_handler.handle_userbot_assignment,
        F.data.startswith("assign:userbot:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.userbots_handler.handle_userbot_action,
        F.data.startswith(("userbot:", "userbots_page:")),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.userbots_handler.process_phone_input,
        ManagementStates.userbot_login_phone,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.userbots_handler.process_code_input,
        ManagementStates.userbot_login_code,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.userbots_handler.process_2fa_input,
        ManagementStates.userbot_login_2fa,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.userbots_handler.process_userbot_name_input,
        ManagementStates.userbot_set_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
