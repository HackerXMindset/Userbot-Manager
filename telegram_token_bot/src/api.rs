use crate::types::*;
use anyhow::{Result, anyhow};
use moka::future::Cache;
use reqwest::Client;
use serde_json::{json, Value};
use std::time::Duration;
use tokio::time::timeout;

pub struct ApiClient {
    client: Client,
    api_key: String,
    cache: Cache<String, TokenData>,
}

impl ApiClient {
    pub async fn new(api_key: String) -> Result<Self> {
        // #COMPLETION_DRIVE: Assuming reqwest Client::new() always succeeds
        // #SUGGEST_VERIFY: Add error handling for client creation with custom connector

        let client = Client::builder()
            .pool_max_idle_per_host(30)
            .pool_idle_timeout(Duration::from_secs(60))
            .timeout(Duration::from_secs(5))
            .build()?;

        let cache = Cache::builder()
            .max_capacity(1000)
            .time_to_live(Duration::from_secs(60))
            .build();

        Ok(Self {
            client,
            api_key,
            cache,
        })
    }

    pub async fn analyze_token(&self, mint_address: &str) -> Result<TokenData> {
        // Check cache first
        if let Some(cached) = self.cache.get(mint_address).await {
            return Ok(cached);
        }

        // Execute all API calls concurrently
        let (
            metadata_result,
            price_result,
            holders_result,
            supply_result,
            pump_analytics_result,
            livestream_result,
        ) = tokio::join!(
            self.query_metadata_v1(mint_address),
            self.get_token_price(mint_address),
            self.get_token_largest_accounts(mint_address),
            self.get_token_supply_info(mint_address),
            self.get_advanced_pump_analytics(mint_address),
            self.get_livestream_status(mint_address)
        );

        let token_data = TokenData {
            mint_address: mint_address.to_string(),
            metadata: metadata_result.ok(),
            price_data: price_result.ok(),
            holders: holders_result.ok(),
            supply_info: supply_result.ok(),
            creator_info: None, // Will be populated later if needed
            pump_analytics: pump_analytics_result.ok(),
            livestream: livestream_result.ok(),
        };

        // Cache the result
        self.cache.insert(mint_address.to_string(), token_data.clone()).await;

        Ok(token_data)
    }

    async fn query_metadata_v1(&self, mint_address: &str) -> Result<MetadataResponse> {
        let url = format!("https://api.helius.xyz/v0/token-metadata?api-key={}", self.api_key);

        let payload = json!({
            "mintAccounts": [mint_address],
            "includeOffChain": true,
            "disableCache": false
        });

        let response = timeout(
            Duration::from_secs(3),
            self.client.post(&url)
                .json(&payload)
                .send()
        ).await??;

        let data: Vec<MetadataResponse> = response.json().await?;
        data.into_iter().next()
            .ok_or_else(|| anyhow!("No metadata found"))
    }

    async fn get_token_largest_accounts(&self, mint_address: &str) -> Result<HoldersData> {
        let url = format!("https://mainnet.helius-rpc.com/?api-key={}", self.api_key);

        let payload = json!({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenLargestAccounts",
            "params": [mint_address]
        });

        let response = timeout(
            Duration::from_secs(3),
            self.client.post(&url)
                .json(&payload)
                .send()
        ).await??;

        let data: HoldersData = response.json().await?;
        Ok(data)
    }

    async fn get_token_supply_info(&self, mint_address: &str) -> Result<SupplyInfo> {
        let url = format!("https://mainnet.helius-rpc.com/?api-key={}", self.api_key);

        let payload = json!({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenSupply",
            "params": [mint_address]
        });

        let response = timeout(
            Duration::from_secs(3),
            self.client.post(&url)
                .json(&payload)
                .send()
        ).await??;

        let data: SupplyInfo = response.json().await?;
        Ok(data)
    }

    async fn get_token_price(&self, mint_address: &str) -> Result<PriceData> {
        let url = format!("https://api.dexscreener.com/latest/dex/tokens/{}", mint_address);

        let response = timeout(
            Duration::from_secs(3),
            self.client.get(&url).send()
        ).await??;

        let data: PriceData = response.json().await?;
        Ok(data)
    }

