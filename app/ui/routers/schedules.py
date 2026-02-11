"""
Schedule management routing module.
"""

from aiogram import Dispatcher, F

from app.ui.states import ManagementStates

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register schedule handlers."""

    manager = context.manager
    settings = context.settings

    dispatcher.callback_query.register(
        manager.handle_schedules,
        F.data.startswith("sched:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        manager.handle_schedule_action,
        F.data.startswith("schedule:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.process_start_time_input,
        ManagementStates.custom_schedule_start_time,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.process_end_time_input,
        ManagementStates.custom_schedule_end_time,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        manager.process_max_calls_input,
        ManagementStates.custom_schedule_max_calls,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
