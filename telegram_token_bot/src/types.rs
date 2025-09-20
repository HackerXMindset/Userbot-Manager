use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenData {
    pub mint_address: String,
    pub metadata: Option<MetadataResponse>,
    pub price_data: Option<PriceData>,
    pub holders: Option<HoldersData>,
    pub supply_info: Option<SupplyInfo>,
    pub creator_info: Option<CreatorInfo>,
    pub pump_analytics: Option<PumpAnalytics>,
    pub livestream: Option<LivestreamData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MetadataResponse {
    #[serde(rename = "onChainMetadata")]
    pub on_chain_metadata: Option<OnChainMetadata>,
    #[serde(rename = "offChainMetadata")]
    pub off_chain_metadata: Option<OffChainMetadata>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OnChainMetadata {
    pub metadata: Option<TokenMetadata>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenMetadata {
    pub data: TokenMetadataData,
    #[serde(rename = "isMutable")]
    pub is_mutable: Option<bool>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenMetadataData {
    pub name: Option<String>,
    pub symbol: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OffChainMetadata {
    pub metadata: Option<OffChainTokenData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OffChainTokenData {
    pub name: Option<String>,
    pub symbol: Option<String>,
    pub description: Option<String>,
    pub image: Option<String>,
    pub twitter: Option<String>,
    pub telegram: Option<String>,
    pub website: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceData {
    pub pairs: Option<Vec<TokenPair>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenPair {
    #[serde(rename = "priceUsd")]
    pub price_usd: Option<String>,
    #[serde(rename = "marketCap")]
    pub market_cap: Option<f64>,
    pub volume: Option<VolumeData>,
    #[serde(rename = "priceChange")]
    pub price_change: Option<PriceChangeData>,
    pub liquidity: Option<LiquidityData>,
    #[serde(rename = "dexId")]
    pub dex_id: Option<String>,
    #[serde(rename = "pairCreatedAt")]
    pub pair_created_at: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct VolumeData {
    pub h1: Option<f64>,
    pub h6: Option<f64>,
    pub h24: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceChangeData {
    pub h1: Option<f64>,
    pub h6: Option<f64>,
    pub h24: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LiquidityData {
    pub usd: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HoldersData {
    pub result: Option<HoldersResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HoldersResult {
    pub value: Option<Vec<TokenHolder>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenHolder {
    pub address: Option<String>,
    #[serde(rename = "uiAmount")]
    pub ui_amount: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupplyInfo {
    pub result: Option<SupplyResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupplyResult {
    pub value: Option<SupplyValue>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SupplyValue {
    #[serde(rename = "uiAmount")]
    pub ui_amount: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CreatorInfo {
    pub address: String,
    pub balance: Option<f64>,
    pub sol_balance: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PumpAnalytics {
    pub found: Option<bool>,
    #[serde(rename = "bondingCurveProgress")]
    pub bonding_curve_progress: Option<f64>,
    #[serde(rename = "allTimeHighMarketCap")]
    pub ath_market_cap: Option<f64>,
    #[serde(rename = "marketCap")]
    pub market_cap: Option<f64>,
    #[serde(rename = "numHolders")]
    pub num_holders: Option<u64>,
    #[serde(rename = "sniperCount")]
    pub sniper_count: Option<u64>,
    #[serde(rename = "sniperOwnedPercentage")]
    pub sniper_owned_percentage: Option<f64>,
    #[serde(rename = "devHoldingsPercentage")]
    pub dev_holdings_percentage: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LivestreamData {
    pub is_live: Option<bool>,
    pub participants: Option<u64>,
    pub replies: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ApiError {
    pub error: String,
}