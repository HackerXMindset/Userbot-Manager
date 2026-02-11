"""
DexScreener API Client - Fetches token data from DexScreener REST API
Provides market cap, price, liquidity data for ongoing monitoring
"""

import asyncio
import aiohttp
import logging
import time
import json
from collections import deque
from typing import Dict, Any, Optional, Deque, List
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class DexScreenerAPIClient:
    """
    DexScreener REST API client for fetching token pair data.
    Endpoint: https://api.dexscreener.com/tokens/v1/{chainId}/{tokenAddress}
    """

    TOKENS_URL = "https://api.dexscreener.com/tokens/v1"
    TOKEN_PAIRS_URL = "https://api.dexscreener.com/token-pairs/v1"
    LATEST_TOKENS_URL = "https://api.dexscreener.com/latest/dex/tokens"
    REQUEST_TIMEOUT = 10  # seconds
    CACHE_TTL = 60  # Cache results for 60 seconds
    MAX_RETRIES = 3
    BACKOFF_BASE = 2  # Exponential backoff base (seconds)
    MAX_REQUESTS_PER_SECOND = 4  # hard cap per requirements

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Optional[List[Dict[str, Any]]]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}
        self._rate_limit_lock = asyncio.Lock()
        self._request_times: Deque[float] = deque()

    async def start(self):
        """Initialize HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'Accept': 'application/json'}
            )
            logger.info("DexScreener API client started")

    async def stop(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("DexScreener API client stopped")

    async def _apply_rate_limit(self):
        """Ensure we respect the MAX_REQUESTS_PER_SECOND budget."""
        async with self._rate_limit_lock:
            now = time.monotonic()

            # Drop timestamps older than 1 second
            while self._request_times and now - self._request_times[0] >= 1:
                self._request_times.popleft()

            if len(self._request_times) >= self.MAX_REQUESTS_PER_SECOND:
                sleep_for = 1 - (now - self._request_times[0])
                sleep_for = max(sleep_for, 0)
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                now = time.monotonic()
                while self._request_times and now - self._request_times[0] >= 1:
                    self._request_times.popleft()

            self._request_times.append(now)

    async def fetch_token(
        self,
        address: str,
        chain_id: str = "solana",
        use_cache: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """
        Fetch token pair data from DexScreener API with retry/backoff.

        Returns only the primary pair (first in list). To access all pairs use
        fetch_token_pairs().
        """
        pairs = await self.fetch_token_pairs(address, chain_id=chain_id, use_cache=use_cache)
        if not pairs:
            return None
        best_pair = self._select_preferred_pair(pairs)

        fdv_val = self._safe_float(best_pair.get('fdv') or best_pair.get('marketCap'))
        price_val = self._safe_float(best_pair.get('priceUsd'))
        logger.debug(
            f"[DEXSCREENER] ✓ {chain_id}:{address.strip()[:8]}... "
            f"MC: ${fdv_val:,.2f} "
            f"Price: ${price_val:.8f}"
        )
        return best_pair

    async def fetch_token_pairs(
        self,
        address: str,
        chain_id: str = "solana",
        use_cache: bool = True,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch the full list of token pairs from DexScreener for a contract address.

        Returns a list of pair dicts (can be empty). None indicates a hard error.
        """
        address = address.strip()
        normalized_chain = (chain_id or "solana").lower()
        cache_key = f"{normalized_chain}:{address}"

        if use_cache and cache_key in self._cache:
            cache_age = datetime.utcnow() - self._cache_timestamps.get(cache_key, datetime.min)
            if cache_age < timedelta(seconds=self.CACHE_TTL):
                logger.debug(
                    f"[DEXSCREENER] Cache hit for {chain_id}:{address[:8]}... "
                    f"(age: {cache_age.seconds}s)"
                )
                return self._cache[cache_key]

        if not self.session:
            await self.start()

        endpoints = [
            ("tokens_v1", f"{self.TOKENS_URL}/{normalized_chain}/{address}"),
            ("token_pairs_v1", f"{self.TOKEN_PAIRS_URL}/{normalized_chain}/{address}"),
            ("latest_tokens", f"{self.LATEST_TOKENS_URL}/{address}"),
        ]

        combined_empty_payloads: Dict[str, Any] = {}

        # Retry logic with exponential backoff
        for attempt in range(self.MAX_RETRIES):
            retry_due_to_backoff = False
            empty_payloads = {}

            try:
                for endpoint_name, url in endpoints:
                    await self._apply_rate_limit()
                    logger.debug(
                        f"[DEXSCREENER] Fetching {chain_id}:{address[:8]}... "
                        f"via {endpoint_name} (attempt {attempt + 1}/{self.MAX_RETRIES})"
                    )

                    async with self.session.get(url) as response:
                        if response.status == 200:
                            data = await response.json()
                            pairs = self._extract_pairs(data)

                            if pairs:
                                self._cache[cache_key] = pairs
                                self._cache_timestamps[cache_key] = datetime.utcnow()
                                return pairs

                            empty_payloads[endpoint_name] = data
                            combined_empty_payloads[endpoint_name] = data
                            continue

                        elif response.status == 404:
                            empty_payloads[endpoint_name] = {"status": 404}
                            combined_empty_payloads[endpoint_name] = {"status": 404}
                            continue

                        elif response.status == 429:
                            backoff_time = self.BACKOFF_BASE ** (attempt + 1)
                            logger.warning(
                                f"[DEXSCREENER] Rate limited (429) for {chain_id}:{address[:8]}... "
                                f"via {endpoint_name}, backing off {backoff_time}s"
                            )

                            if attempt < self.MAX_RETRIES - 1:
                                await asyncio.sleep(backoff_time)
                                retry_due_to_backoff = True
                                break
                            else:
                                logger.error(
                                    f"[DEXSCREENER] Max retries exceeded for {chain_id}:{address[:8]}... "
                                    "(rate limit)"
                                )
                                return None

                        else:
                            text = await response.text()
                            logger.error(
                                f"[DEXSCREENER] Unexpected status {response.status} for "
                                f"{chain_id}:{address[:8]}... via {endpoint_name}: {text[:200]}"
                            )

                            if 500 <= response.status < 600 and attempt < self.MAX_RETRIES - 1:
                                backoff_time = self.BACKOFF_BASE ** attempt
                                logger.info(
                                    f"[DEXSCREENER] Retrying after {backoff_time}s due to server error "
                                    f"({chain_id}:{address[:8]}) via {endpoint_name}"
                                )
                                await asyncio.sleep(backoff_time)
                                retry_due_to_backoff = True
                                break

                if retry_due_to_backoff:
                    continue

            except asyncio.TimeoutError:
                logger.error(
                    f"[DEXSCREENER] Timeout fetching {chain_id}:{address[:8]}... "
                    f"(attempt {attempt + 1})"
                )
                if attempt < self.MAX_RETRIES - 1:
                    backoff_time = self.BACKOFF_BASE ** attempt
                    await asyncio.sleep(backoff_time)
                    continue
                return None

            except aiohttp.ClientError as e:
                logger.error(
                    f"[DEXSCREENER] Client error for {chain_id}:{address[:8]}... "
                    f"(attempt {attempt + 1}): {e}"
                )
                if attempt < self.MAX_RETRIES - 1:
                    backoff_time = self.BACKOFF_BASE ** attempt
                    await asyncio.sleep(backoff_time)
                    continue
                return None

            except Exception as e:
                logger.error(f"[DEXSCREENER] Unexpected error for {chain_id}:{address[:8]}...: {e}", exc_info=True)
                return None

        if combined_empty_payloads:
            self._cache[cache_key] = []
            self._cache_timestamps[cache_key] = datetime.utcnow()
            return []

        return None

    @staticmethod
    def _select_preferred_pair(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        DexScreener orders pairs by relevance (volume/liquidity). Use the first entry
        to mirror the UI and get the MC DexScreener shows for the contract.
        """
        return pairs[0]

    @staticmethod
    def _extract_pairs(data: Any) -> List[Dict[str, Any]]:
        if isinstance(data, dict):
            pairs = data.get('pairs')
            return pairs or []
        if isinstance(data, list):
            return data
        return []

    @staticmethod
    def _extract_liquidity(pair: Dict[str, Any]) -> float:
        """Extract liquidity USD value as float for sorting."""
        liquidity = pair.get('liquidity')
        if isinstance(liquidity, dict):
            value = liquidity.get('usd')
        else:
            value = liquidity

        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """Convert a value to float safely."""
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def get_market_cap(self, pair_data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        """
        Extract market cap (FDV) from pair data

        Args:
            pair_data: Pair data dict from fetch_token()

        Returns:
            Market cap as Decimal, or None if not available
        """
        if not pair_data:
            return None

        # DexScreener uses 'fdv' (fully diluted valuation) as market cap
        fdv = pair_data.get('fdv') or pair_data.get('marketCap')
        if fdv is None or fdv <= 0:
            return None

        try:
            return Decimal(str(fdv))
        except Exception as e:
            logger.error(f"[DEXSCREENER] Error parsing market cap '{fdv}': {e}")
            return None

    def get_price(self, pair_data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        """Extract USD price from pair data"""
        if not pair_data:
            return None

        price = pair_data.get('priceUsd')
        if price is None or price <= 0:
            return None

        try:
            return Decimal(str(price))
        except Exception as e:
            logger.error(f"[DEXSCREENER] Error parsing price '{price}': {e}")
            return None

    def get_liquidity(self, pair_data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        """Extract liquidity from pair data"""
        if not pair_data:
            return None

        # Try liquidity.usd first, fallback to liquidity
        liquidity_data = pair_data.get('liquidity', {})
        if isinstance(liquidity_data, dict):
            liquidity = liquidity_data.get('usd')
        else:
            liquidity = liquidity_data

        if liquidity is None or liquidity < 0:
            return None

        try:
            return Decimal(str(liquidity))
        except Exception as e:
            logger.error(f"[DEXSCREENER] Error parsing liquidity '{liquidity}': {e}")
            return None

    def get_ticker(self, pair_data: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract token symbol/ticker from pair data"""
        if not pair_data:
            return None

        # DexScreener stores base token info
        base_token = pair_data.get('baseToken', {})
        return base_token.get('symbol')

    def clear_cache(self, address: Optional[str] = None):
        """
        Clear cache for specific token or all tokens

        Args:
            address: If provided, clear only this token. If None, clear all.
        """
        if address:
            removed = False
            for key in list(self._cache.keys()):
                if key.endswith(f":{address}"):
                    self._cache.pop(key, None)
                    self._cache_timestamps.pop(key, None)
                    removed = True
            if removed:
                logger.debug(f"[DEXSCREENER] Cache cleared for {address[:8]}...")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.debug("[DEXSCREENER] All cache cleared")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        now = datetime.utcnow()
        fresh_count = sum(
            1 for ts in self._cache_timestamps.values()
            if now - ts < timedelta(seconds=self.CACHE_TTL)
        )

        return {
            'total_cached': len(self._cache),
            'fresh_cached': fresh_count,
            'stale_cached': len(self._cache) - fresh_count,
            'cache_ttl_seconds': self.CACHE_TTL
        }


# Global singleton instance
_dexscreener_client_instance = None


def get_dexscreener_client() -> DexScreenerAPIClient:
    """Get the singleton DexScreener API client instance"""
    global _dexscreener_client_instance
    if _dexscreener_client_instance is None:
        _dexscreener_client_instance = DexScreenerAPIClient()
    return _dexscreener_client_instance
