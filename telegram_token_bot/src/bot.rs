use crate::api::ApiClient;
use crate::types::*;
use anyhow::Result;
use regex::Regex;
use std::sync::Arc;
use std::time::Instant;
use teloxide::{prelude::*, utils::html};

pub async fn start_bot(bot_token: String, api_client: ApiClient) -> Result<()> {
    let bot = Bot::new(bot_token);
    let api_client = Arc::new(api_client);

    teloxide::repl(bot, move |bot: Bot, msg: Message| {
        let api_client = Arc::clone(&api_client);
        async move {
            handle_message(bot, msg, api_client).await
        }
    })
    .await;

    Ok(())
}

async fn handle_message(
    bot: Bot,
    msg: Message,
    api_client: Arc<ApiClient>,
) -> ResponseResult<()> {
    if let Some(text) = msg.text() {
        if let Some(contract_address) = detect_contract_address(text) {
            // Start timing
            let start_time = Instant::now();

            // Analyze token
            match api_client.analyze_token(&contract_address).await {
                Ok(token_data) => {
                    let elapsed = start_time.elapsed();
                    let timing_text = format!("⚡ {}ms!", elapsed.as_millis());
                    let (formatted_text, _image_url) = format_token_data(&token_data);
                    let final_text = format!("{}\n\n{}", timing_text, formatted_text);

                    // Send single message with timing and results
                    bot.send_message(msg.chat.id, final_text)
                        .parse_mode(teloxide::types::ParseMode::Html)
                        .disable_web_page_preview(true)
                        .await?;
                }
                Err(e) => {
                    let elapsed = start_time.elapsed();
                    let timing_text = format!("⚡ {}ms!", elapsed.as_millis());
                    let error_text = format!("{}\n\n❌ Error analyzing token: {}", timing_text, e);

                    bot.send_message(msg.chat.id, error_text)
                        .await?;
                }
            }
        } else {
            bot.send_message(msg.chat.id, "🪙 Send me a contract address to analyze token data!")
                .await?;
        }
    }

    Ok(())
}

