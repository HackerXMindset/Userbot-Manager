import aiohttp
import asyncio
import orjson
import sys
import os
from functools import wraps
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("HELIUS_API_KEY")
PUMP_FUN_JWT = os.getenv("PUMP_FUN_JWT")

def retry(retries=2, delay=0.2):
    """A decorator for retrying a function with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            _delay = delay
            for i in range(retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if i == retries - 1:
                        raise
                    await asyncio.sleep(_delay)
                    _delay *= 2
        return wrapper
    return decorator

@retry()
async def query_metadata_v1(session, mint_address):
    """Fetch token metadata using Helius queryMetadataV1 endpoint"""
    url = f"https://api.helius.xyz/v0/token-metadata?api-key={API_KEY}"
    payload = {
        "mintAccounts": [mint_address],
        "includeOffChain": True,
        "disableCache": False
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

@retry()
async def get_token_largest_accounts(session, mint_address):
    """Get largest token holders using getTokenLargestAccounts"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getTokenLargestAccounts",
        "params": [mint_address]
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

@retry()
async def get_asset(session, mint_address):
    """Fetch asset data using getAsset method"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getAsset",
        "params": {"id": mint_address}
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}


@retry()
async def get_token_supply_info(session, mint_address):
    """Get detailed token supply information"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getTokenSupply",
        "params": [mint_address]
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

@retry()
async def get_account_info(session, mint_address):
    """Get detailed account information"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getAccountInfo",
        "params": [mint_address, {"encoding": "base64"}]
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

@retry()
async def get_token_price(session, mint_address):
    """Get token price from DexScreener API"""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

@retry()
async def get_creator_balance(session, creator_address, mint_address):
    """Get creator's current token balance"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getTokenAccountsByOwner",
        "params": [
            creator_address,
            {"mint": mint_address},
            {"encoding": "jsonParsed"}
        ]
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

