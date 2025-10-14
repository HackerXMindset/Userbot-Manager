"""
Auto-click routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register auto-click handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.auto_click_handler.wizard_process_dynamic_target,
        F.data.startswith("auto_click_dynamic_wizard:target:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.auto_click_handler.wizard_toggle_dynamic_userbot,
        F.data.startswith("auto_click_dynamic_wizard:toggle_userbot:"),
        ManagementStates.adding_dynamic_click_rule_userbot,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.auto_click_handler.wizard_toggle_dynamic_userbot,
        F.data.startswith("auto_click_dynamic_wizard:toggle_userbot:"),
        ManagementStates.editing_dynamic_click_rule_userbots,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.auto_click_handler.wizard_save_dynamic_rule,
        F.data == "auto_click_dynamic_wizard:userbots_done",
        ManagementStates.adding_dynamic_click_rule_userbot,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.auto_click_handler.process_edit_dynamic_userbots,
        F.data == "auto_click_dynamic_wizard:userbots_done",
        ManagementStates.editing_dynamic_click_rule_userbots,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.auto_click_handler.wizard_process_target_group,
        F.data.startswith("auto_click_wizard:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.auto_click_handler.handle_auto_click_action,
        F.data.startswith("auto_click:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.wizard_process_bot_id,
        ManagementStates.adding_auto_click_rule_bot_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.wizard_process_button_text,
        ManagementStates.adding_auto_click_rule_button_text,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.wizard_process_dynamic_user_id,
        ManagementStates.adding_dynamic_click_rule_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.wizard_process_dynamic_buttons,
        ManagementStates.adding_dynamic_click_rule_buttons,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.process_edit_dynamic_user,
        ManagementStates.editing_dynamic_click_rule_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.process_edit_dynamic_buttons,
        ManagementStates.editing_dynamic_click_rule_buttons,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.process_edit_dynamic_buttons,
        ManagementStates.editing_dynamic_click_rule_buttons,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.process_edit_name,
        ManagementStates.editing_auto_click_rule_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.auto_click_handler.process_edit_ticker,
        ManagementStates.editing_dynamic_rule_ticker,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