fn detect_contract_address(text: &str) -> Option<String> {
    // #COMPLETION_DRIVE: Assuming Solana address regex pattern is correct
    // #SUGGEST_VERIFY: Test with various Solana address formats to ensure accuracy

    let pattern = Regex::new(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b").ok()?;
    pattern.find(text).map(|m| m.as_str().to_string())
}

fn format_token_data(data: &TokenData) -> (String, Option<String>) {
    let ca = &data.mint_address;

    // Extract basic token info
    let (name, symbol, description, is_mutable) = extract_basic_info(data);
    let (_price, market_cap, fdv, volume_data, price_changes) = extract_price_info(data);
    let _supply = extract_supply_info(data);
    let holders_info = extract_holders_info(data);
    let social_links = extract_social_links(data);
    let pump_info = extract_pump_info(data);
    let livestream_info = extract_livestream_info(data);

    let mut parts = Vec::new();

    // Header
    parts.push(format!("🚀 <b>{} ({})</b>", html::escape(&name), html::escape(&symbol)));
    parts.push(format!("<code>{}</code>", html::escape(ca)));
    parts.push(format!(
        "<a href=\"https://solscan.io/token/{}\">Solscan</a> | <a href=\"https://dexscreener.com/solana/{}\">DexScreener</a> | <a href=\"https://birdeye.so/token/{}?chain=solana\">Birdeye</a>",
        ca, ca, ca
    ));
    parts.push(String::new());

    // Market Data
    parts.push(format!("🧢 <b>MC:</b> ${:.0} | 💧 <b>Liq:</b> ${:.0}", market_cap, 0.0));
    parts.push(format!("💎 <b>FDV:</b> ${:.0}", fdv));

    if let Some(vol) = volume_data {
        parts.push(format!("📊 <b>Vol (6h):</b> ${:.0} | <b>(1h):</b> ${:.0}",
            vol.h6.unwrap_or(0.0), vol.h1.unwrap_or(0.0)));
    }
    parts.push(String::new());

    // Price Changes
    if let Some(changes) = price_changes {
        let change_1h = changes.h1.unwrap_or(0.0);
        let change_6h = changes.h6.unwrap_or(0.0);
        let emoji_1h = if change_1h > 0.0 { "🚀" } else if change_1h < 0.0 { "📉" } else { "😐" };
        let emoji_6h = if change_6h > 0.0 { "🔥" } else if change_6h < 0.0 { "💀" } else { "😐" };

        parts.push("📉 <b>Price Change (1h/6h)</b>".to_string());
        parts.push(format!("{} {:+.1}% / {} {:+.1}%", emoji_1h, change_1h, emoji_6h, change_6h));
        parts.push(String::new());
    }

    // Holders
    if let Some(holders) = holders_info {
        parts.push(format!("👥 <b>Holders:</b> {}", holders.len()));
        parts.push(String::new());
    }

    // Security & Dev
    parts.push("🔒 <b>Security & Dev</b>".to_string());

    if let Some(pump) = &pump_info {
        if let Some(sniper_count) = pump.sniper_count {
            let sniper_percentage = pump.sniper_owned_percentage.unwrap_or(0.0);
            parts.push(format!("⚠️ <b>Risk:</b> Snipers: {} ({:.2}%)", sniper_count, sniper_percentage));
        }
    }

    parts.push(format!("🔧 <b>Mutable:</b> {}", if is_mutable { "✅" } else { "❌" }));
    parts.push(String::new());

    // Socials
    parts.push("🌐 <b>Socials</b>".to_string());
    if !social_links.is_empty() {
        let social_parts: Vec<String> = social_links.iter().map(|(name, url)| {
            format!("<a href=\"{}\">{}</a>", url, name)
        }).collect();
        parts.push(social_parts.join(" | "));
    } else {
        parts.push("No social links found.".to_string());
    }
    parts.push(String::new());

    // Livestream Status
    if let Some(livestream) = livestream_info {
        if livestream.is_live.unwrap_or(false) {
            let participants = livestream.participants.unwrap_or(0);
            let replies = livestream.replies.unwrap_or(0);
            parts.push("📺 <b>Livestream Status</b>".to_string());
            parts.push(format!("└ 🟢 Live | 👥 {} participants | 💬 {} replies", participants, replies));
            parts.push(String::new());
        }
    }

    // Description
    if !description.is_empty() {
        parts.push(format!("📝 {}", html::escape(&description)));
        parts.push(String::new());
    }

    (parts.join("\n"), None) // Image URL not implemented yet
}

fn extract_basic_info(data: &TokenData) -> (String, String, String, bool) {
    let mut name = "Unknown".to_string();
    let mut symbol = "N/A".to_string();
    let mut description = String::new();
    let mut is_mutable = false;

    if let Some(metadata) = &data.metadata {
        if let Some(on_chain) = &metadata.on_chain_metadata {
            if let Some(meta) = &on_chain.metadata {
                if let Some(n) = &meta.data.name {
                    name = n.trim().to_string();
                }
                if let Some(s) = &meta.data.symbol {
                    symbol = s.trim().to_string();
                }
                is_mutable = meta.is_mutable.unwrap_or(false);
            }
        }

        if let Some(off_chain) = &metadata.off_chain_metadata {
            if let Some(meta) = &off_chain.metadata {
                if let Some(n) = &meta.name {
                    name = n.clone();
                }
                if let Some(s) = &meta.symbol {
                    symbol = s.clone();
                }
                if let Some(d) = &meta.description {
                    description = d.clone();
                }
            }
        }
    }

    (name, symbol, description, is_mutable)
}

fn extract_price_info(data: &TokenData) -> (f64, f64, f64, Option<VolumeData>, Option<PriceChangeData>) {
    if let Some(price_data) = &data.price_data {
        if let Some(pairs) = &price_data.pairs {
            if let Some(pair) = pairs.first() {
                let price = pair.price_usd.as_ref()
                    .and_then(|p| p.parse::<f64>().ok())
                    .unwrap_or(0.0);
                let market_cap = pair.market_cap.unwrap_or(0.0);
                let supply = extract_supply_info(data);
                let fdv = if supply > 0.0 { price * supply } else { 0.0 };

                return (price, market_cap, fdv, pair.volume.clone(), pair.price_change.clone());
            }
        }
    }
    (0.0, 0.0, 0.0, None, None)
}

fn extract_supply_info(data: &TokenData) -> f64 {
    if let Some(supply_info) = &data.supply_info {
        if let Some(result) = &supply_info.result {
            if let Some(value) = &result.value {
                return value.ui_amount.unwrap_or(0.0);
            }
        }
    }
    0.0
}

fn extract_holders_info(data: &TokenData) -> Option<Vec<TokenHolder>> {
    if let Some(holders_data) = &data.holders {
        if let Some(result) = &holders_data.result {
            return result.value.clone();
        }
    }
    None
}

fn extract_social_links(data: &TokenData) -> Vec<(String, String)> {
    let mut links = Vec::new();

    if let Some(metadata) = &data.metadata {
        if let Some(off_chain) = &metadata.off_chain_metadata {
            if let Some(meta) = &off_chain.metadata {
                if let Some(twitter) = &meta.twitter {
                    links.push(("X/Twitter".to_string(), twitter.clone()));
                }
                if let Some(telegram) = &meta.telegram {
                    links.push(("Telegram".to_string(), telegram.clone()));
                }
                if let Some(website) = &meta.website {
                    links.push(("Website".to_string(), website.clone()));
                }
            }
        }
    }

    links
}

fn extract_pump_info(data: &TokenData) -> Option<&PumpAnalytics> {
    data.pump_analytics.as_ref()
}

fn extract_livestream_info(data: &TokenData) -> Option<&LivestreamData> {
    data.livestream.as_ref()
}