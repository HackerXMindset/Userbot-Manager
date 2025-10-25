use crate::social::format_social_label;
use crate::types::*;
use anyhow::{anyhow, Result};
use reqwest::Client;
use serde::Serialize;
use serde_json::json;
use std::env;
use std::time::Duration;
use tokio::time::timeout;
use tracing::{debug, warn};

pub struct ApiClient {
    client: Client,
    api_key: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DexPayload {
    pub pairs: Vec<TokenPair>,
    pub orders: Vec<DexScreenerOrder>,
    pub pump_fun: Option<PumpFunData>,
    pub jupiter: Option<JupiterTokenData>,
    pub dev_sol_balance: Option<f64>,
    pub holders: Option<HoldersData>,
    pub supply_ui_amount: Option<f64>,
    pub dev_token_holding: Option<DevTokenHolding>,
    pub vamped_fun: Option<VampedFunData>,
}

impl ApiClient {
    pub async fn new(api_key: String) -> Result<Self> {
        let client = Client::builder()
            .pool_max_idle_per_host(30)
            .pool_idle_timeout(Duration::from_secs(60))
            .timeout(Duration::from_secs(5))
            .build()?;

        Ok(Self { client, api_key })
    }

    pub async fn analyze_token(&self, contract: &DetectedContract) -> Result<TokenAnalysis> {
        match contract.chain {
            Chain::Solana => self.analyze_solana_token(&contract.address).await,
            Chain::Bnb => self.analyze_bnb_token(&contract.address).await,
        }
    }

    async fn analyze_solana_token(&self, mint_address: &str) -> Result<TokenAnalysis> {
        let (
            dexscreener_result,
            holders_result,
            pump_fun_result,
            jupiter_result,
            dexscreener_orders_result,
            supply_result,
            vamped_result,
        ) = tokio::join!(
            self.get_dexscreener_data(mint_address),
            self.get_token_largest_accounts(mint_address),
            self.get_pump_fun_data(mint_address),
            self.fetch_jupiter_token_data(mint_address),
            self.get_dexscreener_orders_data("solana", mint_address),
            self.get_token_supply(mint_address),
            self.get_vamped_fun_data(mint_address),
        );

        // Fetch dev SOL balance if Jupiter data has dev address
        let dev_sol_balance = if let Ok(jupiter_data) = &jupiter_result {
            if let Some(dev_address) = &jupiter_data.dev {
                self.get_sol_balance(dev_address).await.ok()
            } else {
                None
            }
        } else {
            None
        };

        let dev_token_holding = if let Ok(jupiter_data) = &jupiter_result {
            if let Some(dev_address) = &jupiter_data.dev {
                self.get_dev_token_holding(dev_address, mint_address)
                    .await
                    .ok()
                    .flatten()
            } else {
                None
            }
        } else {
            None
        };

        let token_data = TokenData {
            mint_address: mint_address.to_string(),
            metadata: None,
            dexscreener_data: dexscreener_result.ok(),
            holders: holders_result.ok(),
            supply_info: supply_result.ok(),
            creator_info: None,
            pump_fun_data: pump_fun_result.ok(),
            jupiter_data: jupiter_result.ok(),
            dexscreener_orders_data: dexscreener_orders_result.ok(),
            dev_sol_balance,
            dev_token_holding,
            vamped_fun_data: vamped_result.ok(),
        };

        Ok(TokenAnalysis::Solana(token_data))
    }

