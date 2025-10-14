"""
Group management routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register group management handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.groups_handler.handle_group_action,
        F.data.startswith(("group:", "groups_page:")),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.groups_handler.delete_group,
        F.data.startswith("confirm_delete_group:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.groups_handler.process_group_input,
        ManagementStates.adding_group,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.groups_handler.process_group_name_input,
        ManagementStates.group_set_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
