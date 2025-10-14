"""
DexScreener Token Service (monitoring disabled)

This module previously handled live market-cap tracking for monitored tokens.
The monitoring loop and external API polling have been removed so the service
now acts as a lightweight registry that records tokens without fetching or
updating market data.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.config import settings
from app.db import db
from app.models import TokenModel

logger = logging.getLogger(__name__)

# Singleton instance for global access
_dex_service_instance: Optional["DexScreenerService"] = None


def get_dex_service() -> "DexScreenerService":
    """Return the singleton Dex service instance."""
    global _dex_service_instance
    if _dex_service_instance is None:
        _dex_service_instance = DexScreenerService()
    return _dex_service_instance


class DexScreenerService:
    """
    DexScreener integration stub.

    Market-cap monitoring and DexScreener polling have been disabled. The
    exposed methods remain so other parts of the system can continue to add and
    manage tracked tokens without attempting to fetch live data.
    """

    def __init__(self) -> None:
        self.token_model = TokenModel(db)
        self.userbot_manager = None
        self.running = False

    # ==================== LIFECYCLE ====================

    def set_userbot_manager(self, manager) -> None:
        """Record the UserbotManager reference (for compatibility)."""
        self.userbot_manager = manager
        if manager:
            logger.info("UserbotManager set on Dex service (monitoring disabled)")
        else:
            logger.info("UserbotManager cleared on Dex service (monitoring disabled)")

    async def start(self) -> None:
        """Start the service (no monitoring loop is launched)."""
        if self.running:
            return

        self.running = True
        logger.info("Dex service started (market cap monitoring disabled)")

    async def stop(self) -> None:
        """Stop the service."""
        if not self.running:
            return

        self.running = False
        logger.info("Dex service stopped")

    # ==================== TOKEN MANAGEMENT ====================

    async def add_token(self, token_address: str) -> Dict[str, Any]:
        """
        Register a new token without contacting external services.
        Tokens are stored with placeholder market-cap values defaulting to zero.
        """
        try:
            existing = await self.token_model.get_by_address(token_address)
            if existing:
                return {
                    "success": False,
                    "error": "Token already being tracked",
                    "token": dict(existing),
                }

            initial_mc = Decimal("0")
            token = await self.token_model.create_or_update(
                token_address, initial_mc, ticker=None
            )

            logger.info(
                "[INIT] Registered %s... without market cap monitoring",
                token_address[:8],
            )

            return {
                "success": True,
                "token": dict(token),
                "initial_mc": float(initial_mc),
            }

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error adding token %s: %s", token_address[:8], exc, exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

    async def remove_token(self, token_address: str) -> Dict[str, Any]:
        """Mark a token as stopped."""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    "success": False,
                    "error": "Token not found",
                }

            await self.token_model.set_status(token["id"], "stopped")
            logger.info("Stopped tracking %s...", token_address[:8])

            return {
                "success": True,
                "token": dict(token),
            }

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error(
                "Error stopping tracking for %s: %s", token_address[:8], exc, exc_info=True
            )
            return {
                "success": False,
                "error": str(exc),
            }

    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """Return token information from the database."""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    "success": False,
                    "error": "Token not found in database",
                }

            result: Dict[str, Any] = {
                "success": True,
                "token": dict(token),
                "dex_data": None,
            }

            first_seen_mc = token.get("first_seen_mc")
            last_mc = token.get("last_mc")
            if first_seen_mc and last_mc and first_seen_mc > 0:
                result["multiplier"] = float(last_mc / first_seen_mc)

            return result

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error loading token info for %s: %s", token_address, exc)
            return {
                "success": False,
                "error": str(exc),
            }

    async def get_service_stats(self) -> Dict[str, Any]:
        """Return service statistics indicating monitoring is disabled."""
        try:
            token_stats = await self.token_model.get_token_stats()
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Error fetching token stats: %s", exc, exc_info=True)
            token_stats = {}

        return {
            "running": self.running,
            "monitoring_enabled": False,
            "poll_interval": settings.dex_poll_secs,
            "timeout": settings.dex_timeout,
            "max_retries": settings.dex_max_retries,
            "min_mc_threshold": 0.0,
            "tokens": token_stats,
        }

    # ==================== LEGACY API SHIMS ====================

    async def _fetch_token_data(self, token_address: str, *args, **kwargs) -> List[Dict[str, Any]]:
        """
        Legacy hook for components that previously depended on DexScreener data.
        Returns an empty list to signal that live data is no longer available.
        """
        logger.debug(
            "Market cap monitoring disabled; skipping data fetch for %s",
            token_address[:8],
        )
        return []

    async def _fetch_batch_token_data(
        self, addresses: List[str], *args, **kwargs
    ) -> List[Dict[str, Any]]:
        """Legacy batch fetch shim returning no data."""
        logger.debug(
            "Market cap monitoring disabled; skipping batch fetch for %d tokens",
            len(addresses),
        )
        return []