    pub async fn analyze_bnb_token(&self, contract_address: &str) -> Result<TokenAnalysis> {
        let dexscreener_data = match self.get_dexscreener_data(contract_address).await {
            Ok(data) => Some(data),
            Err(err) => {
                warn!(
                    "DexScreener primary fetch failed for {}: {}",
                    contract_address, err
                );
                None
            }
        };

        let (dex_slug, okx_chain_id) = Self::resolve_evm_chain_context(dexscreener_data.as_ref());
        debug!(
            "evm_chain_context: address={} slug={} okx_chain={}",
            contract_address, dex_slug, okx_chain_id
        );

        let (token_summary_result, orders_result, okx_result) = tokio::join!(
            self.get_dexscreener_token_summary(dex_slug, contract_address),
            self.get_dexscreener_orders_data(dex_slug, contract_address),
            self.get_okx_latest_info(contract_address, okx_chain_id),
        );

        if let Err(err) = &token_summary_result {
            warn!(
                "DexScreener token summary fetch failed for {} on {}: {}",
                contract_address, dex_slug, err
            );
        }
        if let Err(err) = &orders_result {
            warn!(
                "DexScreener orders fetch failed for {} on {}: {}",
                contract_address, dex_slug, err
            );
        }

        let raw_data = okx_result?;
        let normalized = Self::normalize_bnb_data(
            contract_address,
            &raw_data,
            dexscreener_data,
            token_summary_result.ok(),
            orders_result.ok(),
        );
        Ok(TokenAnalysis::Bnb(normalized))
    }

    pub async fn fetch_dex_payload(&self, mint_address: &str) -> Result<DexPayload> {
        let (pairs_res, orders_res, pump_fun_res, jupiter_res, holders_res, supply_res, vamped_res) = tokio::join!(
            self.get_dexscreener_data(mint_address),
            self.get_dexscreener_orders_data("solana", mint_address),
            self.get_pump_fun_data(mint_address),
            self.fetch_jupiter_token_data(mint_address),
            self.get_token_largest_accounts(mint_address),
            self.get_token_supply(mint_address),
            self.get_vamped_fun_data(mint_address),
        );

        let pairs = pairs_res?.pairs.unwrap_or_default();
        let orders = orders_res?;
        let pump_fun = pump_fun_res.ok();
        let jupiter = jupiter_res.ok();
        let holders = holders_res.ok();
        let vamped_fun = vamped_res.ok();
        let supply_ui_amount = supply_res.ok().and_then(|info| {
            info.result
                .and_then(|res| res.value)
                .and_then(|val| val.ui_amount)
        });

        let dev_sol_balance = if let Some(jup) = &jupiter {
            if let Some(dev_address) = &jup.dev {
                self.get_sol_balance(dev_address).await.ok()
            } else {
                None
            }
        } else {
            None
        };

        let dev_token_holding = if let Some(jup) = &jupiter {
            if let Some(dev_address) = &jup.dev {
                self.get_dev_token_holding(dev_address, mint_address)
                    .await
                    .ok()
                    .flatten()
            } else {
                None
            }
        } else {
            None
        };

        Ok(DexPayload {
            pairs,
            orders,
            pump_fun,
            jupiter,
            dev_sol_balance,
            holders,
            supply_ui_amount,
            dev_token_holding,
            vamped_fun,
        })
    }

    async fn get_okx_latest_info(
        &self,
        contract_address: &str,
        chain_id: &str,
    ) -> Result<OkxTokenData> {
        let url = format!(
            "https://web3.okx.com/priapi/v1/dx/market/v2/latest/info?tokenContractAddress={}&chainId={}",
            contract_address, chain_id
        );
        let response = timeout(Duration::from_secs(5), self.client.get(&url).send()).await??;
        let payload: OkxLatestInfoResponse = response.json().await?;
        if let Some(data) = payload.data {
            Ok(data)
        } else {
            let message = payload
                .error_message
                .or(payload.msg)
                .or(payload.detail_msg)
                .or(payload.error_code)
                .unwrap_or_else(|| "unknown error".to_string());
            Err(anyhow!(
                "OKX latest info missing data for {} ({})",
                contract_address,
                message
            ))
        }
    }

    async fn get_dexscreener_token_summary(
        &self,
        chain_slug: &str,
        contract_address: &str,
    ) -> Result<Vec<TokenPair>> {
        let url = format!(
            "https://api.dexscreener.com/tokens/v1/{}/{}",
            chain_slug, contract_address
        );
        let response = timeout(Duration::from_secs(3), self.client.get(&url).send()).await??;
        let data: Vec<TokenPair> = response.json().await?;
        Ok(data)
    }

