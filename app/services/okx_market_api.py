"""
OKX Market API Client - fetches latest token info from OKX Web3 API.

Used to obtain market cap and pricing data for gain alerts.
"""

import asyncio
import aiohttp
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class OkxMarketAPIClient:
    BASE_URL = "https://web3.okx.com/priapi/v1/dx/market/v2/latest/info"
    REQUEST_TIMEOUT = 10
    CACHE_TTL_SECONDS = 30
    DEFAULT_RATE_PROFILE = "default"

    RATE_LIMITS: Dict[str, Dict[str, float]] = {
        "default": {"min_interval": 1.0},          # 1 request per second
        "mc_monitor": {"min_interval": 1.0 / 3.0},  # Up to 3 requests per second
    }

    CHAIN_ID_MAP = {
        "bsc": "56",
        "bnb": "56",
        "56": "56",
        "eth": "1",
        "ethereum": "1",
        "1": "1",
        "polygon": "137",
        "matic": "137",
        "137": "137",
        "arbitrum": "42161",
        "42161": "42161",
        "optimism": "10",
        "10": "10",
        "sol": "501",
        "solana": "501",
        "solana-mainnet": "501",
        "501": "501",
    }

    def __init__(self) -> None:
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._lock = asyncio.Lock()
        self._rate_state: Dict[str, Dict[str, Any]] = {
            profile: {"last_call": 0.0, "lock": asyncio.Lock()}
            for profile in self.RATE_LIMITS
        }

    async def start(self) -> None:
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(timeout=timeout)

    async def stop(self) -> None:
        if self.session:
            await self.session.close()
            self.session = None
        self._cache.clear()
        self._cache_expiry.clear()
        for state in self._rate_state.values():
            state["last_call"] = 0.0

    async def fetch_token_info(
        self,
        address: str,
        chain_id: Optional[str] = None,
        rate_profile: str = DEFAULT_RATE_PROFILE,
        use_cache: bool = True,
        cache_ttl: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch OKX token data, respecting per-profile rate limits and cache options."""
        await self.start()

        normalized_chain = self._normalize_chain(chain_id, address)
        if normalized_chain is None:
            logger.debug(f"[OKX] Unsupported chain for address {address}, skipping OKX lookup")
            return None

        cache_key = f"{normalized_chain}:{address}"
        ttl_seconds = cache_ttl if cache_ttl is not None else self.CACHE_TTL_SECONDS

        if use_cache:
            async with self._lock:
                expires_at = self._cache_expiry.get(cache_key)
                if expires_at and expires_at > datetime.utcnow():
                    return self._cache.get(cache_key)

        await self._apply_rate_limit(rate_profile)

        params = {
            "tokenContractAddress": address,
            "chainId": normalized_chain,
        }

        try:
            async with self.session.get(self.BASE_URL, params=params) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.warning(
                        f"[OKX] Unexpected status {response.status} for {address} on chain {normalized_chain}: {text[:200]}"
                    )
                    return None

                payload = await response.json()
        except asyncio.TimeoutError:
            logger.warning(f"[OKX] Timeout fetching data for {address} on chain {normalized_chain}")
            return None
        except aiohttp.ClientError as err:
            logger.warning(f"[OKX] Client error fetching {address}: {err}")
            return None
        except Exception as exc:
            logger.error(f"[OKX] Unexpected error fetching {address}: {exc}", exc_info=True)
            return None

        data = payload.get("data")
        if not data:
            message = payload.get("errorMessage") or payload.get("msg") or payload.get("detailMsg") or payload.get("errorCode")
            logger.debug(
                f"[OKX] No data returned for {address} on chain {normalized_chain} ({message})"
            )
            return None

        async with self._lock:
            self._cache[cache_key] = data
            self._cache_expiry[cache_key] = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        return data

    def get_market_cap(self, data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        if not data:
            return None
        raw_value = data.get("marketCap") or data.get("market_cap")
        return self._to_decimal(raw_value)

    def get_price(self, data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        if not data:
            return None
        raw_value = data.get("price")
        return self._to_decimal(raw_value)

    def get_ticker(self, data: Optional[Dict[str, Any]]) -> Optional[str]:
        if not data:
            return None
        symbol = data.get("tokenSymbol")
        if symbol:
            return symbol
        return data.get("tokenName")

    def _normalize_chain(self, chain_id: Optional[str], address: str) -> Optional[str]:
        if chain_id:
            key = chain_id.lower()
            if key in self.CHAIN_ID_MAP:
                return self.CHAIN_ID_MAP[key]
        if address.lower().startswith("0x"):
            return "56"  # default to BSC for EVM-style addresses
        # Treat other formats (e.g., Solana base58) as Solana
        return "501"

    async def _apply_rate_limit(self, profile: str) -> None:
        """Throttle outbound OKX requests according to the requested profile."""
        config = self.RATE_LIMITS.get(profile, self.RATE_LIMITS[self.DEFAULT_RATE_PROFILE])

        if profile not in self._rate_state:
            self._rate_state[profile] = {"last_call": 0.0, "lock": asyncio.Lock()}

        state = self._rate_state[profile]
        lock: asyncio.Lock = state["lock"]
        min_interval = max(config.get("min_interval", 0.0), 0.0)

        async with lock:
            last_call = state.get("last_call", 0.0)
            if min_interval > 0 and last_call:
                now = asyncio.get_running_loop().time()
                elapsed = now - last_call
                if elapsed < min_interval:
                    await asyncio.sleep(min_interval - elapsed)
                    now = asyncio.get_running_loop().time()
            else:
                now = asyncio.get_running_loop().time()

            state["last_call"] = now

    @staticmethod
    def _to_decimal(value: Any) -> Optional[Decimal]:
        if value in (None, "", 0, "0"):
            return None
        try:
            return Decimal(str(value))
        except (ValueError, ArithmeticError, TypeError):
            return None


_okx_market_client: Optional[OkxMarketAPIClient] = None


def get_okx_market_client() -> OkxMarketAPIClient:
    global _okx_market_client
    if _okx_market_client is None:
        _okx_market_client = OkxMarketAPIClient()
    return _okx_market_client
