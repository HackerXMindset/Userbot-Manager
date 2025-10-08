use crate::api::ApiClient;
use crate::social::{detect_social_platform, format_social_label};
use crate::types::*;
use anyhow::Result;
use once_cell::sync::Lazy;
use regex::Regex;
use std::cmp::Ordering;
use std::sync::Arc;
use std::time::Instant;
use teloxide::update_listeners::{AsUpdateStream, UpdateListener};
use teloxide::{prelude::*, types::UpdateKind, update_listeners, utils::html};
use tokio::sync::watch;
use tokio_stream::StreamExt;
use tracing::error;

static SOLANA_ADDRESS_REGEX: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b").expect("valid solana regex"));

static BNB_ADDRESS_REGEX: Lazy<Regex> =
    Lazy::new(|| Regex::new(r"\b0x[a-fA-F0-9]{40}\b").expect("valid bnb regex"));

fn format_compact_amount(value: f64) -> String {
    let abs_val = value.abs();
    if abs_val >= 1_000_000_000.0 {
        format!("{:.1}B", value / 1_000_000_000.0)
    } else if abs_val >= 1_000_000.0 {
        format!("{:.1}M", value / 1_000_000.0)
    } else if abs_val >= 1_000.0 {
        format!("{:.1}K", value / 1_000.0)
    } else if abs_val >= 1.0 {
        format!("{:.0}", value)
    } else {
        format!("{:.2}", value)
    }
}

fn format_float_trimmed(value: f64, decimals: usize) -> String {
    let mut formatted = format!("{:.*}", decimals, value);
    if formatted.contains('.') {
        while formatted.ends_with('0') {
            formatted.pop();
        }
        if formatted.ends_with('.') {
            formatted.pop();
        }
    }
    if formatted.is_empty() {
        "0".to_string()
    } else {
        formatted
    }
}

fn maybe_format_float(value: Option<f64>, decimals: usize) -> Option<String> {
    value.map(|v| format_float_trimmed(v, decimals))
}

fn maybe_format_percentage(value: Option<f64>) -> Option<String> {
    value.map(|v| format_float_trimmed(v, 2))
}

fn select_primary_pair<'a>(dex_data: &'a DexScreenerData) -> Option<&'a TokenPair> {
    let pairs = dex_data.pairs.as_ref()?;
    let mut best_pair = None;
    let mut best_liquidity = 0.0;

    for pair in pairs {
        let liq = pair.liquidity.as_ref().and_then(|l| l.usd).unwrap_or(0.0);

        if best_pair.is_none() || liq.partial_cmp(&best_liquidity) == Some(Ordering::Greater) {
            best_liquidity = liq;
            best_pair = Some(pair);
        }
    }

    best_pair.or_else(|| pairs.first())
}

fn format_pair_timestamp(timestamp_ms: i64) -> Option<String> {
    chrono::DateTime::from_timestamp_millis(timestamp_ms)
        .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
}

fn format_unix_timestamp_ms(timestamp_ms: i64) -> Option<String> {
    chrono::DateTime::from_timestamp_millis(timestamp_ms)
        .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
}

fn format_relative_timestamp(timestamp_ms: i64) -> Option<String> {
    chrono::DateTime::from_timestamp_millis(timestamp_ms).map(|dt| {
        let now = chrono::Utc::now();
        let duration = now - dt;
        let hours = duration.num_hours();
        if hours >= 48 {
            format!("{} days ago", duration.num_days())
        } else if hours >= 1 {
            let minutes = duration.num_minutes() % 60;
            format!("{}h {}m ago", hours, minutes)
        } else {
            let minutes = duration.num_minutes();
            if minutes > 0 {
                format!("{}m ago", minutes)
            } else {
                "just now".to_string()
            }
        }
    })
}

pub async fn start_bot(
    bot_token: String,
    api_client: Arc<ApiClient>,
    mut shutdown_rx: watch::Receiver<bool>,
) -> Result<()> {
    let bot = Bot::new(bot_token);

    let mut listener = update_listeners::polling_default(bot.clone()).await;
    let stream = listener.as_stream();

    tokio::pin!(stream);

    loop {
        tokio::select! {
            changed = shutdown_rx.changed() => {
                if changed.is_ok() && *shutdown_rx.borrow() {
                    listener.stop_token().stop();
                    break;
                }
            }
            update = stream.next() => {
                match update {
                    Some(Ok(update)) => {
                        if let UpdateKind::Message(message) = update.kind {
                            let bot_clone = bot.clone();
                            let client = Arc::clone(&api_client);
                            if let Err(err) = handle_message(bot_clone, message, client).await {
                                error!("Handler error: {:?}", err);
                            }
                        }
                    }
                    Some(Err(err)) => {
                        if matches!(err, teloxide::RequestError::Api(teloxide::ApiError::TerminatedByOtherGetUpdates)) {
                            error!("Polling interrupted by another getUpdates call. Retrying...");
                        } else {
                            error!("Failed to poll update: {:?}", err);
                        }
                    }
                    None => break,
                }
            }
        }
    }

    Ok(())
}

async fn handle_message(bot: Bot, msg: Message, api_client: Arc<ApiClient>) -> ResponseResult<()> {
    if let Some(text) = msg.text() {
        if let Some(contract) = detect_contract_address(text) {
            // Start timing
            let start_time = Instant::now();

            // Analyze token
            match api_client.analyze_token(&contract).await {
                Ok(analysis) => {
                    let elapsed = start_time.elapsed();
                    let timing_text = format!("⚡ {}ms!", elapsed.as_millis());
                    let (formatted_text, _image_url) = format_analysis(&analysis);
                    let final_text = format!("{}\n\n{}", timing_text, formatted_text);

                    let lines: Vec<&str> = final_text.split('\n').collect();
                    let mut message_chunk = String::new();

                    for line in lines {
                        if message_chunk.len() + line.len() + 1 > 4000 {
                            bot.send_message(msg.chat.id, &message_chunk)
                                .parse_mode(teloxide::types::ParseMode::Html)
                                .disable_web_page_preview(true)
                                .await?;
                            message_chunk.clear();
                        }
                        message_chunk.push_str(line);
                        message_chunk.push('\n');
                    }

                    if !message_chunk.is_empty() {
                        bot.send_message(msg.chat.id, &message_chunk)
                            .parse_mode(teloxide::types::ParseMode::Html)
                            .disable_web_page_preview(true)
                            .await?;
                    }
                }
                Err(e) => {
                    let elapsed = start_time.elapsed();
                    let timing_text = format!("⚡ {}ms!", elapsed.as_millis());
                    let error_text = format!("{}\n\n❌ Error analyzing token: {}", timing_text, e);

                    bot.send_message(msg.chat.id, error_text).await?;
                }
            }
        }
    }

    Ok(())
}

fn detect_contract_address(text: &str) -> Option<DetectedContract> {
    let sol_match = SOLANA_ADDRESS_REGEX.find(text);
    let bnb_match = BNB_ADDRESS_REGEX.find(text);

    match (sol_match, bnb_match) {
        (Some(sol), Some(bnb)) => {
            if sol.start() <= bnb.start() {
                Some(DetectedContract::new(
                    sol.as_str().to_string(),
                    Chain::Solana,
                ))
            } else {
                Some(DetectedContract::new(bnb.as_str().to_string(), Chain::Bnb))
            }
        }
        (Some(sol), None) => Some(DetectedContract::new(
            sol.as_str().to_string(),
            Chain::Solana,
        )),
        (None, Some(bnb)) => Some(DetectedContract::new(bnb.as_str().to_string(), Chain::Bnb)),
        (None, None) => None,
    }
}

fn create_progress_bar(percentage: f64) -> String {
    let total_blocks = 20;
    let filled_blocks = ((percentage / 100.0) * total_blocks as f64).round() as usize;
    let empty_blocks = total_blocks - filled_blocks;

    let filled = "█".repeat(filled_blocks);
    let empty = "░".repeat(empty_blocks);

    format!("[{}{}] {:.1}%", filled, empty, percentage)
}

fn format_analysis(analysis: &TokenAnalysis) -> (String, Option<String>) {
    match analysis {
        TokenAnalysis::Solana(data) => format_solana_token_data(data),
        TokenAnalysis::Bnb(data) => format_bnb_token_data(data),
    }
}

