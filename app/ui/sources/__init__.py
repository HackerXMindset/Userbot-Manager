"""
Source management feature package.

Contains the refactored service that powers ``app.ui.handlers.sources``.
"""

from .service import SourceService

__all__ = ["SourceService"]
