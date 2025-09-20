import requests
import json
import sys

API_KEY = "a618b55d-ced7-473c-84a5-fbc2bf34ce97"
PUMP_FUN_JWT = "eyJhbGciOiJFUzI1NiIsInR5cCI6IkpXVCIsImtpZCI6IkRmYnlOelZjdkZrX0ltUVBGTFNTb1NMTTR5eUVBenVqdGVNa01GeEpRWWcifQ.eyJzaWQiOiJjbWZvbG1jcm4wMDA3anIwYnNydmUwMGc5IiwiaXNzIjoicHJpdnkuaW8iLCJpYXQiOjE3NTgxNTA4NDgsImF1ZCI6ImNtMXAyZ3pvdDAzZnpxdHk1eHpnamd0aHEiLCJzdWIiOiJkaWQ6cHJpdnk6Y21mb2t6OTNkMDA2MGw4MGIzY2duM2l1dSIsImV4cCI6MTc1ODE1NDQ0OH0.rARcbkTAFj4IFlGTlr20Px0pA8IQJG-13MUPKunj1u9rnp_0m_SEnGozRE6eW27CQq1AccL_tMv66OrMUWDNeg"

def query_metadata_v1(mint_address):
    """Fetch token metadata using Helius queryMetadataV1 endpoint"""
    url = f"https://api.helius.xyz/v0/token-metadata?api-key={API_KEY}"
    payload = {
        "mintAccounts": [mint_address],
        "includeOffChain": True,
        "disableCache": False
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_token_largest_accounts(mint_address):
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_asset(mint_address):
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_transaction_history(mint_address, limit=50):
    """Get recent transaction history for token"""
    url = f"https://mainnet.helius-rpc.com/?api-key={API_KEY}"
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "getSignaturesForAddress",
        "params": [mint_address, {"limit": limit}]
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_token_supply_info(mint_address):
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_account_info(mint_address):
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_token_price(mint_address):
    """Get token price from DexScreener API"""
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{mint_address}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_creator_balance(creator_address, mint_address):
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_sol_balance(address):
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
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}

def get_livestream_status(mint_address):
    """Check if token is currently live on pump.fun"""
    url = "https://frontend-api-v3.pump.fun/coins/currently-live?offset=0&limit=1000&includeNsfw=false&order=DESC"

    # Check if JWT token is properly configured
    has_jwt = PUMP_FUN_JWT and PUMP_FUN_JWT != "your_pump_fun_jwt_token_here"

    if has_jwt:
        headers = {
            "Authorization": f"Bearer {PUMP_FUN_JWT}"
        }
    else:
        headers = {}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        live_coins = response.json()

        # Find the token by mint address
        for coin in live_coins:
            if coin.get('mint') == mint_address:
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
                    "auth_used": has_jwt
                }

        # Token not found in live list
        return {"is_live": False, "participants": 0, "replies": 0, "auth_used": has_jwt}
    except Exception as e:
        # If auth failed, try without authentication as fallback
        if has_jwt and "401" in str(e):
            try:
                response = requests.get(url, timeout=10)
                response.raise_for_status()
                live_coins = response.json()

                for coin in live_coins:
                    if coin.get('mint') == mint_address:
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
                            "auth_used": False,
                            "fallback_used": True
                        }
                return {"is_live": False, "participants": 0, "replies": 0, "auth_used": False, "fallback_used": True}
            except Exception as fallback_error:
                return {"error": f"Auth failed: {str(e)}, Fallback failed: {str(fallback_error)}"}

        return {"error": str(e), "auth_used": has_jwt}

def get_advanced_pump_analytics(mint_address):
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
        response = requests.get(url, headers=headers, timeout=10)

        # If advanced API fails, fallback to old endpoint
        if response.status_code == 404 or response.status_code == 401:
            return get_basic_pump_analytics(mint_address)

        response.raise_for_status()
        data = response.json()

        # Search for our token in the featured coins list
        coins = data.get('coins', [])
        coin = next((c for c in coins if c.get('coinMint') == mint_address), None)

        if not coin:
            # Token not in featured list, fallback to basic endpoint
            return get_basic_pump_analytics(mint_address)

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
        return get_basic_pump_analytics(mint_address)

def get_basic_pump_analytics(mint_address):
    """Fallback to basic pump.fun endpoint if advanced API fails."""
    url = f"https://frontend-api-v3.pump.fun/coins/{mint_address}"

    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 404:
            return {"found": False}

        response.raise_for_status()
        coin = response.json()

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


def analyze_token(mint_address):
    """Perform complete token analysis using all available endpoints"""
    result = {"mint_address": mint_address}

    # Get metadata using queryMetadataV1
    metadata_result = query_metadata_v1(mint_address)
    if "error" not in metadata_result and metadata_result:
        result["metadata_v1"] = metadata_result[0] if metadata_result else {}

    # Get largest holders
    holders_result = get_token_largest_accounts(mint_address)
    if "error" not in holders_result:
        result["largest_accounts"] = holders_result

    # Get asset data
    asset_result = get_asset(mint_address)
    if "error" not in asset_result:
        result["asset_data"] = asset_result

    # Get transaction history
    tx_history = get_transaction_history(mint_address, 10)
    if "error" not in tx_history:
        result["transaction_history"] = tx_history

    # Get token supply info
    supply_info = get_token_supply_info(mint_address)
    if "error" not in supply_info:
        result["supply_info"] = supply_info

    # Get account info
    account_info = get_account_info(mint_address)
    if "error" not in account_info:
        result["account_info"] = account_info

    # Get price data
    price_data = get_token_price(mint_address)
    if "error" not in price_data:
        result["price_data"] = price_data

    # Get creator balance and SOL balance
    if "asset_data" in result and result["asset_data"].get("result", {}).get("creators"):
        creators = result["asset_data"]["result"]["creators"]
        if creators:
            creator_address = creators[0].get("address")
            if creator_address:
                # Get creator's token balance
                creator_balance = get_creator_balance(creator_address, mint_address)
                if "error" not in creator_balance:
                    result["creator_balance"] = creator_balance

                # Get creator's SOL balance
                sol_balance = get_sol_balance(creator_address)
                if "error" not in sol_balance:
                    result["creator_sol_balance"] = sol_balance

    # Get livestream status
    livestream_data = get_livestream_status(mint_address)
    if "error" not in livestream_data:
        result["livestream_status"] = livestream_data

    # Get advanced pump.fun analytics
    advanced_analytics = get_advanced_pump_analytics(mint_address)
    if "error" not in advanced_analytics:
        result["advanced_pump_analytics"] = advanced_analytics

    return result

def main():
    while True:
        mint_address = input("What coin data do you want? Enter CA (or 'exit' to quit): ").strip()

        if mint_address.lower() == 'exit':
            print("👋 Exiting...")
            break

        if not mint_address:
            print("❌ Please enter a valid contract address.")
            continue

        result = analyze_token(mint_address)
        print(json.dumps(result, indent=1, separators=(',', ':')))
        print()  # Add blank line before next prompt

if __name__ == "__main__":
    main()