@retry()
async def get_sol_balance(session, address):
    """Get SOL balance for an address"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getBalance",
        "params": [address]
    }
    headers = {"Content-Type": "application/json"}

    try:
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            return await response.json(loads=orjson.loads)
    except Exception as e:
        return {"error": str(e)}

def _process_livestream_coin(coin, auth_used, fallback_used=False):
    """Process a single coin from the livestream data."""
    return {
        "is_live": coin.get('is_currently_live', False),
        "participants": coin.get('num_participants', 0),
        "replies": coin.get('reply_count', 0),
        "market_cap": coin.get('market_cap', 0),
        "usd_market_cap": coin.get('usd_market_cap', 0),
        "thumbnail": coin.get('thumbnail'),
        "bonding_curve_progress": coin.get('bondingCurveProgress', 0),
        "created_timestamp": coin.get('created_timestamp', 0),
        "last_trade_timestamp": coin.get('last_trade_timestamp', 0),
        "virtual_sol_reserves": coin.get('virtual_sol_reserves', 0),
        "real_sol_reserves": coin.get('real_sol_reserves', 0),
        "complete": coin.get('complete', False),
        "raydium_pool": coin.get('raydium_pool'),
        "twitter": coin.get('twitter'),
        "telegram": coin.get('telegram'),
        "website": coin.get('website'),
        "auth_used": auth_used,
        "fallback_used": fallback_used
    }

@retry()
async def get_livestream_status(session, mint_address):
    """Check if token is currently live on pump.fun"""
    url = "https://frontend-api-v3.pump.fun/coins/currently-live?offset=0&limit=1000&includeNsfw=false&order=DESC"

    # Check if JWT token is properly configured
    has_jwt = PUMP_FUN_JWT and PUMP_FUN_JWT != "your_pump_fun_jwt_token_here"

    headers = {"Authorization": f"Bearer {PUMP_FUN_JWT}"} if has_jwt else {}

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            response.raise_for_status()
            live_coins = await response.json(loads=orjson.loads)

        for coin in live_coins:
            if coin.get('mint') == mint_address:
                return _process_livestream_coin(coin, has_jwt)

        return {"is_live": False, "participants": 0, "replies": 0, "auth_used": has_jwt}
    except Exception as e:
        if has_jwt and "401" in str(e):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
                    response.raise_for_status()
                    live_coins = await response.json(loads=orjson.loads)

                for coin in live_coins:
                    if coin.get('mint') == mint_address:
                        return _process_livestream_coin(coin, False, fallback_used=True)

                return {"is_live": False, "participants": 0, "replies": 0, "auth_used": False, "fallback_used": True}
            except Exception as fallback_error:
                return {"error": f"Auth failed: {str(e)}, Fallback failed: {str(fallback_error)}"}

        return {"error": str(e), "auth_used": has_jwt}

@retry()
async def get_advanced_pump_analytics(session, mint_address):
    """Get advanced analytics from pump.fun using the advanced API endpoint."""
    # Try advanced API featured endpoint first
    url = "https://advanced-api-v2.pump.fun/coins/featured"

    # Check if JWT token is properly configured
    has_jwt = PUMP_FUN_JWT and PUMP_FUN_JWT != "your_pump_fun_jwt_token_here"

    if has_jwt:
        headers = {
            "Authorization": f"Bearer {PUMP_FUN_JWT}",
            "Content-Type": "application/json"
        }
    else:
        headers = {"Content-Type": "application/json"}

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=3)) as response:
            # If advanced API fails, fallback to old endpoint
            if response.status == 404 or response.status == 401:
                return await get_basic_pump_analytics(session, mint_address)

            response.raise_for_status()
            data = await response.json(loads=orjson.loads)

        # Search for our token in the featured coins list
        coins = data.get('coins', [])
        coin = next((c for c in coins if c.get('coinMint') == mint_address), None)

        if not coin:
            # Token not in featured list, fallback to basic endpoint
            return await get_basic_pump_analytics(session, mint_address)

        # Advanced API returns comprehensive data
        return {
            "found": True,
            "bondingCurveProgress": coin.get('bondingCurveProgress', 0),
            "allTimeHighMarketCap": coin.get('allTimeHighMarketCap', 0),
            "marketCap": coin.get('marketCap', 0),
            "numHolders": coin.get('numHolders'),
            "sniperCount": coin.get('sniperCount'),
            "sniperOwnedPercentage": coin.get('sniperOwnedPercentage'),
            "topHoldersPercentage": coin.get('topHoldersPercentage'),
            "devHoldingsPercentage": coin.get('devHoldingsPercentage'),
            "twitterReuseCount": coin.get('twitterReuseCount'),
            "buyTransactions": coin.get('buyTransactions'),
            "sellTransactions": coin.get('sellTransactions'),
            "transactions": coin.get('transactions'),
            "graduationDate": coin.get('graduationDate'),
            "hasTwitter": coin.get('hasTwitter', False),
            "hasTelegram": coin.get('hasTelegram', False),
            "hasWebsite": coin.get('hasWebsite', False),
            "hasSocial": coin.get('hasSocial', False),
            # Add social links
            "twitter": coin.get('twitter'),
            "telegram": coin.get('telegram'),
            "website": coin.get('website'),
        }
    except Exception as e:
        # Fallback to basic endpoint if advanced fails
        return await get_basic_pump_analytics(session, mint_address)

@retry()
async def get_basic_pump_analytics(session, mint_address):
    """Fallback to basic pump.fun endpoint if advanced API fails."""
    url = f"https://frontend-api-v3.pump.fun/coins/{mint_address}"

    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=3)) as response:
            if response.status == 404:
                return {"found": False}

            response.raise_for_status()
            coin = await response.json(loads=orjson.loads)

        return {
            "found": True,
            "bondingCurveProgress": coin.get('bonding_curve_progress', 0),
            "allTimeHighMarketCap": coin.get('ath_market_cap', 0),
            "marketCap": coin.get('market_cap', 0),
            "usd_market_cap": coin.get('usd_market_cap', 0),
            "hasTwitter": bool(coin.get('twitter')),
            "hasTelegram": bool(coin.get('telegram')),
            "hasWebsite": bool(coin.get('website')),
            "hasSocial": any([coin.get('twitter'), coin.get('telegram'), coin.get('website')]),
            "twitter": coin.get('twitter'),
            "telegram": coin.get('telegram'),
            "website": coin.get('website'),
        }
    except Exception as e:
        return {"error": str(e)}

async def get_pump_analytics_fast(session, mint_address):
    """Get pump analytics using parallel advanced+basic approach"""
    advanced_task = asyncio.create_task(get_advanced_pump_analytics(session, mint_address))
    basic_task = asyncio.create_task(get_basic_pump_analytics(session, mint_address))

    done, pending = await asyncio.wait([advanced_task, basic_task], return_when=asyncio.FIRST_COMPLETED)

    # Cancel remaining tasks
    for task in pending:
        task.cancel()

    # Return first successful result
    for task in done:
        result = await task
        if not isinstance(result, Exception) and result.get("found", True):
            return result

    return {"found": False}

async def _get_creator_data(session, mint_address, asset_data_task):
    """Helper to get creator balance and SOL balance as soon as asset_data is ready."""
    try:
        # Wait for asset_data task to complete
        asset_result = await asset_data_task

        if not isinstance(asset_result, Exception) and "error" not in asset_result and asset_result.get("result", {}).get("creators"):
            creators = asset_result["result"]["creators"]
            if creators:
                creator_address = creators[0].get("address")
                if creator_address:
                    creator_balance_task = get_creator_balance(session, creator_address, mint_address)
                    sol_balance_task = get_sol_balance(session, creator_address)
                    creator_balance, sol_balance = await asyncio.gather(
                        creator_balance_task, sol_balance_task, return_exceptions=True
                    )
                    return creator_balance, sol_balance
    except Exception:
        pass
    return None, None




async def analyze_token(mint_address):
    """Perform complete token analysis using all available endpoints"""
    result = {"mint_address": mint_address}

    connector = aiohttp.TCPConnector(limit=100, limit_per_host=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = {
            "metadata_v1": query_metadata_v1(session, mint_address),
            "largest_accounts": get_token_largest_accounts(session, mint_address),
            "asset_data": get_asset(session, mint_address),
            "supply_info": get_token_supply_info(session, mint_address),
            "account_info": get_account_info(session, mint_address),
            "price_data": get_token_price(session, mint_address),
            "livestream_status": get_livestream_status(session, mint_address),
            "advanced_pump_analytics": get_pump_analytics_fast(session, mint_address),
        }

        # Start creator data task in parallel - it will wait for asset_data internally
        creator_data_task = asyncio.create_task(
            _get_creator_data(session, mint_address, tasks["asset_data"])
        )

        # Run main tasks and creator task in parallel
        main_results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        result.update(dict(zip(tasks.keys(), main_results)))

        # Get creator data result
        creator_balance, sol_balance = await creator_data_task
        if creator_balance:
            result["creator_balance"] = creator_balance
        if sol_balance:
            result["creator_sol_balance"] = sol_balance

    return result

import cProfile

async def main():
    mint_address = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    with cProfile.Profile() as pr:
        result = await analyze_token(mint_address)
    pr.print_stats(sort='cumulative')
    print(orjson.dumps(result, option=orjson.OPT_INDENT_2))

if __name__ == "__main__":
    asyncio.run(main())
