"""
Notifications routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register notification handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.notifications_handler.handle_notifications_action,
        F.data.startswith("notifications:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.notifications_handler.process_notification_channel_input,
        ManagementStates.setting_notification_channel,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.notifications_handler.process_blacklist_input,
        ManagementStates.adding_blacklist_user,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