fn format_solana_token_data(data: &TokenData) -> (String, Option<String>) {
    let ca = &data.mint_address;
    let mut parts = Vec::new();

    // Default values
    let mut name = "Unknown".to_string();
    let mut symbol = "N/A".to_string();
    let mut description = "".to_string();
    let mut image_url: Option<String> = None;
    let mut social_links = std::collections::HashMap::new();

    // Extract from Helius Metadata if available
    if let Some(metadata) = &data.metadata {
        if let Some(on_chain) = &metadata.on_chain_metadata {
            if let Some(meta) = &on_chain.metadata {
                name = meta.data.name.clone().unwrap_or(name).trim().to_string();
                symbol = meta
                    .data
                    .symbol
                    .clone()
                    .unwrap_or(symbol)
                    .trim()
                    .to_string();
            }
        }
        if let Some(off_chain) = &metadata.off_chain_metadata {
            if let Some(meta) = &off_chain.metadata {
                name = meta.name.clone().unwrap_or(name);
                symbol = meta.symbol.clone().unwrap_or(symbol);
                description = meta.description.clone().unwrap_or_default();
                image_url = meta.image.clone();
            }
        }
    }

    // Override with pump.fun data if available
    if let Some(pf) = &data.pump_fun_data {
        name = pf.name.clone().unwrap_or(name);
        symbol = pf.symbol.clone().unwrap_or(symbol);
        description = pf.description.clone().unwrap_or(description);
        image_url = pf.image_uri.clone();
        if pf.twitter.is_some() {
            social_links.insert("Twitter".to_string(), pf.twitter.clone());
        }
        if pf.telegram.is_some() {
            social_links.insert("Telegram".to_string(), pf.telegram.clone());
        }
        if pf.website.is_some() {
            social_links.insert("Website".to_string(), pf.website.clone());
        }
    }

    // Extract social links from dexscreener
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(info) = &pair.info {
                if let Some(socials) = &info.socials {
                    for social in socials {
                        if let (Some(platform), Some(handle)) = (&social.platform, &social.handle) {
                            if platform.to_lowercase() == "telegram" {
                                social_links.insert("Telegram".to_string(), Some(handle.clone()));
                            }
                        }
                    }
                }
            }
        }
    }

    // --- Formatting ---
    let name_esc = html::escape(&name);
    let symbol_esc = html::escape(&symbol);
    let ca_esc = html::escape(ca);

    // 1. Header
    parts.push(format!("🚀 <b>{} ({})</b>", name_esc, symbol_esc));
    parts.push(format!("<code>{}</code>", ca_esc));
    parts.push(format!(
        "<a href=\"https://solscan.io/token/{}\">Solscan</a> | <a href=\"https://dexscreener.com/solana/{}\">DexScreener</a> | <a href=\"https://birdeye.so/token/{}?chain=solana\">Birdeye</a>",
        ca, ca, ca
    ));
    parts.push(String::new());

    // 2. 💰 Price & Market Data
    parts.push("💰 <b>Price & Market Data</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(price_native) = &pair.price_native {
                parts.push(format!("💰 <b>Price (dex):</b> {}", price_native));
            }
            parts.push(format!(
                "🧢 <b>MC (dex):</b> ${:.0}",
                pair.market_cap.unwrap_or(0.0)
            ));
            parts.push(format!(
                "💎 <b>FDV (dex):</b> ${:.0}",
                pair.fdv.unwrap_or(0.0)
            ));
        }
    }
    if let Some(pf) = &data.pump_fun_data {
        parts.push(format!(
            "🧢 <b>MC (pf):</b> ${:.0}",
            pf.usd_market_cap.unwrap_or(0.0)
        ));
        parts.push(format!(
            "<b>Market Cap SOL (pf):</b> {:.2}",
            pf.market_cap.unwrap_or(0.0)
        ));
        parts.push(format!(
            "🔥 <b>ATH (pf):</b> ${:.0}",
            pf.ath_market_cap.unwrap_or(0.0)
        ));
    }
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(price) = jup_data.usd_price {
            parts.push(format!("💰 <b>Price (jup):</b> ${}", price));
        }
        if let Some(mcap) = jup_data.mcap {
            parts.push(format!("🧢 <b>MC (jup):</b> ${:.0}", mcap));
        }
        if let Some(fdv) = jup_data.fdv {
            parts.push(format!("💎 <b>FDV (jup):</b> ${:.0}", fdv));
        }
    }
    parts.push(String::new());

    // 3. 📊 Trading Volume
    parts.push("📊 <b>Trading Volume</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(volume) = &pair.volume {
                parts.push(format!(
                    "📊 <b>24h (dex):</b> ${:.0}",
                    volume.h24.unwrap_or(0.0)
                ));
                parts.push(format!(
                    "<b>6h/1h/5m (dex):</b> ${:.0} / ${:.0} / ${:.0}",
                    volume.h6.unwrap_or(0.0),
                    volume.h1.unwrap_or(0.0),
                    volume.m5.unwrap_or(0.0)
                ));
            }
        }
    }
    parts.push(String::new());

    // 4. 📈 Price Changes
    parts.push("📈 <b>Price Changes</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(price_change) = &pair.price_change {
                parts.push(format!(
                    "📈 <b>24h/6h/1h/5m (dex):</b> {:.2}% / {:.2}% / {:.2}% / {:.2}%",
                    price_change.h24.unwrap_or(0.0),
                    price_change.h6.unwrap_or(0.0),
                    price_change.h1.unwrap_or(0.0),
                    price_change.m5.unwrap_or(0.0)
                ));
            }
        }
    }
    parts.push(String::new());

    // 5. 🔄 Transaction Activity
    parts.push("🔄 <b>Transaction Activity</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(txns) = &pair.txns {
                if let (Some(h24), Some(h6), Some(h1), Some(m5)) =
                    (&txns.h24, &txns.h6, &txns.h1, &txns.m5)
                {
                    parts.push(format!(
                        "🔄 <b>24h (dex):</b> {} buys / {} sells",
                        h24.buys.unwrap_or(0),
                        h24.sells.unwrap_or(0)
                    ));
                    parts.push(format!(
                        "<b>6h (dex):</b> {} buys / {} sells",
                        h6.buys.unwrap_or(0),
                        h6.sells.unwrap_or(0)
                    ));
                    parts.push(format!(
                        "<b>1h (dex):</b> {} buys / {} sells",
                        h1.buys.unwrap_or(0),
                        h1.sells.unwrap_or(0)
                    ));
                    parts.push(format!(
                        "<b>5m (dex):</b> {} buys / {} sells",
                        m5.buys.unwrap_or(0),
                        m5.sells.unwrap_or(0)
                    ));
                }
            }
        }
    }
    parts.push(String::new());

    // 6. 💧 Liquidity
    parts.push("💧 <b>Liquidity</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            parts.push(format!(
                "💧 <b>USD (dex):</b> ${:.0}",
                pair.liquidity
                    .as_ref()
                    .map_or(0.0, |l| l.usd.unwrap_or(0.0))
            ));
            if let Some(liquidity) = &pair.liquidity {
                parts.push(format!(
                    "<b>Base/Quote (dex):</b> {:.2} / {:.2}",
                    liquidity.base.unwrap_or(0.0),
                    liquidity.quote.unwrap_or(0.0)
                ));
            }
        }
    }
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(liquidity) = jup_data.liquidity {
            parts.push(format!("💧 <b>Liquidity (jup):</b> ${:.0}", liquidity));
        }
    }
    parts.push(String::new());

    // 7. 📦 Supply & Token Info
    parts.push("📦 <b>Supply & Token Info</b>".to_string());
    if let Some(pf) = &data.pump_fun_data {
        if let Some(total_supply) = pf.total_supply {
            parts.push(format!("📦 <b>Total Supply (pf):</b> {}", total_supply));
        }
    }
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(circ_supply) = jup_data.circ_supply {
            parts.push(format!(
                "🔄 <b>Circulating Supply (jup):</b> {:.0}",
                circ_supply
            ));
        }
        if let Some(total_supply) = jup_data.total_supply {
            parts.push(format!("📦 <b>Total Supply (jup):</b> {:.0}", total_supply));
        }
        parts.push(format!("📊 <b>Decimals (jup):</b> {}", jup_data.decimals));
    }
    parts.push(String::new());

    // 8. 🔒 Security & Governance
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(audit) = &jup_data.audit {
            parts.push("🔒 <b>Security & Governance (jup)</b>".to_string());
            parts.push(format!(
                "🔐 <b>Mint Authority:</b> {}",
                if audit.mint_authority_disabled.unwrap_or(false) {
                    "Disabled ✅"
                } else {
                    "Enabled ⚠️"
                }
            ));
            parts.push(format!(
                "🧊 <b>Freeze Authority:</b> {}",
                if audit.freeze_authority_disabled.unwrap_or(false) {
                    "Disabled ✅"
                } else {
                    "Enabled ⚠️"
                }
            ));
            if let Some(top_holders) = audit.top_holders_percentage {
                parts.push(format!("👑 <b>Top Holders:</b> {:.2}%", top_holders));
            }
            parts.push(format!(
                "🎯 <b>Snipers:</b> {:.2}%",
                audit.snipers_holding_percentage.unwrap_or(0.0)
            ));
            if let Some(dev_migrations) = audit.dev_migrations {
                parts.push(format!("🔄 <b>Dev Migrations:</b> {}", dev_migrations));
            }
            if let Some(dev_balance) = audit.dev_balance_percentage {
                parts.push(format!("👨‍💻 <b>Dev Token Balance:</b> {:.2}%", dev_balance));
            }
            parts.push(String::new());
        }
    }

    // 9. 👥 Holders Analysis
    parts.push("👥 <b>Holders Analysis</b>".to_string());
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(holders) = jup_data.holder_count {
            parts.push(format!("👥 <b>Total Holders (jup):</b> {}", holders));
        }
    }
    let supply_ui_amount = data
        .supply_info
        .as_ref()
        .and_then(|info| info.result.as_ref())
        .and_then(|res| res.value.as_ref())
        .and_then(|val| val.ui_amount)
        .filter(|amt| *amt > 0.0);

    if let Some(holders_data) = &data.holders {
        if let Some(result) = &holders_data.result {
            if let Some(context) = &result.context {
                if let Some(slot) = context.slot {
                    parts.push(format!("📊 <b>Data Slot (helius):</b> {}", slot));
                }
            }
            if let Some(holders) = &result.value {
                if let Some(total_supply) = supply_ui_amount {
                    let mut breakdown_links = Vec::new();
                    for holder in holders.iter().take(10) {
                        if let (Some(address), Some(ui_amount)) =
                            (&holder.address, holder.ui_amount)
                        {
                            if ui_amount > 0.0 {
                                let percent = (ui_amount / total_supply) * 100.0;
                                breakdown_links.push(format!(
                                    "<a href=\"https://t.me/GMGN_smartmoney_bot?start={}\">{:.1}%</a>",
                                    address, percent
                                ));
                            }
                        }
                    }
                    if !breakdown_links.is_empty() {
                        parts.push(format!("Breakdown: {}", breakdown_links.join(" | ")));
                    }
                }

                let mut table_lines: Vec<String> = vec![
                    "Top 10 Holders".to_string(),
                    "User | Holdings | % of Supply".to_string(),
                ];
                let mut displayed_count = 0;

                for (index, holder) in holders.iter().take(10).enumerate() {
                    if let (Some(address), Some(ui_amount)) = (&holder.address, holder.ui_amount) {
                        let tail = if address.len() >= 4 {
                            &address[address.len() - 4..]
                        } else {
                            address.as_str()
                        };
                        let base_label = if index + 1 < 10 {
                            format!("{}..{}", index + 1, tail)
                        } else {
                            format!("{}.{tail}", index + 1)
                        };
                        let wallet_link = format!(
                            "<a href=\"https://t.me/GMGN_smartmoney_bot?start={}\">{}</a>",
                            address, base_label
                        );
                        let holdings_text = format_compact_amount(ui_amount);
                        let percent_text = if let Some(total_supply) = supply_ui_amount {
                            if total_supply > 0.0 {
                                format!("{:.2}%", (ui_amount / total_supply) * 100.0)
                            } else {
                                "N/A".to_string()
                            }
                        } else {
                            "N/A".to_string()
                        };

                        table_lines.push(format!(
                            "{} | {} | {}",
                            wallet_link, holdings_text, percent_text
                        ));
                        displayed_count += 1;
                    }
                }

                if displayed_count > 0 {
                    table_lines[0] = format!("Top {} Holders", displayed_count);
                    parts.extend(table_lines);
                } else {
                    parts.push("No holder data available".to_string());
                }
            } else {
                parts.push("No holder data available".to_string());
            }
        }
    }
    parts.push(String::new());

    // 10. 🧑‍💻 Developer Info
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(dev_address) = &jup_data.dev {
            parts.push("🧑‍💻 <b>Developer Info (jup)</b>".to_string());
            let short_addr = if dev_address.len() > 8 {
                format!(
                    "{}...{}",
                    &dev_address[..4],
                    &dev_address[dev_address.len() - 4..]
                )
            } else {
                dev_address.clone()
            };
            let mut dev_parts = vec![format!(
                "👨‍💻 <b>Dev Address:</b> <a href=\"https://solscan.io/account/{}\">{}</a>",
                dev_address, short_addr
            )];
            if let Some(sol_balance) = data.dev_sol_balance {
                dev_parts.push(format!("💰 <b>SOL Balance:</b> {:.2}", sol_balance));
            }
            // Simple dev holdings indicator
            if let Some(dev_holding) = &data.dev_token_holding {
                if let Some(ui_amount) = dev_holding.ui_amount {
                    if ui_amount > 0.0 {
                        // Dev is holding tokens - show red dot with percentage
                        if let Some(supply_info) = &data.supply_info {
                            if let Some(result) = &supply_info.result {
                                if let Some(value) = &result.value {
                                    if let Some(supply_ui) = value.ui_amount {
                                        if supply_ui > 0.0 {
                                            let percent = (ui_amount / supply_ui) * 100.0;
                                            dev_parts.push(format!("🔴 ({:.1}%)", percent));
                                        } else {
                                            dev_parts.push("🔴".to_string());
                                        }
                                    } else {
                                        dev_parts.push("🔴".to_string());
                                    }
                                } else {
                                    dev_parts.push("🔴".to_string());
                                }
                            } else {
                                dev_parts.push("🔴".to_string());
                            }
                        } else {
                            dev_parts.push("🔴".to_string());
                        }
                    } else {
                        // Dev sold all tokens - show green dot
                        dev_parts.push("🟢".to_string());
                    }
                } else {
                    dev_parts.push("🟢".to_string());
                }
            } else {
                // No data available - assume sold
                dev_parts.push("🟢".to_string());
            }

            parts.push(dev_parts.join(" | "));
            parts.push(String::new());
        }
    }

    // 11. 🎢 Bonding Curve
    if let Some(pf) = &data.pump_fun_data {
        parts.push("🎢 <b>Bonding Curve (pf)</b>".to_string());
        let real_sol_lamports = pf.real_sol_reserves.unwrap_or(0.0);
        let real_sol = real_sol_lamports / 1e9;
        let virtual_sol_lamports = pf.virtual_sol_reserves.unwrap_or(0.0);
        let virtual_sol = virtual_sol_lamports / 1e9;
        let virtual_tokens = pf.virtual_token_reserves.unwrap_or(0.0);
        parts.push(format!(
            "💰 <b>Real SOL:</b> {:.2} | <b>Virtual SOL:</b> {:.2}",
            real_sol, virtual_sol
        ));
        if real_sol_lamports > 0.0 || virtual_sol_lamports > 0.0 {
            parts.push(format!(
                "💰 <b>Lamports (real/virtual):</b> {:.0} / {:.0}",
                real_sol_lamports, virtual_sol_lamports
            ));
        }
        parts.push(format!("🪙 <b>Virtual Tokens:</b> {:.0}", virtual_tokens));
        let real_tokens = pf.real_token_reserves.unwrap_or(0.0);
        parts.push(format!("🎯 <b>Real Tokens:</b> {:.0}", real_tokens));
        if let Some(bonding_curve_addr) = &pf.bonding_curve {
            parts.push(format!(
                "📍 <b>Address:</b> <code>{}</code>",
                bonding_curve_addr
            ));
        }
        if let Some(assoc_bonding_curve) = &pf.associated_bonding_curve {
            parts.push(format!(
                "🔗 <b>Assoc. Address:</b> <code>{}</code>",
                assoc_bonding_curve
            ));
        }
        if let Some(raydium_pool) = &pf.raydium_pool {
            parts.push(format!(
                "🏊 <b>Raydium Pool:</b> <code>{}</code> (<a href=\"https://solscan.io/account/{}\">View</a>)",
                raydium_pool, raydium_pool
            ));
        }
        if let Some(pump_swap_pool) = &pf.pump_swap_pool {
            parts.push(format!(
                "🔁 <b>Pump Swap Pool:</b> <code>{}</code> (<a href=\"https://solscan.io/account/{}\">View</a>)",
                pump_swap_pool, pump_swap_pool
            ));
        }
    }
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(bonding_curve) = jup_data.bonding_curve {
            if bonding_curve < 100.0 {
                parts.push(format!(
                    "📊 <b>Progress (jup):</b> {}",
                    create_progress_bar(bonding_curve)
                ));
            }
        }
    }
    parts.push(String::new());

    // 12. 🗓️ Timestamps
    parts.push("🗓️ <b>Timestamps</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(created_at) = &pair.pair_created_at {
                parts.push(format!(
                    "🕒 <b>Pair Created (dex):</b> {}",
                    chrono::DateTime::from_timestamp_millis(*created_at)
                        .unwrap()
                        .format("%Y-%m-%d %H:%M")
                ));
            }
        }
    }
    if let Some(pf) = &data.pump_fun_data {
        if let Some(created_ts) = pf.created_timestamp {
            parts.push(format!(
                "🕒 <b>Token Created (pf):</b> {}",
                chrono::DateTime::from_timestamp_millis(created_ts)
                    .unwrap()
                    .format("%Y-%m-%d %H:%M")
            ));
        }
        if let Some(last_trade_ts) = pf.last_trade_timestamp {
            parts.push(format!(
                "📈 <b>Last Trade (pf):</b> {}",
                chrono::DateTime::from_timestamp_millis(last_trade_ts)
                    .unwrap()
                    .format("%Y-%m-%d %H:%M")
            ));
        }
        if let Some(ath_ts) = pf.ath_market_cap_timestamp {
            parts.push(format!(
                "🔥 <b>ATH Date (pf):</b> {}",
                chrono::DateTime::from_timestamp_millis(ath_ts)
                    .unwrap()
                    .format("%Y-%m-%d %H:%M")
            ));
        }
        if let Some(koth_ts) = pf.king_of_the_hill_timestamp {
            if koth_ts > 0 {
                parts.push(format!(
                    "👑 <b>King of Hill (pf):</b> {}",
                    chrono::DateTime::from_timestamp_millis(koth_ts)
                        .unwrap()
                        .format("%Y-%m-%d %H:%M")
                ));
            }
        }
    }
    parts.push(String::new());

    // 13. 🚦 Status & Flags
    if let Some(pf) = &data.pump_fun_data {
        parts.push("🚦 <b>Status & Flags (pf)</b>".to_string());
        let mut status_parts = Vec::new();
        status_parts.push(
            if pf.is_currently_live.unwrap_or(false) {
                "🟢 Live"
            } else {
                "🔴 Not Live"
            }
            .to_string(),
        );
        status_parts.push(
            if pf.complete.unwrap_or(false) {
                "✅ Complete"
            } else {
                "❌ Incomplete"
            }
            .to_string(),
        );
        if pf.is_banned.unwrap_or(false) {
            status_parts.push("🚫 Banned".to_string());
        }
        if pf.nsfw.unwrap_or(false) {
            status_parts.push("🔞 NSFW".to_string());
        }
        if pf.hidden.unwrap_or(false) {
            status_parts.push("👻 Hidden".to_string());
        }
        if pf.show_name.unwrap_or(false) {
            status_parts.push("📛 Show Name".to_string());
        }
        if pf.inverted.unwrap_or(false) {
            status_parts.push("🔄 Inverted".to_string());
        }
        if pf.initialized.unwrap_or(false) {
            status_parts.push("⚡ Initialized".to_string());
        }
        parts.push(status_parts.join(" | "));
        if let Some(downrank_score) = pf.downrank_score {
            parts.push(format!(
                "⬇️ <b>Downrank Score (pf):</b> {:.2}",
                downrank_score
            ));
        }
        parts.push(String::new());
    }

    // 14. ⚙️ Technical Details
    parts.push("⚙️ <b>Technical Details</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(dex_id) = &pair.dex_id {
                parts.push(format!("🏢 <b>DEX (dex):</b> {}", dex_id));
            }
            if let Some(pair_address) = &pair.pair_address {
                parts.push(format!(
                    "🔗 <b>Pair Address (dex):</b> <code>{}</code>",
                    pair_address
                ));
            }
            if let Some(url) = &pair.url {
                parts.push(format!("🔗 <a href=\"{}\">View on DexScreener</a>", url));
            }
            if let Some(boosts) = &pair.boosts {
                if let Some(active) = boosts.active {
                    parts.push(format!("🚀 <b>Active Boosts (dex):</b> {}", active));
                }
            }
            if let (Some(base), Some(quote)) = (&pair.base_token, &pair.quote_token) {
                parts.push(format!(
                    "📊 <b>Base Token (dex):</b> {} ({}) - <code>{}</code>",
                    base.name.as_deref().unwrap_or("N/A"),
                    base.symbol.as_deref().unwrap_or("N/A"),
                    base.address.as_deref().unwrap_or("N/A")
                ));
                parts.push(format!(
                    "📊 <b>Quote Token (dex):</b> {} ({}) - <code>{}</code>",
                    quote.name.as_deref().unwrap_or("N/A"),
                    quote.symbol.as_deref().unwrap_or("N/A"),
                    quote.address.as_deref().unwrap_or("N/A")
                ));
            }
        }
    }
    if let Some(pf) = &data.pump_fun_data {
        if let Some(prog) = &pf.program {
            parts.push(format!("⚙️ <b>Program (pf):</b> {}", prog));
        }
        if let Some(plat) = &pf.platform {
            parts.push(format!("🖥️ <b>Platform (pf):</b> {}", plat));
        }
        if let Some(market) = &pf.market_id {
            parts.push(format!("📈 <b>Market ID (pf):</b> {}", market));
        }
        if let Some(ts) = pf.last_reply {
            parts.push(format!(
                "💬 <b>Last Reply (pf):</b> {}",
                chrono::DateTime::from_timestamp_millis(ts)
                    .unwrap()
                    .format("%Y-%m-%d %H:%M")
            ));
        }
        if let Some(ts) = pf.updated_at {
            parts.push(format!(
                "🔄 <b>Updated At (pf):</b> {}",
                chrono::DateTime::from_timestamp_millis(ts)
                    .unwrap()
                    .format("%Y-%m-%d %H:%M")
            ));
        }
        if pf.hide_banner.unwrap_or(false) {
            parts.push("🚫 <b>Banner Hidden (pf):</b> ✅".to_string());
        }
    }
    if let Some(jup_data) = &data.jupiter_data {
        parts.push(format!("🆔 <b>Token ID (jup):</b> {}", jup_data.id));
        parts.push(format!(
            "💻 <b>Token Program (jup):</b> {}",
            jup_data.token_program
        ));
        if let Some(icon) = &jup_data.icon {
            parts.push(format!(
                "🖼️ <b>Icon (jup):</b> <a href=\"{}\">{}</a>",
                icon, icon
            ));
        }
        if let Some(price_block_id) = jup_data.price_block_id {
            parts.push(format!(
                "📊 <b>Price Block ID (jup):</b> {}",
                price_block_id
            ));
        }
        if let Some(first_pool) = &jup_data.first_pool {
            parts.push(format!(
                "🏊 <b>First Pool (jup):</b> {} (Created: {})",
                first_pool.id, first_pool.created_at
            ));
        }
        if let Some(launchpad) = &jup_data.launchpad {
            parts.push(format!("🚀 <b>Launchpad (jup):</b> {}", launchpad));
        }
        if let Some(graduated_pool) = &jup_data.graduated_pool {
            parts.push(format!(
                "🎓 <b>Graduated Pool (jup):</b> {}",
                graduated_pool
            ));
        }
        if let Some(graduated_at) = &jup_data.graduated_at {
            parts.push(format!("🎓 <b>Graduated At (jup):</b> {}", graduated_at));
        }
        parts.push(format!(
            "🔄 <b>Updated At (jup):</b> {}",
            jup_data.updated_at
        ));
    }
    parts.push(String::new());

    // 15. 📋 DexScreener Orders
    if let Some(orders) = &data.dexscreener_orders_data {
        if !orders.is_empty() {
            parts.push("📋 <b>DexScreener Orders (dex)</b>".to_string());
            for (i, order) in orders.iter().enumerate() {
                let order_num = i + 1;
                parts.push(format!("📋 <b>Order {}:</b>", order_num));
                parts.push(format!("  🏷️ <b>Type:</b> {}", order.r#type));
                parts.push(format!("  📊 <b>Status:</b> {}", order.status));
                if let Some(timestamp) =
                    chrono::DateTime::from_timestamp_millis(order.payment_timestamp)
                {
                    parts.push(format!(
                        "  💰 <b>Payment:</b> {}",
                        timestamp.format("%Y-%m-%d %H:%M")
                    ));
                }
            }
            parts.push(String::new());
        }
    }

    // 16. 🌐 Social Links
    parts.push("🌐 <b>Social Links</b>".to_string());
    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if let Some(info) = &pair.info {
                if let Some(socials) = &info.socials {
                    let social_links_dex: Vec<String> = socials
                        .iter()
                        .filter_map(|s| {
                            s.handle.as_ref().map(|h| {
                                let platform_name = detect_social_platform(h);
                                format!("<a href=\"{}\">{} (dex)</a>", h, platform_name)
                            })
                        })
                        .collect();
                    if !social_links_dex.is_empty() {
                        parts.push(format!(
                            "🔗 <b>Socials (dex):</b> {}",
                            social_links_dex.join(" | ")
                        ));
                    }
                }
                if let Some(websites) = &info.websites {
                    let website_links: Vec<String> = websites
                        .iter()
                        .filter_map(|w| {
                            w.url
                                .as_ref()
                                .map(|u| format!("<a href=\"{}\">Website (dex)</a>", u))
                        })
                        .collect();
                    if !website_links.is_empty() {
                        parts.push(format!(
                            "🌐 <b>Websites (dex):</b> {}",
                            website_links.join(" | ")
                        ));
                    }
                }
            }
        }
    }
    if !social_links.is_empty() {
        let social_parts: Vec<String> = social_links
            .iter()
            .map(|(_name, url)| {
                let empty_string = String::new();
                let url_str = url.as_ref().unwrap_or(&empty_string);
                let platform_name = detect_social_platform(url_str);
                format!("<a href=\"{}\">{} (pf)</a>", url_str, platform_name)
            })
            .collect();
        parts.push(format!(
            "🔗 <b>Socials (pf):</b> {}",
            social_parts.join(" | ")
        ));
    }
    if let Some(jup_data) = &data.jupiter_data {
        let mut jup_social_parts = Vec::new();
        if let Some(twitter) = &jup_data.twitter {
            let platform_name = detect_social_platform(twitter);
            jup_social_parts.push(format!(
                "<a href=\"{}\">{} (jup)</a>",
                twitter, platform_name
            ));
        }
        if let Some(telegram) = &jup_data.telegram {
            let platform_name = detect_social_platform(telegram);
            jup_social_parts.push(format!(
                "<a href=\"{}\">{} (jup)</a>",
                telegram, platform_name
            ));
        }
        if let Some(website) = &jup_data.website {
            let platform_name = detect_social_platform(website);
            jup_social_parts.push(format!(
                "<a href=\"{}\">{} (jup)</a>",
                website, platform_name
            ));
        }
        if !jup_social_parts.is_empty() {
            parts.push(format!(
                "🔗 <b>Socials (jup):</b> {}",
                jup_social_parts.join(" | ")
            ));
        }
    }
    let has_dex_socials = data
        .dexscreener_data
        .as_ref()
        .and_then(|d| d.pairs.as_ref())
        .and_then(|pairs| pairs.first())
        .and_then(|pair| pair.info.as_ref())
        .map(|info| info.socials.is_some() || info.websites.is_some())
        .unwrap_or(false);

    let has_jupiter_socials = data
        .jupiter_data
        .as_ref()
        .map(|j| j.twitter.is_some() || j.telegram.is_some() || j.website.is_some())
        .unwrap_or(false);

    if social_links.is_empty() && !has_dex_socials && !has_jupiter_socials {
        parts.push("No social links found.".to_string());
    }
    parts.push(String::new());

    // 16. 📝 Description
    if !description.is_empty() {
        parts.push("📝 <b>Description</b>".to_string());
        parts.push(html::escape(&description).to_string());
        parts.push(String::new());
    }

    // 17. 📊 Advanced Stats
    if let Some(jup_data) = &data.jupiter_data {
        if let Some(score) = jup_data.organic_score {
            parts.push("📊 <b>Advanced Analytics (jup)</b>".to_string());
            parts.push(format!(
                "🎯 <b>Organic Score:</b> {:.2} ({})",
                score,
                jup_data.organic_score_label.as_deref().unwrap_or("N/A")
            ));
            if let Some(tags) = &jup_data.tags {
                if !tags.is_empty() {
                    parts.push(format!("🏷️ <b>Tags:</b> {}", tags.join(", ")));
                }
            }
            if let Some(likes) = jup_data.ct_likes {
                parts.push(format!("👍 <b>CT Likes:</b> {}", likes));
            }
            if let Some(likes) = jup_data.smart_ct_likes {
                parts.push(format!("🧠 <b>Smart CT Likes:</b> {}", likes));
            }
            if let Some(verified) = jup_data.is_verified {
                if verified {
                    parts.push("✅ <b>Verified</b>".to_string());
                }
            }
            if let Some(cexes) = &jup_data.cexes {
                if !cexes.is_empty() {
                    parts.push(format!("🏛️ <b>CEX Listings:</b> {}", cexes.join(", ")));
                }
            }

            // Timeframe stats
            fn format_stats(name: &str, stats: &Option<crate::types::Stats>) -> Option<String> {
                stats.as_ref().map(|s| {
                    let mut stat_parts = vec![format!("  <b>{} Stats:</b>", name)];
                    stat_parts.push(format!(
                        "    📈 Price Change: {:.2}%",
                        s.price_change.unwrap_or(0.0)
                    ));
                    stat_parts.push(format!(
                        "    📊 Volume: ${:.0} (B: ${:.0} / S: ${:.0})",
                        s.buy_volume.unwrap_or(0.0) + s.sell_volume.unwrap_or(0.0),
                        s.buy_volume.unwrap_or(0.0),
                        s.sell_volume.unwrap_or(0.0)
                    ));
                    stat_parts.push(format!(
                        "    🌱 Organic Volume: ${:.0} (B: ${:.0} / S: ${:.0})",
                        s.buy_organic_volume.unwrap_or(0.0) + s.sell_organic_volume.unwrap_or(0.0),
                        s.buy_organic_volume.unwrap_or(0.0),
                        s.sell_organic_volume.unwrap_or(0.0)
                    ));
                    stat_parts.push(format!(
                        "    👥 Traders: {} (B: {} / S: {})",
                        s.num_traders.unwrap_or(0),
                        s.num_buys.unwrap_or(0),
                        s.num_sells.unwrap_or(0)
                    ));
                    stat_parts.push(format!(
                        "    👥 Holder Change: {:.2}%",
                        s.holder_change.unwrap_or(0.0)
                    ));
                    stat_parts.push(format!(
                        "    💧 Liquidity Change: {:.2}%",
                        s.liquidity_change.unwrap_or(0.0)
                    ));
                    stat_parts.push(format!(
                        "    📊 Volume Change: {:.2}%",
                        s.volume_change.unwrap_or(0.0)
                    ));
                    if let Some(organic_buyers) = s.num_organic_buyers {
                        stat_parts.push(format!("    🌱 Organic Buyers: {}", organic_buyers));
                    }
                    if let Some(net_buyers) = s.num_net_buyers {
                        stat_parts.push(format!("    📈 Net Buyers: {}", net_buyers));
                    }
                    stat_parts.join("\n")
                })
            }

            if let Some(stats_str) = format_stats("1h", &jup_data.stats_1h) {
                parts.push(stats_str);
            }
            if let Some(stats_str) = format_stats("6h", &jup_data.stats_6h) {
                parts.push(stats_str);
            }
            if let Some(stats_str) = format_stats("24h", &jup_data.stats_24h) {
                parts.push(stats_str);
            }
            parts.push(String::new());
        }
    }

    // 18. 🧛 Vamped.fun Status
    if let Some(vamped) = &data.vamped_fun_data {
        parts.push("🧛 <b>Vamped.fun Status</b>".to_string());

        let is_vamped = vamped.is_vamped.unwrap_or(false);
        let status = if is_vamped {
            "✅ Vamped"
        } else {
            "❌ Not Vamped"
        };
        let platform = vamped.platform.as_deref().unwrap_or("Unknown");

        parts.push(format!("{} | <b>Platform:</b> {}", status, platform));

        if let Some(timestamp) = &vamped.timestamp {
            parts.push(format!("⏰ <b>Checked:</b> {}", timestamp));
        }

        if let Some(token_info) = &vamped.token_info {
            if let Some(name) = &token_info.name {
                parts.push(format!("🏷️ <b>Token Name:</b> {}", html::escape(name)));
            }
            if let Some(symbol) = &token_info.symbol {
                parts.push(format!("💎 <b>Symbol:</b> {}", html::escape(symbol)));
            }
        }

        parts.push(String::new());
    }

    // 19. 💬 Engagement & Community
    if let Some(pf) = &data.pump_fun_data {
        let replies = pf.reply_count.unwrap_or(0);
        let participants = pf.num_participants.unwrap_or(0);
        if replies > 0 || participants > 0 {
            parts.push("💬 <b>Community Engagement (pf)</b>".to_string());
            parts.push(format!(
                "💬 <b>Replies:</b> {} | 👥 <b>Participants:</b> {}",
                replies, participants
            ));
            parts.push(String::new());
        }
    }

    // 20. 📺 Livestream Info
    if let Some(pf) = &data.pump_fun_data {
        if pf.livestream_ban_expiry.unwrap_or(0) > 0
            || pf.livestream_downrank_score.unwrap_or(0.0) > 0.0
        {
            parts.push("📺 <b>Livestream Info (pf)</b>".to_string());
            if pf.livestream_ban_expiry.unwrap_or(0) > 0 {
                parts.push(format!(
                    "🚫 <b>Ban Expiry:</b> {}",
                    chrono::DateTime::from_timestamp_millis(pf.livestream_ban_expiry.unwrap())
                        .unwrap()
                        .format("%Y-%m-%d %H:%M")
                ));
            }
            if pf.livestream_downrank_score.unwrap_or(0.0) > 0.0 {
                parts.push(format!(
                    "⬇️ <b>Downrank Score:</b> {:.2}",
                    pf.livestream_downrank_score.unwrap()
                ));
            }
            if let Some(thumbnail_updated_at) = pf.thumbnail_updated_at {
                if let Some(dt) = chrono::DateTime::from_timestamp_millis(thumbnail_updated_at) {
                    parts.push(format!(
                        "🖼️ <b>Thumbnail Updated:</b> {}",
                        dt.format("%Y-%m-%d %H:%M")
                    ));
                }
            }
            parts.push(String::new());
        }
    }

    // 21. 🏛️ Pump.fun Addresses
    if let Some(pf) = &data.pump_fun_data {
        let mut address_lines = Vec::new();
        if let Some(mint) = &pf.mint {
            address_lines.push(format!(
                "🪙 <b>Mint (pf):</b> <code>{}</code> (<a href=\"https://solscan.io/token/{}\">Solscan</a>)",
                mint, mint
            ));
        }
        if let Some(creator) = &pf.creator {
            address_lines.push(format!(
                "👤 <b>Creator:</b> <code>{}</code> (<a href=\"https://solscan.io/account/{}\">Account</a>)",
                creator, creator
            ));
        }
        if let Some(metadata_uri) = &pf.metadata_uri {
            address_lines.push(format!(
                "🗂️ <b>Metadata URI:</b> <a href=\"{}\">{}</a>",
                html::escape(metadata_uri),
                html::escape(metadata_uri)
            ));
        }
        if !address_lines.is_empty() {
            parts.push("🏛️ <b>Pump.fun Addresses</b>".to_string());
            parts.extend(address_lines);
            parts.push(String::new());
        }
    }

    // 22. 🖼️ Pump.fun Media
    if let Some(pf) = &data.pump_fun_data {
        let mut media_lines = Vec::new();
        if let Some(image_uri) = &pf.image_uri {
            media_lines.push(format!(
                "🖼️ <b>Image:</b> <a href=\"{}\">{}</a>",
                html::escape(image_uri),
                html::escape(image_uri)
            ));
        }
        if let Some(banner_uri) = &pf.banner_uri {
            media_lines.push(format!(
                "🏁 <b>Banner:</b> <a href=\"{}\">{}</a>",
                html::escape(banner_uri),
                html::escape(banner_uri)
            ));
        }
        if let Some(thumbnail) = &pf.thumbnail {
            media_lines.push(format!(
                "🖼️ <b>Thumbnail:</b> <a href=\"{}\">{}</a>",
                html::escape(thumbnail),
                html::escape(thumbnail)
            ));
        }
        if let Some(video_uri) = &pf.video_uri {
            media_lines.push(format!(
                "🎥 <b>Video:</b> <a href=\"{}\">{}</a>",
                html::escape(video_uri),
                html::escape(video_uri)
            ));
        }
        if !media_lines.is_empty() {
            parts.push("🖼️ <b>Pump.fun Media</b>".to_string());
            parts.extend(media_lines);
            parts.push(String::new());
        }
    }

    (parts.join("\n"), image_url)
}

