"""
Jupiter API Service - Direct integration with Jupiter Token API v2
Provides accurate market cap and token data for Solana tokens
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class JupiterAPIService:
    """
    Official Jupiter Token API v2 client
    Endpoint: https://lite-api.jup.ag/tokens/v2/search
    """

    BASE_URL = "https://lite-api.jup.ag/tokens/v2"
    REQUEST_TIMEOUT = 10  # seconds
    CACHE_TTL = 30  # Cache results for 30 seconds to avoid hammering API

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._cache_timestamps: Dict[str, datetime] = {}

    async def start(self):
        """Initialize HTTP session"""
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=self.REQUEST_TIMEOUT)
            self.session = aiohttp.ClientSession(
                timeout=timeout,
                headers={'Accept': 'application/json'}
            )
            logger.info("Jupiter API service started")

    async def stop(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None
        self._cache.clear()
        self._cache_timestamps.clear()
        logger.info("Jupiter API service stopped")

    async def get_token_data(self, token_address: str, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """
        Fetch token data from Jupiter API v2

        Args:
            token_address: Solana token contract address
            use_cache: Use cached result if available and fresh

        Returns:
            Token data dict with mcap, price, liquidity, stats, etc.
            None if token not found or API error
        """
        # Check cache first
        if use_cache and token_address in self._cache:
            cache_age = datetime.utcnow() - self._cache_timestamps.get(token_address, datetime.min)
            if cache_age < timedelta(seconds=self.CACHE_TTL):
                logger.debug(f"[JUPITER] Cache hit for {token_address[:8]}... (age: {cache_age.seconds}s)")
                return self._cache[token_address]

        if not self.session:
            await self.start()

        url = f"{self.BASE_URL}/search?query={token_address}"

        try:
            logger.debug(f"[JUPITER] Fetching data for {token_address[:8]}...")
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # API returns array, find exact match
                    if isinstance(data, list) and len(data) > 0:
                        # Find exact match by ID
                        token_data = None
                        for entry in data:
                            if entry.get('id') == token_address:
                                token_data = entry
                                break

                        if token_data:
                            # Cache the result
                            self._cache[token_address] = token_data
                            self._cache_timestamps[token_address] = datetime.utcnow()

                            logger.debug(
                                f"[JUPITER] ✓ {token_address} "
                                f"MC: ${token_data.get('mcap', 0):,.2f} "
                                f"Price: ${token_data.get('usdPrice', 0):.8f}"
                            )
                            return token_data
                        else:
                            logger.warning(f"[JUPITER] Token ID mismatch for {token_address}")
                            return None
                    else:
                        logger.warning(f"[JUPITER] No data returned for {token_address}")
                        return None

                elif response.status == 404:
                    logger.info(f"[JUPITER] Token {token_address} not found (404)")
                    return None

                elif response.status == 429:
                    logger.error(f"[JUPITER] Rate limited (429) for {token_address}")
                    return None

                else:
                    text = await response.text()
                    logger.error(
                        f"[JUPITER] Unexpected status {response.status} for {token_address}: {text[:200]}"
                    )
                    return None

        except asyncio.TimeoutError:
            logger.error(f"[JUPITER] Timeout fetching {token_address}")
        except aiohttp.ClientError as e:
            logger.error(f"[JUPITER] Client error for {token_address}: {e}")
        except Exception as e:
            logger.error(f"[JUPITER] Unexpected error for {token_address}: {e}", exc_info=True)

        return None

    def get_market_cap(self, token_data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        """
        Extract market cap from token data

        Args:
            token_data: Token data dict from get_token_data()

        Returns:
            Market cap as Decimal, or None if not available
        """
        if not token_data:
            return None

        mcap = token_data.get('mcap')
        if mcap is None or mcap <= 0:
            return None

        try:
            return Decimal(str(mcap))
        except Exception as e:
            logger.error(f"[JUPITER] Error parsing mcap '{mcap}': {e}")
            return None

    def get_price(self, token_data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        """Extract USD price from token data"""
        if not token_data:
            return None

        price = token_data.get('usdPrice')
        if price is None or price <= 0:
            return None

        try:
            return Decimal(str(price))
        except Exception as e:
            logger.error(f"[JUPITER] Error parsing price '{price}': {e}")
            return None

    def get_liquidity(self, token_data: Optional[Dict[str, Any]]) -> Optional[Decimal]:
        """Extract liquidity from token data"""
        if not token_data:
            return None

        liquidity = token_data.get('liquidity')
        if liquidity is None or liquidity < 0:
            return None

        try:
            return Decimal(str(liquidity))
        except Exception as e:
            logger.error(f"[JUPITER] Error parsing liquidity '{liquidity}': {e}")
            return None

    def get_ticker(self, token_data: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract token symbol/ticker from token data"""
        if not token_data:
            return None
        return token_data.get('symbol')

    async def fetch_market_cap(self, token_address: str, use_cache: bool = True) -> Optional[Decimal]:
        """
        Convenience method to fetch just the market cap

        Args:
            token_address: Solana token contract address
            use_cache: Use cached result if available

        Returns:
            Market cap as Decimal, or None if not available
        """
        token_data = await self.get_token_data(token_address, use_cache=use_cache)
        return self.get_market_cap(token_data)

    def clear_cache(self, token_address: Optional[str] = None):
        """
        Clear cache for specific token or all tokens

        Args:
            token_address: If provided, clear only this token. If None, clear all.
        """
        if token_address:
            self._cache.pop(token_address, None)
            self._cache_timestamps.pop(token_address, None)
            logger.debug(f"[JUPITER] Cache cleared for {token_address[:8]}...")
        else:
            self._cache.clear()
            self._cache_timestamps.clear()
            logger.debug("[JUPITER] All cache cleared")

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
_jupiter_service_instance = None


def get_jupiter_service() -> JupiterAPIService:
    """Get the singleton Jupiter API service instance"""
    global _jupiter_service_instance
    if _jupiter_service_instance is None:
        _jupiter_service_instance = JupiterAPIService()
    return _jupiter_service_instance
