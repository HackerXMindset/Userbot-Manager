"""
Routing package for the management bot dispatcher.

This package encapsulates feature-specific registration helpers so that
``app.management_bot.ManagementBot`` no longer needs to maintain a single,
monolithic ``setup_handlers`` method. Each module should expose a
``register`` function that wires its handlers into the provided dispatcher.
"""

from .context import ManagementRouterContext
from .registry import register_management_routes

__all__ = ["ManagementRouterContext", "register_management_routes"]
