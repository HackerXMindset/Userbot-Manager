from __future__ import annotations

from app.ui.keyboards import Keyboards
from app.ui.sources.service import SourceService


class SourcesHandler:
    """
    Thin compatibility wrapper around ``SourceService``.

    The legacy codebase expects an object with the old handler's methods, so we
    delegate attribute access to the new service implementation.
    """

    def __init__(self, db, keyboards: Keyboards):
        self.service = SourceService(db, keyboards)

    def __getattr__(self, item):
        return getattr(self.service, item)
