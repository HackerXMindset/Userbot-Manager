"""
UI Router for Settings
"""

from aiogram import Dispatcher, Router, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery

from app.ui.handlers.settings import SettingsHandler
from app.ui.states import ManagementStates
from app.ui.routers.context import ManagementRouterContext

def setup_settings_router(dispatcher: Dispatcher, context: ManagementRouterContext):
    """Register all handlers for the settings sections."""
    handler = context.settings_handler
    router = Router()

    # Admin filter - only admin users can access settings
    admin_filter = F.from_user.id.in_(context.settings.admin_telegram_ids_list)

    # Register handlers with the router
    router.callback_query.register(
        handler.show_settings_menu,
        F.data.startswith("settings:main"),
        admin_filter
    )

    router.callback_query.register(
        handler.show_gain_alert_settings,
        F.data.startswith("settings:gain_alerts"),
        admin_filter
    )

    # Edit Gain/Drop Thresholds
    router.callback_query.register(
        handler.prompt_edit_gain_threshold,
        F.data.startswith("settings:edit_gain_threshold"),
        admin_filter
    )
    router.message.register(
        handler.save_gain_threshold,
        StateFilter(ManagementStates.awaiting_gain_threshold),
        admin_filter
    )

    router.callback_query.register(
        handler.prompt_edit_drop_threshold,
        F.data.startswith("settings:edit_drop_threshold"),
        admin_filter
    )
    router.message.register(
        handler.save_drop_threshold,
        StateFilter(ManagementStates.awaiting_drop_threshold),
        admin_filter
    )

    router.callback_query.register(
        handler.prompt_edit_drop_floor,
        F.data.startswith("settings:edit_drop_floor"),
        admin_filter
    )
    router.message.register(
        handler.save_drop_floor,
        StateFilter(ManagementStates.awaiting_drop_floor),
        admin_filter
    )

    # Edit Chart Threshold & Bot
    router.callback_query.register(
        handler.prompt_edit_chart_threshold,
        F.data.startswith("settings:edit_chart_threshold"),
        admin_filter
    )
    router.message.register(
        handler.save_chart_threshold,
        StateFilter(ManagementStates.awaiting_global_chart_threshold),
        admin_filter
    )

    router.callback_query.register(
        handler.prompt_edit_chart_bot,
        F.data.startswith("settings:edit_chart_bot"),
        admin_filter
    )
    router.message.register(
        handler.save_chart_bot,
        StateFilter(ManagementStates.awaiting_global_chart_bot),
        admin_filter
    )

    # Edit Gain Template
    router.callback_query.register(
        handler.prompt_edit_gain_template,
        F.data.startswith("settings:edit_gain_template"),
        admin_filter
    )
    router.message.register(
        handler.save_gain_template,
        StateFilter(ManagementStates.awaiting_gain_template),
        admin_filter
    )

    # Edit Guardrails
    async def edit_guardrail_callback(query: CallbackQuery, state: FSMContext) -> None:
        metric = query.data.split(":")[-1]
        await handler.prompt_edit_guardrail(query, state, metric=metric)

    router.callback_query.register(
        edit_guardrail_callback,
        F.data.startswith("settings:edit_guardrail:"),
        admin_filter
    )
    router.message.register(
        handler.save_guardrail_value,
        StateFilter(ManagementStates.awaiting_guardrail_value),
        admin_filter
    )

    # Token Status
    router.callback_query.register(
        handler.show_token_status_menu,
        F.data.startswith("settings:token_status"),
        admin_filter
    )
    router.callback_query.register(
        handler.show_scheduler_overview,
        F.data.startswith("settings:scheduler_overview"),
        admin_filter
    )
    async def tokens_list_callback(query: CallbackQuery) -> None:
        status = query.data.split(":")[-2]
        page = int(query.data.split(":")[-1])
        await handler.show_tokens_list(query, status=status, page=page)

    router.callback_query.register(
        tokens_list_callback,
        F.data.startswith("settings:tokens_list:"),
        admin_filter
    )

    dispatcher.include_router(router)