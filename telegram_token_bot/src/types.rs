use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenData {
    pub mint_address: String,
    pub metadata: Option<MetadataResponse>,
    pub dexscreener_data: Option<DexScreenerData>,
    pub holders: Option<HoldersData>,
    pub supply_info: Option<SupplyInfo>,
    pub creator_info: Option<CreatorInfo>,
    pub pump_fun_data: Option<PumpFunData>,
    pub jupiter_data: Option<JupiterTokenData>,
    pub dexscreener_orders_data: Option<Vec<DexScreenerOrder>>,
    pub dev_sol_balance: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DexScreenerOrder {
    pub r#type: String,
    pub status: String,
    pub payment_timestamp: i64,
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
pub struct DexScreenerData {
    pub pairs: Option<Vec<TokenPair>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenPair {
    #[serde(rename = "chainId")]
    pub chain_id: Option<String>,
    #[serde(rename = "dexId")]
    pub dex_id: Option<String>,
    pub url: Option<String>,
    #[serde(rename = "pairAddress")]
    pub pair_address: Option<String>,
    #[serde(rename = "baseToken")]
    pub base_token: Option<BaseToken>,
    #[serde(rename = "quoteToken")]
    pub quote_token: Option<QuoteToken>,
    #[serde(rename = "priceNative")]
    pub price_native: Option<String>,
    #[serde(rename = "priceUsd")]
    pub price_usd: Option<String>,
    pub txns: Option<Transactions>,
    pub volume: Option<Volume>,
    #[serde(rename = "priceChange")]
    pub price_change: Option<PriceChange>,
    pub liquidity: Option<Liquidity>,
    pub fdv: Option<f64>,
    #[serde(rename = "marketCap")]
    pub market_cap: Option<f64>,
    #[serde(rename = "pairCreatedAt")]
    pub pair_created_at: Option<i64>,
    pub info: Option<Info>,
    pub boosts: Option<Boosts>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Boosts {
    pub active: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BaseToken {
    pub address: Option<String>,
    pub name: Option<String>,
    pub symbol: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct QuoteToken {
    pub address: Option<String>,
    pub name: Option<String>,
    pub symbol: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Transactions {
    pub m5: Option<TxnData>,
    pub h1: Option<TxnData>,
    pub h6: Option<TxnData>,
    pub h24: Option<TxnData>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TxnData {
    pub buys: Option<i64>,
    pub sells: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Volume {
    pub h24: Option<f64>,
    pub h6: Option<f64>,
    pub h1: Option<f64>,
    pub m5: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceChange {
    pub m5: Option<f64>,
    pub h1: Option<f64>,
    pub h6: Option<f64>,
    pub h24: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Liquidity {
    pub usd: Option<f64>,
    pub base: Option<f64>,
    pub quote: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Info {
    #[serde(rename = "imageUrl")]
    pub image_url: Option<String>,
    pub websites: Option<Vec<Website>>,
    pub socials: Option<Vec<Social>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Website {
    pub url: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Social {
    pub platform: Option<String>,
    pub handle: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HoldersData {
    pub result: Option<HoldersResult>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HoldersResult {
    pub context: Option<Context>,
    pub value: Option<Vec<TokenHolder>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Context {
    pub slot: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TokenHolder {
    pub address: Option<String>,
    pub amount: Option<String>,
    pub decimals: Option<u8>,
    #[serde(rename = "uiAmount")]
    pub ui_amount: Option<f64>,
    #[serde(rename = "uiAmountString")]
    pub ui_amount_string: Option<String>,
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
pub struct PumpFunData {
    pub mint: Option<String>,
    pub name: Option<String>,
    pub symbol: Option<String>,
    pub description: Option<String>,
    pub image_uri: Option<String>,
    pub metadata_uri: Option<String>,
    pub twitter: Option<String>,
    pub telegram: Option<String>,
    pub website: Option<String>,
    pub bonding_curve: Option<String>,
    pub associated_bonding_curve: Option<String>,
    pub creator: Option<String>,
    pub created_timestamp: Option<i64>,
    pub last_trade_timestamp: Option<i64>,
    pub ath_market_cap_timestamp: Option<i64>,
    pub king_of_the_hill_timestamp: Option<i64>,
    pub total_supply: Option<u64>,
    pub market_cap: Option<f64>,
    pub usd_market_cap: Option<f64>,
    pub ath_market_cap: Option<f64>,
    pub real_sol_reserves: Option<f64>,
    pub virtual_sol_reserves: Option<f64>,
    pub virtual_token_reserves: Option<f64>,
    pub real_token_reserves: Option<f64>,
    pub reply_count: Option<u64>,
    pub num_participants: Option<u64>,
    pub is_currently_live: Option<bool>,
    pub complete: Option<bool>,
    pub raydium_pool: Option<String>,
    pub pump_swap_pool: Option<String>,
    pub hidden: Option<bool>,
    pub show_name: Option<bool>,
    pub nsfw: Option<bool>,
    pub inverted: Option<bool>,
    pub is_banned: Option<bool>,
    pub initialized: Option<bool>,
    pub hide_banner: Option<bool>,
    pub livestream_ban_expiry: Option<i64>,
    pub livestream_downrank_score: Option<f64>,
    pub downrank_score: Option<f64>,
    pub program: Option<String>,
    pub platform: Option<String>,
    pub market_id: Option<String>,
    pub updated_at: Option<i64>,
    pub last_reply: Option<i64>,
    pub thumbnail_updated_at: Option<i64>,
    pub banner_uri: Option<String>,
    pub thumbnail: Option<String>,
    pub video_uri: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct JupiterTokenData {
    pub id: String,
    pub name: String,
    pub symbol: String,
    #[serde(default)]
    pub icon: Option<String>,
    pub decimals: u8,
    #[serde(default)]
    pub dev: Option<String>,
    #[serde(default)]
    pub circ_supply: Option<f64>,
    #[serde(default)]
    pub total_supply: Option<f64>,
    pub token_program: String,
    #[serde(default)]
    pub launchpad: Option<String>,
    #[serde(default)]
    pub first_pool: Option<FirstPool>,
    #[serde(default)]
    pub graduated_pool: Option<String>,
    #[serde(default)]
    pub graduated_at: Option<String>,
    #[serde(default)]
    pub holder_count: Option<u64>,
    #[serde(default)]
    pub audit: Option<Audit>,
    #[serde(default)]
    pub organic_score: Option<f64>,
    #[serde(default)]
    pub organic_score_label: Option<String>,
    #[serde(default)]
    pub tags: Option<Vec<String>>,
    #[serde(default)]
    pub fdv: Option<f64>,
    #[serde(default)]
    pub mcap: Option<f64>,
    #[serde(default)]
    pub usd_price: Option<f64>,
    #[serde(default)]
    pub price_block_id: Option<u64>,
    #[serde(default)]
    pub liquidity: Option<f64>,
    #[serde(rename = "stats5m", default)]
    pub stats_5m: Option<Stats>,
    #[serde(rename = "stats1h", default)]
    pub stats_1h: Option<Stats>,
    #[serde(rename = "stats6h", default)]
    pub stats_6h: Option<Stats>,
    #[serde(rename = "stats24h", default)]
    pub stats_24h: Option<Stats>,
    #[serde(default)]
    pub bonding_curve: Option<f64>,
    pub updated_at: String,
    #[serde(default)]
    pub twitter: Option<String>,
    #[serde(default)]
    pub telegram: Option<String>,
    #[serde(default)]
    pub website: Option<String>,
    #[serde(default)]
    pub ct_likes: Option<u64>,
    #[serde(rename = "isVerified", default)]
    pub is_verified: Option<bool>,
    #[serde(default)]
    pub cexes: Option<Vec<String>>,
    #[serde(rename = "smartCtLikes", default)]
    pub smart_ct_likes: Option<u64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FirstPool {
    pub id: String,
    pub created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Audit {
    #[serde(default)]
    pub mint_authority_disabled: Option<bool>,
    #[serde(default)]
    pub freeze_authority_disabled: Option<bool>,
    #[serde(default)]
    pub top_holders_percentage: Option<f64>,
    #[serde(default)]
    pub snipers_holding_percentage: Option<f64>,
    #[serde(default)]
    pub dev_migrations: Option<u64>,
    #[serde(rename = "devBalancePercentage", default)]
    pub dev_balance_percentage: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Stats {
    #[serde(default)]
    pub price_change: Option<f64>,
    #[serde(default)]
    pub holder_change: Option<f64>,
    #[serde(default)]
    pub liquidity_change: Option<f64>,
    #[serde(default)]
    pub volume_change: Option<f64>,
    #[serde(default)]
    pub buy_volume: Option<f64>,
    #[serde(default)]
    pub sell_volume: Option<f64>,
    #[serde(default)]
    pub buy_organic_volume: Option<f64>,
    #[serde(default)]
    pub sell_organic_volume: Option<f64>,
    #[serde(default)]
    pub num_buys: Option<u64>,
    #[serde(default)]
    pub num_sells: Option<u64>,
    #[serde(default)]
    pub num_traders: Option<u64>,
    #[serde(default)]
    pub num_organic_buyers: Option<u64>,
    #[serde(default)]
    pub num_net_buyers: Option<u64>,
}
