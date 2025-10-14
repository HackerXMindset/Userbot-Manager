"""
Curate Alpha routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register curate alpha handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.curate_alpha_handler.handle_curate_alpha_action,
        F.data.startswith("curate_alpha:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.curate_alpha_handler.wizard_process_name,
        ManagementStates.curate_alpha_add_rule_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.curate_alpha_handler.wizard_process_destination,
        ManagementStates.curate_alpha_set_destination,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.curate_alpha_handler.wizard_process_min_mentions,
        ManagementStates.curate_alpha_set_min_mentions,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.curate_alpha_handler.process_field_edit,
        ManagementStates.curate_alpha_edit_field,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.curate_alpha_handler.process_field_edit,
        ManagementStates.curate_alpha_edit_field,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
