"""
Source management routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register source management handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.sources_handler.handle_sources_action,
        F.data.startswith(("sources:", "add_route_page:", "sources_manage_page:", "routing:")),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.sources_handler.handle_source_group_selection,
        F.data.startswith("source_group:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.sources_handler.handle_source_type_selection,
        F.data.startswith("source_type:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.sources_handler.handle_global_source_type_selection,
        F.data.startswith("source_global_type:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.sources_handler.handle_source_edit,
        F.data.startswith("source_edit:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.sources_handler.process_source_input,
        ManagementStates.adding_source_chat_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.sources_handler.process_user_input,
        ManagementStates.adding_source_user_id,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.sources_handler.process_source_name_input,
        ManagementStates.source_set_name,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.sources_handler.process_route_keywords_input,
        ManagementStates.route_keywords_input,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.sources_handler.process_route_rewrite_input,
        ManagementStates.route_rewrite_input,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
