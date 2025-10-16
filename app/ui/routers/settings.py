"""
Settings routing module - Routes settings-related callbacks
"""

import logging
from aiogram import Dispatcher, F, types
from aiogram.fsm.context import FSMContext

from .context import ManagementRouterContext

logger = logging.getLogger(__name__)


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register settings handlers"""

    settings_cfg = context.settings
    manager = context.manager

    async def handle_settings_callbacks(query: types.CallbackQuery, state: FSMContext) -> None:
        """Route settings callback queries"""
        parts = query.data.split(":")
        action = parts[1] if len(parts) > 1 else ""

        if action == "main":
            await manager.settings_handler.show_settings_menu(query)
        elif action == "gain_alerts":
            await manager.settings_handler.show_gain_alert_settings(query)
        elif action == "edit_gain_threshold":
            await manager.settings_handler.prompt_edit_gain_threshold(query, state)
        elif action == "edit_drop_threshold":
            await manager.settings_handler.prompt_edit_drop_threshold(query, state)
        elif action == "edit_drop_floor":
            await manager.settings_handler.prompt_edit_drop_floor(query, state)
        elif action == "edit_chart_threshold":
            await manager.settings_handler.prompt_edit_chart_threshold(query, state)
        elif action == "edit_chart_bot":
            await manager.settings_handler.prompt_edit_chart_bot(query, state)
        elif action == "edit_gain_template":
            await manager.settings_handler.prompt_edit_gain_template(query, state)
        elif action == "token_status":
            await manager.settings_handler.show_token_status_menu(query)
        elif action == "scheduler_overview":
            await manager.settings_handler.show_scheduler_overview(query)
        elif action == "tokens_list":
            # Format: settings:tokens_list:active:1
            status = parts[2] if len(parts) > 2 else "active"
            page = int(parts[3]) if len(parts) > 3 else 1
            await manager.settings_handler.show_tokens_list(query, status, page)

    async def handle_gain_threshold_input(message: types.Message, state: FSMContext) -> None:
        """Handle gain threshold value input"""
        await manager.settings_handler.save_gain_threshold(message, state)

    async def handle_drop_threshold_input(message: types.Message, state: FSMContext) -> None:
        """Handle drop threshold value input"""
        await manager.settings_handler.save_drop_threshold(message, state)

    async def handle_drop_floor_input(message: types.Message, state: FSMContext) -> None:
        """Handle drop floor value input"""
        await manager.settings_handler.save_drop_floor(message, state)

    async def handle_chart_threshold_input(message: types.Message, state: FSMContext) -> None:
        """Handle global chart threshold input."""
        await manager.settings_handler.save_chart_threshold(message, state)

    async def handle_chart_bot_input(message: types.Message, state: FSMContext) -> None:
        """Handle global chart bot ID input."""
        await manager.settings_handler.save_chart_bot(message, state)

    async def handle_gain_template_input(message: types.Message, state: FSMContext) -> None:
        """Handle global gain template text input"""
        await manager.settings_handler.save_gain_template(message, state)

    # Register callback query handlers
    dispatcher.callback_query.register(
        handle_settings_callbacks,
        F.data.startswith("settings:"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    # Register message handlers for awaiting input states
    from aiogram.filters import StateFilter

    dispatcher.message.register(
        handle_gain_threshold_input,
        StateFilter("awaiting_gain_threshold"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        handle_drop_threshold_input,
        StateFilter("awaiting_drop_threshold"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        handle_drop_floor_input,
        StateFilter("awaiting_drop_floor"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        handle_chart_threshold_input,
        StateFilter("awaiting_global_chart_threshold"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        handle_chart_bot_input,
        StateFilter("awaiting_global_chart_bot"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        handle_gain_template_input,
        StateFilter("awaiting_gain_template"),
        F.from_user.id.in_(settings_cfg.admin_telegram_ids_list),
    )

    logger.info("Settings router registered")