    fn normalize_bnb_data(
        contract_address: &str,
        raw: &OkxTokenData,
        dexscreener_data: Option<DexScreenerData>,
        dexscreener_token_summary: Option<Vec<TokenPair>>,
        dexscreener_orders: Option<Vec<DexScreenerOrder>>,
    ) -> BnbTokenData {
        let resolved_address = raw
            .token_contract_address
            .as_ref()
            .map(|addr| addr.trim())
            .filter(|addr| !addr.is_empty())
            .map(|addr| addr.to_string())
            .unwrap_or_else(|| contract_address.to_string());

        let price = Self::parse_opt_f64(raw.price.as_ref());
        let change_24h = Self::parse_opt_f64(raw.change.as_ref());
        let change_4h = Self::parse_opt_f64(raw.change_4h.as_ref());
        let change_1h = Self::parse_opt_f64(raw.change_1h.as_ref());
        let change_5m = Self::parse_opt_f64(raw.change_5m.as_ref());
        let market_cap = Self::parse_opt_f64(raw.market_cap.as_ref());
        let liquidity = Self::parse_opt_f64(raw.liquidity.as_ref());
        let volume_24h = Self::parse_opt_f64(raw.volume.as_ref());
        let holders = Self::parse_opt_u64(raw.holders.as_ref());
        let top10 = Self::parse_opt_f64(raw.top10_hold_amount_percentage.as_ref());
        let dev_ratio = Self::parse_opt_f64(raw.dev_holding_ratio.as_ref());
        let risk_level = Self::parse_opt_u8(raw.risk_level.as_ref());

        let token_logo_url = Self::normalize_url(raw.token_logo_url.clone())
            .or_else(|| Self::normalize_url(raw.token_large_logo_url.clone()));

        let chain_name = raw
            .chain_name
            .as_ref()
            .map(|name| name.trim())
            .filter(|name| !name.is_empty())
            .map(|name| name.to_string());

        let holder_maps_url = Self::normalize_url(
            raw.token_third_part_info
                .as_ref()
                .and_then(|info| info.okx_web_site_url.clone()),
        );

        let bubble_maps_url = Self::normalize_url(
            raw.token_third_part_info
                .as_ref()
                .and_then(|info| info.third_party_web_site_url.clone()),
        );

        let dex_socials = dexscreener_data
            .as_ref()
            .and_then(|dex| dex.pairs.as_ref())
            .and_then(|pairs| pairs.first())
            .and_then(|pair| pair.info.as_ref())
            .and_then(|info| info.socials.as_ref())
            .map(|socials| {
                socials
                    .iter()
                    .filter_map(|social| {
                        let handle = social
                            .handle
                            .as_deref()
                            .map(str::trim)
                            .filter(|h| !h.is_empty())?;
                        let label = format_social_label(social.platform.as_deref(), handle);
                        Some(format!("{}: {}", label, handle))
                    })
                    .collect::<Vec<_>>()
            })
            .and_then(|entries| {
                if entries.is_empty() {
                    None
                } else {
                    Some(entries.join("\n"))
                }
            });

        BnbTokenData {
            contract_address: resolved_address,
            name: raw
                .token_name
                .as_ref()
                .map(|name| name.trim().to_string())
                .unwrap_or_default(),
            symbol: raw
                .token_symbol
                .as_ref()
                .map(|symbol| symbol.trim().to_string())
                .unwrap_or_default(),
            price,
            change_24h,
            change_4h,
            change_1h,
            change_5m,
            market_cap,
            liquidity,
            volume_24h,
            holders,
            top10_hold_percentage: top10,
            dev_holding_ratio: dev_ratio,
            risk_level,
            chain_name,
            token_logo_url,
            holder_maps_url,
            bubble_maps_url,
            dex_socials,
            dexscreener_data,
            dexscreener_token_summary,
            dexscreener_orders_data: dexscreener_orders,
        }
    }

