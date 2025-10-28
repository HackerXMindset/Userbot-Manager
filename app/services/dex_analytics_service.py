import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp

from app.config import settings
from app.services.dexscreener_api import get_dexscreener_client
from app.services.jupiter_api import get_jupiter_service
from app.services.okx_market_api import get_okx_market_client

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    """Convert value to float if possible."""
    try:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            return float(value.strip())
    except (TypeError, ValueError):
        return None
    return None


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str) and value.strip():
            return int(float(value.strip()))
    except (TypeError, ValueError):
        return None
    return None


class DexAnalyticsService:
    """Python implementation of the Rust analytics HTTP service."""

    def __init__(self) -> None:
        self._session: Optional[aiohttp.ClientSession] = None
        self._session_lock = asyncio.Lock()
        self._dex_client = get_dexscreener_client()
        self._jupiter = get_jupiter_service()
        self._okx = get_okx_market_client()

    async def _ensure_clients(self) -> None:
        """Ensure HTTP session and dependent clients are ready."""
        async with self._session_lock:
            if not self._session or self._session.closed:
                timeout = aiohttp.ClientTimeout(total=10)
                self._session = aiohttp.ClientSession(timeout=timeout)
        await self._dex_client.start()
        await self._jupiter.start()
        await self._okx.start()

    async def fetch_solana_payload(self, token_address: str) -> Optional[Dict[str, Any]]:
        await self._ensure_clients()

        pairs_data = await self._fetch_dexscreener_latest(token_address)
        orders = await self._fetch_orders("solana", token_address)
        pump_fun = await self._fetch_pump_fun(token_address)
        jupiter = await self._jupiter.get_token_data(token_address, use_cache=False)

        dev_sol_balance = None
        dev_token_holding = None
        if jupiter:
            dev_address = jupiter.get("dev")
            if dev_address:
                dev_sol_balance = await self._get_sol_balance(dev_address)
                dev_token_holding = await self._get_dev_token_holding(dev_address, token_address)

        holders = await self._get_token_largest_accounts(token_address)
        supply_ui_amount = await self._get_token_supply_ui_amount(token_address)
        vamped_fun = await self._fetch_vamped_fun(token_address)

        payload = {
            "pairs": pairs_data.get("pairs") if pairs_data else [],
            "orders": orders or [],
            "pump_fun": pump_fun,
            "jupiter": jupiter,
            "dev_sol_balance": dev_sol_balance,
            "holders": holders,
            "supply_ui_amount": supply_ui_amount,
            "dev_token_holding": dev_token_holding,
            "vamped_fun": vamped_fun,
        }

        return payload

    async def fetch_bnb_payload(self, token_address: str) -> Optional[Dict[str, Any]]:
        await self._ensure_clients()

        chains = ["bsc", "base", "op", "eth"]
        best_pair: Dict[str, Any] = {}
        inferred_chain = "bsc"
        pairs: Optional[List[Dict[str, Any]]] = None

        for chain in chains:
            try:
                chain_pairs = await self._dex_client.fetch_token_pairs(
                    token_address,
                    chain_id=chain,
                    use_cache=False,
                )
            except Exception as exc:  # pragma: no cover
                logger.error(
                    "DexScreener fetch failed for %s on %s: %s", token_address, chain, exc
                )
                continue

            if chain_pairs:
                pairs = chain_pairs
                inferred_chain = chain
                best_pair = self._select_best_pair(chain_pairs)
                break

        okx_data = None
        if inferred_chain:
            okx_data = await self._okx.fetch_token_info(
                token_address, chain_id=inferred_chain, use_cache=False
            )

        if not best_pair and not okx_data:
            logger.warning("No analytics available for BNB token %s", token_address)
            return None

        chain_id = best_pair.get("chainId") or (okx_data or {}).get("chainName") or inferred_chain

        orders = await self._fetch_orders(chain_id, token_address)

        base_token = best_pair.get("baseToken") if best_pair else {}
        price_change = best_pair.get("priceChange") if best_pair else {}
        volume = best_pair.get("volume") if best_pair else {}
        liquidity = best_pair.get("liquidity") if best_pair else {}
        info = best_pair.get("info") if best_pair else {}

        normalized_pairs = []
        for pair in pairs or []:
            normalized = dict(pair)
            normalized["labels"] = pair.get("labels") or []
            normalized["liquidity"] = pair.get("liquidity") or {}
            normalized["volume"] = pair.get("volume") or {}
            normalized["priceChange"] = pair.get("priceChange") or {}
            normalized_pairs.append(normalized)

        socials: List[str] = []
        for social in (info or {}).get("socials", []) or []:
            handle = (social.get("handle") or "").strip()
            platform = (social.get("platform") or "").strip()
            if handle:
                label = platform.title() if platform else "Social"
                socials.append(f"{label}: {handle}")

        payload: Dict[str, Any] = {
            "contract_address": token_address,
            "name": (base_token or {}).get("name")
            or (okx_data or {}).get("tokenName")
            or token_address,
            "symbol": (base_token or {}).get("symbol")
            or (okx_data or {}).get("tokenSymbol")
            or "?",
            "price": _safe_float(
                (okx_data or {}).get("price") or (best_pair or {}).get("priceUsd")
            ),
            "change_24h": _safe_float(
                (okx_data or {}).get("change") or (price_change or {}).get("h24")
            ),
            "change_4h": _safe_float(
                (okx_data or {}).get("change4H") or (price_change or {}).get("h6")
            ),
            "change_1h": _safe_float(
                (okx_data or {}).get("change1H") or (price_change or {}).get("h1")
            ),
            "change_5m": _safe_float(
                (okx_data or {}).get("change5M") or (price_change or {}).get("m5")
            ),
            "market_cap": _safe_float(
                (okx_data or {}).get("marketCap")
                or (best_pair or {}).get("fdv")
                or (best_pair or {}).get("marketCap")
            ),
            "liquidity": _safe_float(
                (okx_data or {}).get("liquidity") or (liquidity or {}).get("usd")
            ),
            "volume_24h": _safe_float(
                (okx_data or {}).get("volume") or (volume or {}).get("h24")
            ),
            "holders": _safe_int((okx_data or {}).get("holders")),
            "top10_hold_percentage": _safe_float(
                (okx_data or {}).get("top10_hold_amount_percentage")
            ),
            "dev_holding_ratio": _safe_float((okx_data or {}).get("dev_holding_ratio")),
            "risk_level": _safe_int((okx_data or {}).get("riskLevel")),
            "chain_name": (okx_data or {}).get("chainName") or str(chain_id).upper(),
            "token_logo_url": (okx_data or {}).get("tokenLogoUrl")
            or (okx_data or {}).get("tokenLargeLogoUrl")
            or (info or {}).get("imageUrl"),
            "holder_maps_url": (okx_data or {}).get("tokenThirdPartInfo", {}).get(
                "okxWebSiteUrl"
            ),
            "bubble_maps_url": (okx_data or {}).get("tokenThirdPartInfo", {}).get(
                "thirdPartyWebSiteUrl"
            ),
            "dex_socials": " | ".join(socials) if socials else None,
            "dexscreener_data": {"pairs": normalized_pairs} if normalized_pairs else None,
            "dexscreener_token_summary": normalized_pairs,
            "dexscreener_orders_data": orders or [],
        }

        return payload

    async def _fetch_dexscreener_latest(self, token_address: str) -> Optional[Dict[str, Any]]:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        session = self._session
        if not session:
            return None

        try:
            async with session.get(url) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(
                        "DexScreener latest error %s for %s: %s",
                        response.status,
                        token_address,
                        text[:200],
                    )
                    return None
                return await response.json()
        except aiohttp.ClientError as exc:
            logger.error("DexScreener latest request failed for %s: %s", token_address, exc)
        return None

    async def _fetch_orders(self, chain_id: str, token_address: str) -> Optional[List[Dict[str, Any]]]:
        url = f"https://api.dexscreener.com/orders/v1/{chain_id}/{token_address}"
        session = self._session
        if not session:
            return None

        try:
            async with session.get(url) as response:
                if response.status == 404:
                    return []
                if response.status != 200:
                    text = await response.text()
                    logger.error(
                        "DexScreener orders error %s for %s: %s",
                        response.status,
                        token_address,
                        text[:200],
                    )
                    return None
                return await response.json()
        except aiohttp.ClientError as exc:
            logger.error("DexScreener orders request failed for %s: %s", token_address, exc)
        return None

    async def _fetch_pump_fun(self, token_address: str) -> Optional[Dict[str, Any]]:
        jwt = getattr(settings, "pump_fun_jwt", None)
        if not jwt:
            jwt = getattr(settings, "PUMP_FUN_JWT", None)

        if not jwt:
            from os import getenv

            jwt = getenv("PUMP_FUN_JWT")

        url = f"https://frontend-api-v3.pump.fun/coins/{token_address}?sync=true"
        headers = {"Accept": "application/json"}
        if jwt:
            headers["Authorization"] = f"Bearer {jwt}"

        session = self._session
        if not session:
            return None

        try:
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    return None
                if response.status != 200:
                    text = await response.text()
                    logger.warning(
                        "Pump.fun error %s for %s: %s",
                        response.status,
                        token_address,
                        text[:200],
                    )
                    return None
                return await response.json()
        except aiohttp.ClientError as exc:
            logger.error("Pump.fun request failed for %s: %s", token_address, exc)
        return None

    async def _fetch_vamped_fun(self, token_address: str) -> Optional[Dict[str, Any]]:
        url = "https://www.vamped.fun/api/check-token"
        payload = {"mintAddress": token_address}
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://www.vamped.fun",
            "Referer": "https://www.vamped.fun/",
        }

        session = self._session
        if not session:
            return None

        try:
            async with session.post(url, json=payload, headers=headers) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.warning(
                        "Vamped.fun error %s for %s: %s",
                        response.status,
                        token_address,
                        text[:200],
                    )
                    return None
                return await response.json()
        except aiohttp.ClientError as exc:
            logger.error("Vamped.fun request failed for %s: %s", token_address, exc)
        return None

    async def _get_sol_balance(self, address: str) -> Optional[float]:
        api_key = getattr(settings, "helius_api_key", None)
        if not api_key:
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getBalance",
            "params": [address],
        }
        url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

        session = self._session
        if not session:
            return None

        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    return None
                data = await response.json()
        except aiohttp.ClientError:
            return None

        try:
            lamports = data.get("result", {}).get("value")
            if lamports is not None:
                return float(lamports) / 1_000_000_000.0
        except (TypeError, ValueError):
            return None
        return None

    async def _get_dev_token_holding(self, owner: str, mint: str) -> Optional[Dict[str, Any]]:
        api_key = getattr(settings, "helius_api_key", None)
        if not api_key:
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenAccountsByOwner",
            "params": [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
        }
        url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

        session = self._session
        if not session:
            return None

        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    return None
                data = await response.json()
        except aiohttp.ClientError:
            return None

        try:
            value = data.get("result", {}).get("value")
            if isinstance(value, list) and value:
                account = value[0]
                return account
        except (TypeError, ValueError):
            return None
        return None

    async def _get_token_largest_accounts(self, mint_address: str) -> Optional[Dict[str, Any]]:
        api_key = getattr(settings, "helius_api_key", None)
        if not api_key:
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenLargestAccounts",
            "params": [mint_address],
        }
        url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

        session = self._session
        if not session:
            return None

        try:
            async with session.post(url, json=payload) as response:
                if response.status != 200:
                    return None
                return await response.json()
        except aiohttp.ClientError as exc:
            logger.error("Helius largest accounts failed for %s: %s", mint_address, exc)
        return None

    async def _get_token_supply_ui_amount(self, mint_address: str) -> Optional[float]:
        api_key = getattr(settings, "helius_api_key", None)
        if not api_key:
            return None

        payload = {
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenSupply",
            "params": [mint_address],
        }
        url = f"https://mainnet.helius-rpc.com/?api-key={api_key}"

        try:
            async with self._session.post(url, json=payload) as response:  # type: ignore[arg-type]
                if response.status != 200:
                    return None
                data = await response.json()
        except aiohttp.ClientError:
            return None

        result = data.get("result", {}) if isinstance(data, dict) else {}
        value = result.get("value") if isinstance(result, dict) else {}
        ui_amount = value.get("uiAmount")
        return _safe_float(ui_amount)

    @staticmethod
    def _select_best_pair(pairs: List[Dict[str, Any]]) -> Dict[str, Any]:
        def score(pair: Dict[str, Any]) -> float:
            liquidity = pair.get("liquidity") or {}
            usd = liquidity.get("usd")
            try:
                return float(usd)
            except (TypeError, ValueError):
                return 0.0

        return max(pairs, key=score)


# Singleton instance for reuse across the app
_analytics_instance: Optional[DexAnalyticsService] = None


def get_dex_analytics_service() -> DexAnalyticsService:
    global _analytics_instance
    if _analytics_instance is None:
        _analytics_instance = DexAnalyticsService()
    return _analytics_instance
