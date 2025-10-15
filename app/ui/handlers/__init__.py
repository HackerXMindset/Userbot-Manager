"""UI handlers for the Telegram Bot Management System"""

from .menu import MenuHandler
from .groups import GroupsHandler
from .userbots import UserbotsHandler
from .schedules import SchedulesHandler
from .sources import SourcesHandler
from .pnl import PnlHandler
from .command_forwarding import CommandForwardingHandler
from .notifications import NotificationsHandler
from .auto_click import AutoClickHandler
from .dynamic_reply import DynamicReplyHandler
from .curate_alpha import CurateAlphaHandler
from .templates import TemplatesHandler
from .settings import SettingsHandler
from .gain_alerts import GainAlertsHandler

__all__ = [
    "MenuHandler",
    "GroupsHandler",
    "UserbotsHandler",
    "SchedulesHandler",
    "SourcesHandler",
    "PnlHandler",
    "CommandForwardingHandler",
    "NotificationsHandler",
    "AutoClickHandler",
    "DynamicReplyHandler",
    "CurateAlphaHandler",
    "TemplatesHandler",
    "SettingsHandler",
    "GainAlertsHandler",
]