fn format_bnb_token_data(data: &BnbTokenData) -> (String, Option<String>) {
    let ca = &data.contract_address;
    let mut parts = Vec::new();

    let name = if data.name.trim().is_empty() {
        "Unknown".to_string()
    } else {
        data.name.trim().to_string()
    };
    let symbol = if data.symbol.trim().is_empty() {
        "N/A".to_string()
    } else {
        data.symbol.trim().to_string()
    };

    let name_esc = html::escape(&name);
    let symbol_esc = html::escape(&symbol);
    let ca_esc = html::escape(ca);

    let primary_pair = data
        .dexscreener_data
        .as_ref()
        .and_then(|dex| select_primary_pair(dex));

    parts.push(format!("🌐 <b>{} ({})</b>", name_esc, symbol_esc));
    parts.push(format!("<code>{}</code>", ca_esc));

    let mut explorer_links = vec![
        format!("<a href=\"https://bscscan.com/token/{0}\">BscScan</a>", ca),
        format!(
            "<a href=\"https://dexscreener.com/bsc/{0}\">DexScreener</a>",
            ca
        ),
    ];
    if let Some(pair) = primary_pair {
        if let Some(url) = &pair.url {
            let dex_label = pair
                .dex_id
                .as_deref()
                .map(|id| id.to_uppercase())
                .unwrap_or_else(|| "DEX".to_string());
            explorer_links.push(format!(
                "<a href=\"{}\">{} Pair (dex)</a>",
                html::escape(url),
                html::escape(&dex_label)
            ));
        }
    }
    if let Some(holder_maps) = &data.holder_maps_url {
        explorer_links.push(format!(
            "<a href=\"{}\">Holder Maps</a>",
            html::escape(holder_maps)
        ));
    }
    if let Some(bubble_maps) = &data.bubble_maps_url {
        explorer_links.push(format!(
            "<a href=\"{}\">BubbleMaps</a>",
            html::escape(bubble_maps)
        ));
    }
    parts.push(explorer_links.join(" | "));

    if let Some(chain_name) = &data.chain_name {
        parts.push(format!("⛓️ <b>Chain:</b> {}", html::escape(chain_name)));
    } else {
        parts.push("⛓️ <b>Chain:</b> BNB Chain".to_string());
    }
    if let Some(pair) = primary_pair {
        if let Some(dex_id) = &pair.dex_id {
            parts.push(format!("🏷️ <b>DEX:</b> {}", html::escape(dex_id)));
        }
        if let Some(labels) = &pair.labels {
            if !labels.is_empty() {
                let labels_text = labels
                    .iter()
                    .map(|label| html::escape(label))
                    .collect::<Vec<_>>()
                    .join(", ");
                parts.push(format!("🏷️ <b>Tags:</b> {}", labels_text));
            }
        }

        if pair.chain_id.is_some()
            || pair.pair_address.is_some()
            || pair.base_token.is_some()
            || pair.quote_token.is_some()
        {
            parts.push("🔗 <b>Pair Metadata (dex)</b>".to_string());
            if let Some(chain_id) = &pair.chain_id {
                parts.push(format!("🌍 <b>Chain ID:</b> {}", html::escape(chain_id)));
            }
            if let Some(pair_address) = &pair.pair_address {
                parts.push(format!(
                    "🔗 <b>Pair Address:</b> <code>{}</code>",
                    html::escape(pair_address)
                ));
            }
            if let Some(base_token) = &pair.base_token {
                let base_name = base_token.name.as_deref().unwrap_or("Unknown");
                let base_symbol = base_token.symbol.as_deref().unwrap_or("?");
                let base_address = base_token.address.as_deref().unwrap_or("n/a");
                parts.push(format!(
                    "🪙 <b>Base:</b> {} ({}) — <code>{}</code>",
                    html::escape(base_name),
                    html::escape(base_symbol),
                    html::escape(base_address)
                ));
            }
            if let Some(quote_token) = &pair.quote_token {
                let quote_name = quote_token.name.as_deref().unwrap_or("Unknown");
                let quote_symbol = quote_token.symbol.as_deref().unwrap_or("?");
                let quote_address = quote_token.address.as_deref().unwrap_or("n/a");
                parts.push(format!(
                    "💱 <b>Quote:</b> {} ({}) — <code>{}</code>",
                    html::escape(quote_name),
                    html::escape(quote_symbol),
                    html::escape(quote_address)
                ));
            }
            parts.push(String::new());
        }
    }
    parts.push(String::new());

    parts.push("💰 <b>Price & Market</b>".to_string());
    if let Some(pair) = primary_pair {
        if let Some(price_usd) = &pair.price_usd {
            parts.push(format!("💰 <b>Price (dex):</b> ${}", price_usd));
        }
        if let Some(price_native) = &pair.price_native {
            let quote_symbol = pair
                .quote_token
                .as_ref()
                .and_then(|q| q.symbol.as_deref())
                .unwrap_or("BNB");
            parts.push(format!(
                "💱 <b>Price ({}):</b> {}",
                html::escape(quote_symbol),
                price_native
            ));
        }
        if let Some(mc) = pair.market_cap {
            parts.push(format!(
                "🧢 <b>MC (dex):</b> ${}",
                format_compact_amount(mc)
            ));
        }
        if let Some(fdv) = pair.fdv {
            parts.push(format!(
                "💎 <b>FDV (dex):</b> ${}",
                format_compact_amount(fdv)
            ));
        }
    }
    if let Some(price_str) = maybe_format_float(data.price, 12) {
        parts.push(format!("💰 <b>Price:</b> ${}", price_str));
    }
    if let Some(mc) = data.market_cap {
        parts.push(format!(
            "🧢 <b>Market Cap:</b> ${}",
            format_compact_amount(mc)
        ));
    }
    if let Some(liq) = data.liquidity {
        parts.push(format!(
            "💧 <b>Liquidity:</b> ${}",
            format_compact_amount(liq)
        ));
    }
    if let Some(volume) = data.volume_24h {
        parts.push(format!(
            "📊 <b>24h Volume:</b> ${}",
            format_compact_amount(volume)
        ));
    }
    if let Some(summary_pairs) = &data.dexscreener_token_summary {
        if !summary_pairs.is_empty() {
            parts.push(String::new());
            parts.push("📌 <b>Dex Summary (tokens)</b>".to_string());
            for summary in summary_pairs {
                let dex_id = summary.dex_id.clone().unwrap_or_else(|| "dex".to_string());
                let chain_id = summary
                    .chain_id
                    .clone()
                    .unwrap_or_else(|| "unknown".to_string());
                let price_usd = summary.price_usd.as_deref().unwrap_or("n/a");
                let price_native = summary.price_native.as_deref().unwrap_or("n/a");
                let base_symbol = summary
                    .base_token
                    .as_ref()
                    .and_then(|t| t.symbol.as_deref())
                    .unwrap_or("?");
                let quote_symbol = summary
                    .quote_token
                    .as_ref()
                    .and_then(|t| t.symbol.as_deref())
                    .unwrap_or("?");
                let pair_url = summary.url.as_deref().unwrap_or("https://dexscreener.com");
                let pair_address = summary.pair_address.as_deref().unwrap_or("n/a");

                parts.push(format!(
                    "• {} ({}) | Base {} / Quote {} | Price ${} ({})",
                    html::escape(&dex_id),
                    html::escape(&chain_id),
                    html::escape(base_symbol),
                    html::escape(quote_symbol),
                    html::escape(price_usd),
                    html::escape(price_native)
                ));

                if let Some(volume) = &summary.volume {
                    parts.push(format!(
                        "  📊 Vol 24h/6h/1h/5m: ${:.0} / ${:.0} / ${:.0} / ${:.0}",
                        volume.h24.unwrap_or(0.0),
                        volume.h6.unwrap_or(0.0),
                        volume.h1.unwrap_or(0.0),
                        volume.m5.unwrap_or(0.0)
                    ));
                }
                if let Some(price_change) = &summary.price_change {
                    parts.push(format!(
                        "  📈 Δ 24h/6h/1h/5m: {:.2}% / {:.2}% / {:.2}% / {:.2}%",
                        price_change.h24.unwrap_or(0.0),
                        price_change.h6.unwrap_or(0.0),
                        price_change.h1.unwrap_or(0.0),
                        price_change.m5.unwrap_or(0.0)
                    ));
                }
                if let Some(liquidity) = &summary.liquidity {
                    parts.push(format!(
                        "  💧 Liquidity: USD ${} | Base {:.2} | Quote {:.2}",
                        liquidity
                            .usd
                            .map(format_compact_amount)
                            .unwrap_or_else(|| "0".to_string()),
                        liquidity.base.unwrap_or(0.0),
                        liquidity.quote.unwrap_or(0.0)
                    ));
                }
                if let Some(fdv) = summary.fdv {
                    parts.push(format!("  💎 FDV: ${}", format_compact_amount(fdv)));
                }
                if let Some(market_cap) = summary.market_cap {
                    parts.push(format!(
                        "  🧢 Market Cap: ${}",
                        format_compact_amount(market_cap)
                    ));
                }
                if let Some(pair_created_at) = summary.pair_created_at {
                    if let Some(formatted) = format_pair_timestamp(pair_created_at) {
                        parts.push(format!("  🆕 Pair Created: {}", formatted));
                    }
                }

                parts.push(format!(
                    "  🔗 Pair Address: <code>{}</code>",
                    html::escape(pair_address)
                ));
                parts.push(format!(
                    "  🔗 Link: <a href=\"{}\">{} pair (tokens)</a>",
                    html::escape(pair_url),
                    html::escape(&dex_id.to_uppercase())
                ));
            }
        }
    }
    if let Some(pair) = primary_pair {
        if let Some(volume) = &pair.volume {
            parts.push(String::new());
            parts.push("📊 <b>Volume (dex)</b>".to_string());
            parts.push(format!(
                "📊 <b>24h:</b> ${:.0} | 6h: ${:.0} | 1h: ${:.0} | 5m: ${:.0}",
                volume.h24.unwrap_or(0.0),
                volume.h6.unwrap_or(0.0),
                volume.h1.unwrap_or(0.0),
                volume.m5.unwrap_or(0.0)
            ));
        }
    }
    parts.push(String::new());

    parts.push("📈 <b>Price Changes</b>".to_string());
    if let Some(change) = maybe_format_percentage(data.change_24h) {
        parts.push(format!("📈 <b>24h:</b> {}%", change));
    }
    if let Some(change_4h) = maybe_format_percentage(data.change_4h) {
        parts.push(format!("⏱️ <b>4h:</b> {}%", change_4h));
    }
    if let Some(change_1h) = maybe_format_percentage(data.change_1h) {
        parts.push(format!("🕒 <b>1h:</b> {}%", change_1h));
    }
    if let Some(change_5m) = maybe_format_percentage(data.change_5m) {
        parts.push(format!("⚡ <b>5m:</b> {}%", change_5m));
    }
    if let Some(pair) = primary_pair {
        if let Some(price_change) = &pair.price_change {
            parts.push(format!(
                "📈 <b>24h/6h/1h/5m (dex):</b> {:.2}% / {:.2}% / {:.2}% / {:.2}%",
                price_change.h24.unwrap_or(0.0),
                price_change.h6.unwrap_or(0.0),
                price_change.h1.unwrap_or(0.0),
                price_change.m5.unwrap_or(0.0)
            ));
        }
    }
    parts.push(String::new());

    parts.push("👥 <b>Holder Metrics</b>".to_string());
    if let Some(holders) = data.holders {
        parts.push(format!("👥 <b>Total Holders:</b> {}", holders));
    }
    if let Some(top10) = maybe_format_percentage(data.top10_hold_percentage) {
        parts.push(format!("🏦 <b>Top 10 Share:</b> {}%", top10));
    }
    if let Some(dev_ratio_pct) = maybe_format_percentage(data.dev_holding_ratio.map(|v| v * 100.0))
    {
        parts.push(format!("🛠️ <b>Dev Holding:</b> {}%", dev_ratio_pct));
    }
    parts.push(String::new());

    if let Some(pair) = primary_pair {
        if let Some(txns) = &pair.txns {
            if let (Some(h24), Some(h6), Some(h1), Some(m5)) =
                (&txns.h24, &txns.h6, &txns.h1, &txns.m5)
            {
                parts.push(String::new());
                parts.push("🔄 <b>Transactions (dex)</b>".to_string());
                parts.push(format!(
                    "🔄 <b>24h:</b> {} buys / {} sells",
                    h24.buys.unwrap_or(0),
                    h24.sells.unwrap_or(0)
                ));
                parts.push(format!(
                    "⏱️ <b>6h:</b> {} buys / {} sells",
                    h6.buys.unwrap_or(0),
                    h6.sells.unwrap_or(0)
                ));
                parts.push(format!(
                    "🕒 <b>1h:</b> {} buys / {} sells",
                    h1.buys.unwrap_or(0),
                    h1.sells.unwrap_or(0)
                ));
                parts.push(format!(
                    "⚡ <b>5m:</b> {} buys / {} sells",
                    m5.buys.unwrap_or(0),
                    m5.sells.unwrap_or(0)
                ));
            }
        }

        if let Some(liquidity) = &pair.liquidity {
            parts.push(String::new());
            parts.push("💧 <b>Liquidity (dex)</b>".to_string());
            parts.push(format!(
                "💧 <b>USD:</b> ${}",
                liquidity
                    .usd
                    .map(format_compact_amount)
                    .unwrap_or_else(|| "0".to_string())
            ));
            parts.push(format!(
                "🪙 <b>Base/Quote:</b> {:.2} / {:.2}",
                liquidity.base.unwrap_or(0.0),
                liquidity.quote.unwrap_or(0.0)
            ));
        }

        if let Some(info) = &pair.info {
            if let Some(websites) = &info.websites {
                let website_lines: Vec<String> = websites
                    .iter()
                    .filter_map(|website| website.url.as_ref())
                    .map(|url| {
                        let safe_url = html::escape(url);
                        format!("🔗 <a href=\"{0}\">{0}</a>", safe_url)
                    })
                    .collect();
                if !website_lines.is_empty() {
                    parts.push(String::new());
                    parts.push("🌐 <b>Websites (dex)</b>".to_string());
                    parts.extend(website_lines);
                }
            }

            if let Some(socials) = &info.socials {
                let mut social_lines = Vec::new();
                for social in socials {
                    if let Some(handle) = social.handle.as_deref() {
                        let label = format_social_label(social.platform.as_deref(), handle);
                        let safe_handle = html::escape(handle);
                        let safe_label = html::escape(&label);
                        social_lines.push(format!(
                            "📣 <b>{}:</b> <a href=\"{}\">{}</a>",
                            safe_label, safe_handle, safe_handle
                        ));
                    }
                }
                if !social_lines.is_empty() {
                    parts.push(String::new());
                    parts.push("📣 <b>Socials (dex)</b>".to_string());
                    parts.extend(social_lines);
                }
            }

            if let Some(image_url) = &info.image_url {
                if data.token_logo_url.is_none() {
                    parts.push(String::new());
                    parts.push(format!(
                        "🖼️ <b>Image (dex):</b> <a href=\"{0}\">{0}</a>",
                        html::escape(image_url)
                    ));
                }
            }
        }

        if let Some(boosts) = &pair.boosts {
            if boosts.active.unwrap_or(0) > 0 {
                parts.push(String::new());
                parts.push(format!(
                    "🚀 <b>Boosts (dex):</b> {} active",
                    boosts.active.unwrap_or(0)
                ));
            }
        }

        if let Some(created_at) = pair.pair_created_at {
            if let Some(formatted) = format_pair_timestamp(created_at) {
                parts.push(String::new());
                parts.push(format!("🆕 <b>Pair Created (dex):</b> {}", formatted));
            }
        }
    }

    if let Some(dex_data) = &data.dexscreener_data {
        if let Some(pairs) = &dex_data.pairs {
            if pairs.len() > 1 {
                parts.push("🔁 <b>Other Pairs (dex)</b>".to_string());
                let primary_address = primary_pair
                    .and_then(|pair| pair.pair_address.clone())
                    .unwrap_or_default();
                for pair in pairs {
                    let pair_addr = pair.pair_address.clone().unwrap_or_default();
                    if !primary_address.is_empty()
                        && pair_addr.eq_ignore_ascii_case(&primary_address)
                    {
                        continue;
                    }
                    let dex_id = pair.dex_id.clone().unwrap_or_else(|| "dex".to_string());
                    let chain_id = pair.chain_id.as_deref().unwrap_or("unknown");
                    let price = pair.price_usd.as_deref().unwrap_or("n/a");
                    let liq = pair
                        .liquidity
                        .as_ref()
                        .and_then(|l| l.usd)
                        .map(|usd| format_compact_amount(usd))
                        .unwrap_or_else(|| "0".to_string());
                    let base_symbol = pair
                        .base_token
                        .as_ref()
                        .and_then(|t| t.symbol.as_deref())
                        .unwrap_or("?");
                    let quote_symbol = pair
                        .quote_token
                        .as_ref()
                        .and_then(|t| t.symbol.as_deref())
                        .unwrap_or("?");
                    let url = pair.url.as_deref().unwrap_or("https://dexscreener.com");
                    let pair_addr_display = if pair_addr.is_empty() {
                        "n/a".to_string()
                    } else {
                        pair_addr.clone()
                    };
                    parts.push(format!(
                        "• {} ({}) | Base {} | Quote {} | Price ${} | 💧 ${} | Pair: <code>{}</code> | <a href=\"{}\">{} pair (dex)</a>",
                        html::escape(&dex_id),
                        html::escape(chain_id),
                        html::escape(base_symbol),
                        html::escape(quote_symbol),
                        html::escape(price),
                        html::escape(&liq),
                        html::escape(&pair_addr_display),
                        html::escape(url),
                        html::escape(&dex_id.to_uppercase())
                    ));
                }
                parts.push(String::new());
            }
        }
    }

    if let Some(orders) = &data.dexscreener_orders_data {
        parts.push("🧾 <b>Dex Orders</b>".to_string());
        let mut token_profile = None;
        let mut takeover_order = None;

        for order in orders {
            if order.r#type == "tokenProfile" && order.status.eq_ignore_ascii_case("approved") {
                token_profile = Some(order);
            }
            if order.r#type == "communityTakeover" && order.status.eq_ignore_ascii_case("approved")
            {
                takeover_order = Some(order);
            }
        }

        if let Some(order) = token_profile {
            let mut line = String::from("💠 <b>Token Profile Paid:</b> ✅");
            if let Some(human) = format_relative_timestamp(order.payment_timestamp) {
                line.push_str(&format!(" ({})", human));
            }
            if let Some(iso) = format_unix_timestamp_ms(order.payment_timestamp) {
                line.push_str(&format!("\n   <code>{}</code>", iso));
            }
            parts.push(line);
        } else {
            parts.push("💠 <b>Token Profile Paid:</b> ❌".to_string());
        }

        if let Some(order) = takeover_order {
            let mut line = String::from("🤝 <b>Community Takeover:</b> ✅");
            if let Some(human) = format_relative_timestamp(order.payment_timestamp) {
                line.push_str(&format!(" ({})", human));
            }
            if let Some(iso) = format_unix_timestamp_ms(order.payment_timestamp) {
                line.push_str(&format!("\n   <code>{}</code>", iso));
            }
            parts.push(line);
        }

        let mut order_lines = Vec::new();
        for order in orders.iter().take(5) {
            let mut line = format!("• {} ({})", order.r#type, order.status);
            if let Some(human) = format_relative_timestamp(order.payment_timestamp) {
                line.push_str(&format!(" – {}", human));
            }
            order_lines.push(line);
        }
        if !order_lines.is_empty() {
            parts.push(order_lines.join("\n"));
        }
        parts.push(String::new());
    }

    if let Some(risk_level) = data.risk_level {
        parts.push(format!("🚨 <b>Risk Level:</b> {}", risk_level));
    }

    let mut image_url = data.token_logo_url.clone();
    if image_url.is_none() {
        image_url = primary_pair
            .and_then(|pair| pair.info.as_ref())
            .and_then(|info| info.image_url.clone());
    }
    (parts.join("\n"), image_url)
}
