"""
Command forwarding routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register command forwarding handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.cmd_fwd_handler.handle_cmd_fwd_action,
        F.data.startswith("cmd_fwd:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.wizard_process_command_input,
        ManagementStates.cmd_fwd_add_rule_command,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.wizard_process_user_id_input,
        ManagementStates.cmd_fwd_add_monitored_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.wizard_process_destination_input,
        ManagementStates.cmd_fwd_add_rule_destination,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.wizard_process_user_id_input,
        ManagementStates.cmd_fwd_add_replying_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.wizard_process_custom_interval_input,
        ManagementStates.cmd_fwd_add_rule_custom_interval,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.process_edit_command_input,
        ManagementStates.cmd_fwd_edit_command,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.cmd_fwd_handler.process_excluded_text_input,
        ManagementStates.cmd_fwd_add_excluded_text,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
