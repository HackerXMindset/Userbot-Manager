import logging
from typing import Any, Dict, Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)


class RustDexBridge:
    """HTTP client for retrieving DexScreener payloads from the Rust service."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')

    async def fetch_dex_payload(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Fetch DexScreener JSON for a token via the Rust HTTP endpoint."""
        if not self.base_url:
            logger.error("Rust analysis base URL is not configured.")
            return None

        url = f"{self.base_url}/dex/{token_address}"
        timeout = aiohttp.ClientTimeout(total=12)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        body = await response.text()
                        logger.error(
                            "Rust analysis endpoint error %s for %s: %s",
                            response.status,
                            token_address,
                            body,
                        )
                        return None

                    return await response.json(content_type=None)

        except aiohttp.ClientError as err:
            logger.error("Rust analysis HTTP error for %s: %s", token_address, err)
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error("Unexpected Rust analysis error for %s: %s", token_address, err)

        return None

    async def fetch_bnb_payload(self, token_address: str) -> Optional[Dict[str, Any]]:
        """Fetch BNB analysis JSON via the Rust HTTP endpoint."""
        if not self.base_url:
            logger.error("Rust analysis base URL is not configured.")
            return None

        url = f"{self.base_url}/bnb/{token_address}"
        timeout = aiohttp.ClientTimeout(total=12)

        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        body = await response.text()
                        logger.error(
                            "Rust BNB endpoint error %s for %s: %s",
                            response.status,
                            token_address,
                            body,
                        )
                        return None

                    return await response.json(content_type=None)

        except aiohttp.ClientError as err:
            logger.error("Rust BNB HTTP error for %s: %s", token_address, err)
        except Exception as err:  # pragma: no cover - defensive logging
            logger.error("Unexpected Rust BNB error for %s: %s", token_address, err)

        return None


rust_dex_bridge = RustDexBridge(settings.rust_analysis_base_url)
