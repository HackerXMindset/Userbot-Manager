"""UI handlers for the Telegram Bot Management System"""

from .menu import MenuHandler
from .groups import GroupsHandler
from .userbots import UserbotsHandler
from .schedules import SchedulesHandler
from .targets import TargetsHandler
from .sources import SourcesHandler
from .alerts import AlertsHandler
from .pnl import PnlHandler
from .notifications import NotificationsHandler
from .auto_click import AutoClickHandler
from .curate_alpha import CurateAlphaHandler
from .templates import TemplatesHandler

__all__ = [
    "MenuHandler",
    "GroupsHandler", 
    "UserbotsHandler",
    "SchedulesHandler",
    "TargetsHandler",
    "SourcesHandler",
    "AlertsHandler",
    "PnlHandler",
    "NotificationsHandler",
    "AutoClickHandler",
    "CurateAlphaHandler",
    "TemplatesHandler",
]