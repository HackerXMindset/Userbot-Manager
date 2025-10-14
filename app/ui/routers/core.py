"""
Core dispatcher registration for global management utilities.
"""

from aiogram import Dispatcher, F

from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register core handlers that do not belong to a feature-specific module."""

    settings = context.settings

    dispatcher.callback_query.register(
        context.cleanup_service.run_cleanup,
        F.data == "confirm_cleanup",
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
