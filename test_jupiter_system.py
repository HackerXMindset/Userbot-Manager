#!/usr/bin/env python3
"""Test script for new Jupiter API integration"""

import asyncio
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))

from app.services.jupiter_api import get_jupiter_service


async def test_jupiter_api():
    """Test Jupiter API service"""
    jupiter = get_jupiter_service()
    await jupiter.start()

    # Test token address
    token_address = 'AbKf1znsuCwsKHNUVX2odHZDGQCSxp1zX6h6gU3apump'

    print(f"\n=== Testing Jupiter API ===")
    print(f"Token: {token_address[:8]}...")

    # Test 1: Get token data
    print("\n[Test 1] Fetching token data...")
    data = await jupiter.get_token_data(token_address, use_cache=False)

    if data:
        mc = jupiter.get_market_cap(data)
        ticker = jupiter.get_ticker(data)
        price = jupiter.get_price(data)
        liquidity = jupiter.get_liquidity(data)

        print(f"✓ Market Cap: ${mc:,.2f}")
        print(f"✓ Ticker: {ticker}")
        print(f"✓ Price: ${price:.8f}")
        print(f"✓ Liquidity: ${liquidity:,.2f}")
    else:
        print("✗ Failed to fetch data")
        return False

    # Test 2: Test cache
    print("\n[Test 2] Testing cache...")
    data2 = await jupiter.get_token_data(token_address, use_cache=True)
    if data2:
        print("✓ Cache working")
    else:
        print("✗ Cache failed")
        return False

    # Test 3: Cache stats
    print("\n[Test 3] Cache statistics...")
    stats = jupiter.get_cache_stats()
    print(f"✓ Cached tokens: {stats['total_cached']}")
    print(f"✓ Fresh cached: {stats['fresh_cached']}")
    print(f"✓ Cache TTL: {stats['cache_ttl_seconds']}s")

    # Test 4: Fetch market cap directly
    print("\n[Test 4] Direct market cap fetch...")
    mc_direct = await jupiter.fetch_market_cap(token_address, use_cache=False)
    if mc_direct:
        print(f"✓ Direct MC: ${mc_direct:,.2f}")
    else:
        print("✗ Direct fetch failed")
        return False

    await jupiter.stop()

    print("\n=== All Tests Passed ✓ ===\n")
    return True


if __name__ == "__main__":
    result = asyncio.run(test_jupiter_api())
    sys.exit(0 if result else 1)
