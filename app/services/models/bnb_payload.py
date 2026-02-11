from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BnbTokenSummary(BaseModel):
    chain_id: Optional[str] = Field(None, alias="chainId")
    dex_id: Optional[str] = Field(None, alias="dexId")
    url: Optional[str] = None
    pair_address: Optional[str] = Field(None, alias="pairAddress")
    labels: Optional[List[str]] = None
    base_token: Optional[dict] = Field(None, alias="baseToken")
    quote_token: Optional[dict] = Field(None, alias="quoteToken")
    price_native: Optional[str] = Field(None, alias="priceNative")
    price_usd: Optional[str] = Field(None, alias="priceUsd")
    txns: Optional[dict] = None
    volume: Optional[dict] = None
    price_change: Optional[dict] = Field(None, alias="priceChange")
    liquidity: Optional[dict] = None
    fdv: Optional[float] = None
    market_cap: Optional[float] = Field(None, alias="marketCap")
    pair_created_at: Optional[int] = Field(None, alias="pairCreatedAt")


class BnbDexPair(BaseModel):
    chain_id: Optional[str] = Field(None, alias="chainId")
    dex_id: Optional[str] = Field(None, alias="dexId")
    url: Optional[str] = None
    pair_address: Optional[str] = Field(None, alias="pairAddress")
    labels: Optional[List[str]] = None
    base_token: Optional[dict] = Field(None, alias="baseToken")
    quote_token: Optional[dict] = Field(None, alias="quoteToken")
    price_native: Optional[str] = Field(None, alias="priceNative")
    price_usd: Optional[str] = Field(None, alias="priceUsd")
    txns: Optional[dict] = None
    volume: Optional[dict] = None
    price_change: Optional[dict] = Field(None, alias="priceChange")
    liquidity: Optional[dict] = None
    fdv: Optional[float] = None
    market_cap: Optional[float] = Field(None, alias="marketCap")
    pair_created_at: Optional[int] = Field(None, alias="pairCreatedAt")
    info: Optional[dict] = None
    boosts: Optional[dict] = None


class BnbTokenPayload(BaseModel):
    contract_address: str = Field(..., alias="contract_address")
    name: str
    symbol: str
    price: Optional[float]
    change_24h: Optional[float]
    change_4h: Optional[float]
    change_1h: Optional[float]
    change_5m: Optional[float]
    market_cap: Optional[float]
    liquidity: Optional[float]
    volume_24h: Optional[float]
    holders: Optional[int]
    top10_hold_percentage: Optional[float]
    dev_holding_ratio: Optional[float]
    risk_level: Optional[int]
    chain_name: Optional[str]
    token_logo_url: Optional[str]
    holder_maps_url: Optional[str]
    bubble_maps_url: Optional[str]
    dex_socials: Optional[str]
    dexscreener_data: Optional[dict]
    dexscreener_token_summary: Optional[List[BnbTokenSummary]]
    dexscreener_orders_data: Optional[List[dict]]

    class Config:
        allow_population_by_field_name = True
