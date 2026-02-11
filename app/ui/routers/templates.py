"""
Templates routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register template handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.templates_handler.handle_templates_action,
        F.data.startswith(("templates:", "templates_page:", "templates_assign_page:")),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.templates_handler.wizard_process_name,
        ManagementStates.template_add_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.templates_handler.wizard_process_text,
        ManagementStates.template_add_text,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.templates_handler.wizard_process_edit_name,
        ManagementStates.template_edit_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.templates_handler.wizard_process_edit_text,
        ManagementStates.template_edit_text,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