    fn parse_opt_f64(value: Option<&String>) -> Option<f64> {
        value.and_then(|raw| raw.trim().parse::<f64>().ok())
    }

    fn parse_opt_u64(value: Option<&String>) -> Option<u64> {
        value.and_then(|raw| raw.trim().parse::<u64>().ok())
    }

    fn parse_opt_u8(value: Option<&String>) -> Option<u8> {
        value.and_then(|raw| raw.trim().parse::<u8>().ok())
    }

    fn normalize_url(value: Option<String>) -> Option<String> {
        value.and_then(|raw| {
            let trimmed = raw.trim();
            if trimmed.is_empty() {
                None
            } else {
                Some(trimmed.to_string())
            }
        })
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
            self.client.post(&url).json(&payload).send(),
        )
        .await??;
        let data: HoldersData = response.json().await?;
        Ok(data)
    }

    async fn get_dexscreener_data(&self, mint_address: &str) -> Result<DexScreenerData> {
        let url = format!(
            "https://api.dexscreener.com/latest/dex/tokens/{}",
            mint_address
        );
        let response = timeout(Duration::from_secs(3), self.client.get(&url).send()).await??;
        let data: DexScreenerData = response.json().await?;
        Ok(data)
    }

    async fn get_token_supply(&self, mint_address: &str) -> Result<SupplyInfo> {
        let url = format!("https://mainnet.helius-rpc.com/?api-key={}", self.api_key);
        let payload = json!({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenSupply",
            "params": [mint_address]
        });
        let response = timeout(
            Duration::from_secs(3),
            self.client.post(&url).json(&payload).send(),
        )
        .await??;
        let data: SupplyInfo = response.json().await?;
        Ok(data)
    }

    async fn get_pump_fun_data(&self, mint_address: &str) -> Result<PumpFunData> {
        let url = format!(
            "https://frontend-api-v3.pump.fun/coins/{}?sync=true",
            mint_address
        );
        let jwt = env::var("PUMP_FUN_JWT").unwrap_or_default();
        let response = timeout(
            Duration::from_secs(5),
            self.client.get(&url).bearer_auth(jwt).send(),
        )
        .await??;
        if response.status() == 404 {
            return Err(anyhow!("Token not found on pump.fun"));
        }
        let data: PumpFunData = response.json().await?;
        Ok(data)
    }

    async fn fetch_jupiter_token_data(&self, mint_address: &str) -> Result<JupiterTokenData> {
        let url = format!(
            "https://lite-api.jup.ag/tokens/v2/search?query={}",
            mint_address
        );
        let response = timeout(Duration::from_secs(5), self.client.get(&url).send()).await??;

        if response.status().is_client_error() || response.status().is_server_error() {
            if response.status() == reqwest::StatusCode::NOT_FOUND {
                return Err(anyhow!("Token not found on Jupiter (404)"));
            }
            return Err(anyhow!(
                "Jupiter API returned an error: {}",
                response.status()
            ));
        }
        let data: Vec<JupiterTokenData> = response.json().await?;
        data.into_iter()
            .next()
            .ok_or_else(|| anyhow!("No Jupiter data found"))
    }

    async fn get_dexscreener_orders_data(
        &self,
        chain_id: &str,
        token_address: &str,
    ) -> Result<Vec<DexScreenerOrder>> {
        let url = format!(
            "https://api.dexscreener.com/orders/v1/{}/{}",
            chain_id, token_address
        );
        let response = timeout(Duration::from_secs(5), self.client.get(&url).send()).await??;

        if response.status().is_client_error() || response.status().is_server_error() {
            if response.status() == reqwest::StatusCode::NOT_FOUND {
                return Err(anyhow!("DexScreener Orders: Token not found (404)"));
            }
            return Err(anyhow!(
                "DexScreener Orders API returned an error: {}",
                response.status()
            ));
        }

        let data: Vec<DexScreenerOrder> = response.json().await?;
        Ok(data)
    }

