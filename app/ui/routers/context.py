from dataclasses import dataclass
from typing import Any, Optional

from aiogram import Dispatcher

from app.ui.keyboards import Keyboards


@dataclass(slots=True)
class ManagementRouterContext:
    """
    Shared dependencies that router modules need when registering handlers.

    The fields intentionally remain minimal; downstream refactors can extend
    this object as responsibilities migrate out of ``ManagementBot``.
    """

    dispatcher: Dispatcher
    keyboards: Keyboards
    db: Any
    settings: Any
    manager: Any
    cleanup_service: Any
    system_manager: Optional[Any] = None
    settings_handler: Optional[Any] = None
