"""
PNL routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register profit-and-loss handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.pnl_handler.handle_pnl_action,
        F.data.startswith("pnl:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.pnl_handler.wizard_process_user_id_input,
        ManagementStates.pnl_add_monitored_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.pnl_handler.wizard_process_destination_input,
        ManagementStates.pnl_add_rule_destination,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.pnl_handler.wizard_process_user_id_input,
        ManagementStates.pnl_add_replying_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