    async fn get_vamped_fun_data(&self, mint_address: &str) -> Result<VampedFunData> {
        let url = "https://www.vamped.fun/api/check-token";
        let payload = json!({
            "mintAddress": mint_address
        });
        let response = timeout(
            Duration::from_secs(5),
            self.client
                .post(url)
                .header("Content-Type", "application/json")
                .header("Origin", "https://www.vamped.fun")
                .header("Referer", "https://www.vamped.fun/")
                .json(&payload)
                .send(),
        )
        .await??;

        if response.status().is_client_error() || response.status().is_server_error() {
            return Err(anyhow!(
                "Vamped.fun API returned an error: {}",
                response.status()
            ));
        }

        let data: VampedFunData = response.json().await?;
        Ok(data)
    }

    fn resolve_evm_chain_context(
        dex_data: Option<&DexScreenerData>,
    ) -> (&'static str, &'static str) {
        let chain_hint = dex_data
            .and_then(|dex| dex.pairs.as_ref())
            .and_then(|pairs| pairs.iter().find_map(|pair| pair.chain_id.as_deref()));

        if let Some(chain_id) = chain_hint {
            let normalized = chain_id.trim().to_ascii_lowercase();
            if normalized.contains("base") || normalized == "8453" {
                return ("base", "8453");
            }
            if normalized.contains("bsc") || normalized.contains("bnb") || normalized == "56" {
                return ("bsc", "56");
            }
            if let Ok(value) = normalized.parse::<u64>() {
                match value {
                    8453 => return ("base", "8453"),
                    56 => return ("bsc", "56"),
                    _ => {}
                }
            }
        }

        ("bsc", "56")
    }

    async fn get_sol_balance(&self, address: &str) -> Result<f64> {
        let url = format!("https://mainnet.helius-rpc.com/?api-key={}", self.api_key);
        let payload = json!({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getBalance",
            "params": [address]
        });
        let response = timeout(
            Duration::from_secs(3),
            self.client.post(&url).json(&payload).send(),
        )
        .await??;

        #[derive(serde::Deserialize)]
        struct BalanceResponse {
            result: Option<BalanceResult>,
        }

        #[derive(serde::Deserialize)]
        struct BalanceResult {
            value: u64,
        }

        let data: BalanceResponse = response.json().await?;
        if let Some(result) = data.result {
            Ok(result.value as f64 / 1_000_000_000.0) // Convert lamports to SOL
        } else {
            Err(anyhow!("No balance data found"))
        }
    }

    async fn get_dev_token_holding(
        &self,
        owner: &str,
        mint: &str,
    ) -> Result<Option<DevTokenHolding>> {
        let url = format!("https://mainnet.helius-rpc.com/?api-key={}", self.api_key);
        let payload = json!({
            "jsonrpc": "2.0",
            "id": "1",
            "method": "getTokenAccountsByOwner",
            "params": [
                owner,
                {"mint": mint},
                {"encoding": "jsonParsed"}
            ]
        });

        let response = timeout(
            Duration::from_secs(3),
            self.client.post(&url).json(&payload).send(),
        )
        .await??;

        let data: TokenAccountsResponse = response.json().await?;

        if let Some(result) = data.result {
            if let Some(accounts) = result.value {
                if let Some(account) = accounts.into_iter().next() {
                    let token_details = &account.account.data.parsed.info;
                    let token_amount = &token_details.token_amount;

                    return Ok(Some(DevTokenHolding {
                        owner_address: owner.to_string(),
                        mint_address: mint.to_string(),
                        token_account: account.pubkey,
                        amount: token_amount.amount.clone(),
                        decimals: token_amount.decimals,
                        ui_amount: token_amount.ui_amount,
                        ui_amount_string: token_amount.ui_amount_string.clone(),
                        state: token_details.state.clone(),
                    }));
                }
            }
        }

        Ok(None) // No token account found
    }
}