    async fn get_livestream_status(&self, mint_address: &str) -> Result<LivestreamData> {
        let url = "https://frontend-api-v3.pump.fun/coins/currently-live?offset=0&limit=1000&includeNsfw=false&order=DESC";

        let response = timeout(
            Duration::from_secs(3),
            self.client.get(url).send()
        ).await??;

        let live_coins: Vec<Value> = response.json().await?;

        // Find token by mint address
        for coin in live_coins {
            if let Some(mint) = coin.get("mint").and_then(|v| v.as_str()) {
                if mint == mint_address {
                    return Ok(LivestreamData {
                        is_live: coin.get("is_currently_live").and_then(|v| v.as_bool()),
                        participants: coin.get("num_participants").and_then(|v| v.as_u64()),
                        replies: coin.get("reply_count").and_then(|v| v.as_u64()),
                    });
                }
            }
        }

        Ok(LivestreamData {
            is_live: Some(false),
            participants: Some(0),
            replies: Some(0),
        })
    }

    async fn get_advanced_pump_analytics(&self, mint_address: &str) -> Result<PumpAnalytics> {
        let url = "https://advanced-api-v2.pump.fun/coins/featured";

        let response = timeout(
            Duration::from_secs(3),
            self.client.get(url).send()
        ).await;

        match response {
            Ok(Ok(resp)) if resp.status().is_success() => {
                let data: Value = resp.json().await?;

                if let Some(coins) = data.get("coins").and_then(|v| v.as_array()) {
                    for coin in coins {
                        if let Some(coin_mint) = coin.get("coinMint").and_then(|v| v.as_str()) {
                            if coin_mint == mint_address {
                                return Ok(PumpAnalytics {
                                    found: Some(true),
                                    bonding_curve_progress: coin.get("bondingCurveProgress").and_then(|v| v.as_f64()),
                                    ath_market_cap: coin.get("allTimeHighMarketCap").and_then(|v| v.as_f64()),
                                    market_cap: coin.get("marketCap").and_then(|v| v.as_f64()),
                                    num_holders: coin.get("numHolders").and_then(|v| v.as_u64()),
                                    sniper_count: coin.get("sniperCount").and_then(|v| v.as_u64()),
                                    sniper_owned_percentage: coin.get("sniperOwnedPercentage").and_then(|v| v.as_f64()),
                                    dev_holdings_percentage: coin.get("devHoldingsPercentage").and_then(|v| v.as_f64()),
                                });
                            }
                        }
                    }
                }
            }
            _ => {
                // Fallback to basic endpoint
                return self.get_basic_pump_analytics(mint_address).await;
            }
        }

        Ok(PumpAnalytics {
            found: Some(false),
            bonding_curve_progress: None,
            ath_market_cap: None,
            market_cap: None,
            num_holders: None,
            sniper_count: None,
            sniper_owned_percentage: None,
            dev_holdings_percentage: None,
        })
    }

    async fn get_basic_pump_analytics(&self, mint_address: &str) -> Result<PumpAnalytics> {
        let url = format!("https://frontend-api-v3.pump.fun/coins/{}", mint_address);

        let response = timeout(
            Duration::from_secs(3),
            self.client.get(&url).send()
        ).await??;

        if response.status() == 404 {
            return Ok(PumpAnalytics {
                found: Some(false),
                bonding_curve_progress: None,
                ath_market_cap: None,
                market_cap: None,
                num_holders: None,
                sniper_count: None,
                sniper_owned_percentage: None,
                dev_holdings_percentage: None,
            });
        }

        let coin: Value = response.json().await?;

        Ok(PumpAnalytics {
            found: Some(true),
            bonding_curve_progress: coin.get("bonding_curve_progress").and_then(|v| v.as_f64()),
            ath_market_cap: coin.get("ath_market_cap").and_then(|v| v.as_f64()),
            market_cap: coin.get("market_cap").and_then(|v| v.as_f64()),
            num_holders: None,
            sniper_count: None,
            sniper_owned_percentage: None,
            dev_holdings_percentage: None,
        })
    }
}