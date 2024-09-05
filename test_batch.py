#!/usr/bin/env python3
"""Test script for batch DexScreener API implementation"""

import asyncio
import aiohttp
import logging
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_URL = "https://api.dexscreener.com/tokens/v1/solana"

async def _fetch_batch_token_data(addresses: List[str], retries: int = 0) -> Optional[List[Dict[str, Any]]]:
    """Test version of batch API fetch"""
    async with aiohttp.ClientSession() as session:
        try:
            # Limit to 30 addresses per batch (API limit)
            if len(addresses) > 30:
                addresses = addresses[:30]
                logger.warning(f"Batch size limited to 30 tokens (was {len(addresses)})")
            
            # Build batch URL with comma-separated addresses
            addresses_str = ",".join(addresses)
            url = f"{BASE_URL}/{addresses_str}"
            
            logger.info(f"Testing batch API with {len(addresses)} tokens: {url}")
            
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # API returns array of pairs for batch requests
                    if isinstance(data, list):
                        logger.info(f"Successfully fetched {len(data)} pairs for {len(addresses)} tokens")
                        return data
                    else:
                        logger.warning(f"Unexpected batch response format: {type(data)}")
                        return None
                else:
                    logger.warning(f"DexScreener batch API returned {response.status} for {len(addresses)} tokens")
                    
        except Exception as e:
            logger.error(f"Error fetching batch token data: {e}")
        
        return None

async def test_batch_processing():
    """Test batch processing logic"""
    # Sample token addresses
    test_addresses = [
        "So11111111111111111111111111111111111111112",  # SOL
        "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
        "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    ]
    
    # Mock tokens structure
    mock_tokens = [{"address": addr} for addr in test_addresses]
    
    # Test batch API call
    batch_data = await _fetch_batch_token_data(test_addresses)
    
    if batch_data:
        # Test token matching logic
        for token in mock_tokens:
            token_address = token['address']
            # Find the data for this specific token in the batch response
            token_pairs = [pair for pair in batch_data 
                         if pair.get('baseToken', {}).get('address') == token_address]
            
            if token_pairs:
                logger.info(f"Found {len(token_pairs)} pairs for token {token_address[:8]}...")
                # Show sample pair data
                pair = token_pairs[0]
                logger.info(f"  - Symbol: {pair.get('baseToken', {}).get('symbol')}")
                logger.info(f"  - Price: ${pair.get('priceUsd', 'N/A')}")
                logger.info(f"  - Market Cap: ${pair.get('marketCap', 'N/A')}")
            else:
                logger.warning(f"No pairs found for token {token_address[:8]}...")
    else:
        logger.error("Failed to fetch batch data")

if __name__ == "__main__":
    asyncio.run(test_batch_processing())