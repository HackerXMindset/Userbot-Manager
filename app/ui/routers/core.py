"""
Core dispatcher registration for global management utilities.
"""

from aiogram import Dispatcher, F

from app.services.admin_cleanup import CANCEL_WIPE_CALLBACK, WIPE_CONTRACTS_CALLBACK
from .context import ManagementRouterContext


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register core handlers that do not belong to a feature-specific module."""

    settings = context.settings

    dispatcher.callback_query.register(
        context.cleanup_service.run_cleanup,
        F.data == "confirm_cleanup",
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        context.cleanup_service.confirm_wipe_contracts,
        F.data == WIPE_CONTRACTS_CALLBACK,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        context.cleanup_service.cancel_wipe_contracts,
        F.data == CANCEL_WIPE_CALLBACK,
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
