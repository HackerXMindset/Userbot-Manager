import logging
from typing import Any, Dict, Optional

from app.services.dex_analytics_service import get_dex_analytics_service

logger = logging.getLogger(__name__)


class RustDexBridge:
    """Compatibility wrapper that now uses the Python analytics service."""

    def __init__(self, analytics_service=None) -> None:
        self._service = analytics_service or get_dex_analytics_service()

    async def fetch_dex_payload(self, token_address: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._service.fetch_solana_payload(token_address)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Python analytics error for %s: %s", token_address, exc, exc_info=True)
            return None

    async def fetch_bnb_payload(self, token_address: str) -> Optional[Dict[str, Any]]:
        try:
            return await self._service.fetch_bnb_payload(token_address)
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Python analytics BNB error for %s: %s", token_address, exc, exc_info=True)
            return None


rust_dex_bridge = RustDexBridge()
