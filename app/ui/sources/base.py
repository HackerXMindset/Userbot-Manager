from __future__ import annotations

from app.ui.keyboards import Keyboards
from app.models import GroupModel
from app.models.source_chat import SourceChatModel


class SourceBase:
    """Shared state for source-management mixins."""

    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
        self.source_model = SourceChatModel(db)
        self.cache = {}
        self.cache_time = {}
