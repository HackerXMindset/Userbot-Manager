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

                    // Smart section-aware message splitting
                    send_split_message(&bot, &msg, &final_text).await?;
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

async fn send_split_message(bot: &Bot, msg: &Message, text: &str) -> ResponseResult<()> {
    let max_length = 4000;

    // Define section headers that make good break points
    let section_headers = [
        "🪐 <b>Jupiter Token Analysis</b>",
        "📜 <b>DexScreener Orders (Dex)</b>", 
        "🔒 <b>Security & Dev</b>",
        "🌐 <b>Socials</b>",
        "📈 <b>DexScreener Data</b>",
        "💰 <b>Price & Market Data</b>",
        "📊 <b>Volume Data (Dex)</b>",
        "💧 <b>Liquidity (Dex)</b>", 
        "🔄 <b>Transactions</b>",
        "🗓️ <b>Timestamps (pf)</b>",
        "💬 <b>Engagement (pf)</b>",
        "🎢 <b>Bonding Curve (pf)</b>",
        "🚦 <b>Status (pf)</b>",
        "⚙️ <b>System Info (pf)</b>",
        "📺 <b>Livestream (pf)</b>",
    ];

    let lines: Vec<&str> = text.split('\n').collect();
    let mut chunks = Vec::new();
    let mut current_chunk = Vec::new();
    let mut current_length = 0;

    for line in lines {
        let line_length = line.len() + 1; // +1 for newline

        // Check if this line is a section header
        let is_section_header = section_headers.iter().any(|header| line.contains(header));

        // If adding this line would exceed the limit, and we have content, start a new chunk
        if current_length + line_length > max_length && !current_chunk.is_empty() {
            chunks.push(current_chunk.join("\n"));
            current_chunk.clear();
            current_length = 0;
        }
        // If this is a section header and we already have substantial content, break here
        else if is_section_header && current_length > (max_length as f64 * 0.7) as usize && !current_chunk.is_empty() {
            chunks.push(current_chunk.join("\n"));
            current_chunk.clear();
            current_length = 0;
        }

        current_chunk.push(line);
        current_length += line_length;
    }

    // Add the last chunk
    if !current_chunk.is_empty() {
        chunks.push(current_chunk.join("\n"));
    }

    // Send each chunk
    for chunk in chunks {
        if !chunk.trim().is_empty() {
            bot.send_message(msg.chat.id, &chunk)
                .parse_mode(teloxide::types::ParseMode::Html)
                .disable_web_page_preview(true)
                .await?;
        }
    }

    Ok(())
}

fn detect_contract_address(text: &str) -> Option<String> {
    // Solana address regex pattern has been noted. Testing with various Solana address formats is recommended to ensure accuracy.
    let pattern = Regex::new(r"\b[1-9A-HJ-NP-Za-km-z]{32,44}\b").ok()?;
    pattern.find(text).map(|m| m.as_str().to_string())
}

fn format_jupiter_data(jup_data: &JupiterTokenData) -> String {
    let mut parts = Vec::new();
    parts.push("🪐 <b>Jupiter Token Analysis</b>".to_string());

    if let Some(score) = jup_data.organic_score {
        parts.push(format!("- <b>Organic Score:</b> {:.2} ({})", score, jup_data.organic_score_label.as_deref().unwrap_or("N/A")));
    }

    if let Some(tags) = &jup_data.tags {
        if !tags.is_empty() {
            parts.push(format!("- <b>Tags:</b> {}", tags.join(", ")));
        }
    }

    if let Some(twitter) = &jup_data.twitter {
        parts.push(format!("- <b>Twitter (Jup):</b> {}", twitter));
    }
    if let Some(telegram) = &jup_data.telegram {
        parts.push(format!("- <b>Telegram (Jup):</b> {}", telegram));
    }
    if let Some(website) = &jup_data.website {
        parts.push(format!("- <b>Website (Jup):</b> {}", website));
    }
    if let Some(likes) = jup_data.ct_likes {
        parts.push(format!("- <b>CT Likes (Jup):</b> {}", likes));
    }
    if let Some(likes) = jup_data.smart_ct_likes {
        parts.push(format!("- <b>Smart CT Likes (Jup):</b> {}", likes));
    }
    if let Some(verified) = jup_data.is_verified {
        if verified {
            parts.push("- <b>Verified (Jup):</b> ✅".to_string());
        }
    }
    if let Some(cexes) = &jup_data.cexes {
        if !cexes.is_empty() {
            parts.push(format!("- <b>CEXes (Jup):</b> {}", cexes.join(", ")));
        }
    }

    if let Some(price) = jup_data.usd_price {
        parts.push(format!("- <b>Price (Jup):</b> ${}", price));
    }
    if let Some(mcap) = jup_data.mcap {
        parts.push(format!("- <b>Market Cap (Jup):</b> ${:.0}", mcap));
    }
    if let Some(fdv) = jup_data.fdv {
        parts.push(format!("- <b>FDV (Jup):</b> ${:.0}", fdv));
    }
    if let Some(liquidity) = jup_data.liquidity {
        parts.push(format!("- <b>Liquidity (Jup):</b> ${:.0}", liquidity));
    }
    if let Some(holders) = jup_data.holder_count {
        parts.push(format!("- <b>Holders (Jup):</b> {}", holders));
    }

    if let Some(audit) = &jup_data.audit {
        parts.push("".to_string());
        parts.push("  <b>Security Audit (Jup):</b>".to_string());
        parts.push(format!("  - Mint Authority: {}", if audit.mint_authority_disabled.unwrap_or(false) { "Disabled ✅" } else { "Enabled ⚠️" }));
        parts.push(format!("  - Freeze Authority: {}", if audit.freeze_authority_disabled.unwrap_or(false) { "Disabled ✅" } else { "Enabled ⚠️" }));
        if let Some(top_holders) = audit.top_holders_percentage {
            parts.push(format!("  - Top Holders: {:.2}%", top_holders));
        }
        parts.push(format!("  - Snipers: {:.2}%", audit.snipers_holding_percentage.unwrap_or(0.0)));
        if let Some(dev_migrations) = audit.dev_migrations {
            parts.push(format!("  - Dev Migrations: {}", dev_migrations));
        }
        if let Some(dev_balance) = audit.dev_balance_percentage {
            parts.push(format!("  - Dev Balance: {:.2}%", dev_balance));
        }
    }

    fn format_stats(name: &str, stats: &Option<Stats>) -> Option<String> {
        stats.as_ref().map(|s| {
            let mut stat_parts = vec![format!("  <b>{} Stats:</b>", name)];
            stat_parts.push(format!("    Price Change: {:.2}%", s.price_change.unwrap_or(0.0)));
            stat_parts.push(format!("    Volume: ${:.0} (B: ${:.0} / S: ${:.0})", s.buy_volume.unwrap_or(0.0) + s.sell_volume.unwrap_or(0.0), s.buy_volume.unwrap_or(0.0), s.sell_volume.unwrap_or(0.0)));
            stat_parts.push(format!("    Organic Volume: ${:.0} (B: ${:.0} / S: ${:.0})", s.buy_organic_volume.unwrap_or(0.0) + s.sell_organic_volume.unwrap_or(0.0), s.buy_organic_volume.unwrap_or(0.0), s.sell_organic_volume.unwrap_or(0.0)));
            stat_parts.push(format!("    Traders: {} (B: {} / S: {})", s.num_traders.unwrap_or(0), s.num_buys.unwrap_or(0), s.num_sells.unwrap_or(0)));
            stat_parts.push(format!("    Holder Change: {:.2}%", s.holder_change.unwrap_or(0.0)));
            stat_parts.push(format!("    Liquidity Change: {:.2}%", s.liquidity_change.unwrap_or(0.0)));
            stat_parts.join("\n")
        })
    }

    parts.push("".to_string());
    if let Some(stats_str) = format_stats("5m", &jup_data.stats_5m) {
        parts.push(stats_str);
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


    if let Some(bonding_curve) = jup_data.bonding_curve {
        parts.push("".to_string());
        parts.push(format!("- <b>Bonding Curve (Jup):</b> {:.2}%", bonding_curve));
    }

    parts.join("\n")
}

fn format_token_data(data: &TokenData) -> (String, Option<String>) {
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
                symbol = meta.data.symbol.clone().unwrap_or(symbol).trim().to_string();
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
        if pf.twitter.is_some() { social_links.insert("Twitter".to_string(), pf.twitter.clone()); }
        if pf.telegram.is_some() { social_links.insert("Telegram".to_string(), pf.telegram.clone()); }
        if pf.website.is_some() { social_links.insert("Website".to_string(), pf.website.clone()); }
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

    // Check DEX paid status early for prominent display
    let (dex_paid_status, dex_paid_dot) = if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            if pair.info.is_some() {
                ("Available", "🟢")
            } else {
                ("Not Available", "🔴")
            }
        } else {
            ("Not Available", "🔴")
        }
    } else {
        ("Not Available", "🔴")
    };

    // Header
    parts.push(format!("🚀 <b>{} ({})</b>", name_esc, symbol_esc));
    parts.push(format!("<code>{}</code>", ca_esc));
    parts.push(format!(
        "<a href=\"https://solscan.io/token/{}\">Solscan</a> | <a href=\"https://dexscreener.com/solana/{}\">DexScreener</a> | <a href=\"https://birdeye.so/token/{}?chain=solana\">Birdeye</a>",
        ca, ca, ca
    ));

    // Prominent DEX Paid Status
    let info_link = format!("https://t.me/phanesbot?start=dp_{}", ca);
    parts.push(format!("{} <b>DEX Paid:</b> {} <a href=\"{}\">[info]</a>", dex_paid_dot, dex_paid_status, info_link));
    parts.push(String::new());

    // Market Data (from dexscreener)
    let (market_cap, fdv, liquidity_usd) = if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            (pair.market_cap.unwrap_or(0.0), pair.fdv.unwrap_or(0.0), pair.liquidity.as_ref().map_or(0.0, |l| l.usd.unwrap_or(0.0)))
        } else {
            (0.0, 0.0, 0.0)
        }
    } else {
        (0.0, 0.0, 0.0)
    };

    if let Some(dexscreener_data) = &data.dexscreener_data {
        if let Some(pair) = dexscreener_data.pairs.as_ref().and_then(|p| p.first()) {
            parts.push("📈 <b>DexScreener Data</b>".to_string());
            if let Some(dex_id) = &pair.dex_id {
                parts.push(format!("<b>DEX:</b> {}", dex_id));
            }
            if let Some(pair_address) = &pair.pair_address {
                parts.push(format!("<b>Pair:</b> <code>{}</code>", pair_address));
            }
            if let Some(url) = &pair.url {
                parts.push(format!("<a href=\"{}\">View on DexScreener</a>", url));
            }
            if let (Some(base), Some(quote)) = (&pair.base_token, &pair.quote_token) {
                parts.push(format!("<b>Base:</b> {} ({}) - <code>{}</code>", base.name.as_deref().unwrap_or("N/A"), base.symbol.as_deref().unwrap_or("N/A"), base.address.as_deref().unwrap_or("N/A")));
                parts.push(format!("<b>Quote:</b> {} ({}) - <code>{}</code>", quote.name.as_deref().unwrap_or("N/A"), quote.symbol.as_deref().unwrap_or("N/A"), quote.address.as_deref().unwrap_or("N/A")));
            }

            parts.push(format!("🧢 <b>MC (dex):</b> ${:.0}", pair.market_cap.unwrap_or(0.0)));
            parts.push(format!("💎 <b>FDV (dex):</b> ${:.0}", pair.fdv.unwrap_or(0.0)));
            parts.push(format!("💧 <b>Liq (dex):</b> ${:.0}", pair.liquidity.as_ref().map_or(0.0, |l| l.usd.unwrap_or(0.0))));
            if let Some(liquidity) = &pair.liquidity {
                parts.push(format!("<b>Liq (base/quote):</b> {:.2} / {:.2}", liquidity.base.unwrap_or(0.0), liquidity.quote.unwrap_or(0.0)));
            }

            if let Some(price_native) = &pair.price_native {
                parts.push(format!("💰 <b>Price (native):</b> {}", price_native));
            }
            if let Some(volume) = &pair.volume {
                parts.push(format!("📊 <b>Volume (24h):</b> ${:.0}", volume.h24.unwrap_or(0.0)));
                parts.push(format!("<b>Volume (6h/1h/5m):</b> ${:.0} / ${:.0} / ${:.0}", volume.h6.unwrap_or(0.0), volume.h1.unwrap_or(0.0), volume.m5.unwrap_or(0.0)));
            }
            if let Some(price_change) = &pair.price_change {
                parts.push(format!("📉 <b>Price Change (24h/6h/1h/5m):</b> {:.2}% / {:.2}% / {:.2}% / {:.2}%", price_change.h24.unwrap_or(0.0), price_change.h6.unwrap_or(0.0), price_change.h1.unwrap_or(0.0), price_change.m5.unwrap_or(0.0)));
            }
            if let Some(created_at) = &pair.pair_created_at {
                parts.push(format!("<b>Created:</b> {}", chrono::DateTime::from_timestamp_millis(*created_at).unwrap().format("%Y-%m-%d %H:%M")));
            }
            if let Some(txns) = &pair.txns {
                if let (Some(h24), Some(h6), Some(h1), Some(m5)) = (&txns.h24, &txns.h6, &txns.h1, &txns.m5) {
                    parts.push("🔄 <b>Transactions</b>".to_string());
                    parts.push(format!("<b>24h:</b> {} buys / {} sells", h24.buys.unwrap_or(0), h24.sells.unwrap_or(0)));
                    parts.push(format!("<b>6h:</b> {} buys / {} sells", h6.buys.unwrap_or(0), h6.sells.unwrap_or(0)));
                    parts.push(format!("<b>1h:</b> {} buys / {} sells", h1.buys.unwrap_or(0), h1.sells.unwrap_or(0)));
                    parts.push(format!("<b>5m:</b> {} buys / {} sells", m5.buys.unwrap_or(0), m5.sells.unwrap_or(0)));
                }
            }
            if let Some(info) = &pair.info {
                if let Some(socials) = &info.socials {
                    let social_links: Vec<String> = socials.iter().filter_map(|s| s.handle.as_ref().map(|h| format!("<a href=\"{}\">{}</a>", h, s.platform.as_deref().unwrap_or("Social")))).collect();
                    if !social_links.is_empty() {
                        parts.push(format!("<b>Socials:</b> {}", social_links.join(" | ")));
                    }
                }
                if let Some(websites) = &info.websites {
                    let website_links: Vec<String> = websites.iter().filter_map(|w| w.url.as_ref().map(|u| format!("<a href=\"{}\">Website</a>", u))).collect();
                    if !website_links.is_empty() {
                        parts.push(format!("<b>Websites:</b> {}", website_links.join(" | ")));
                    }
                }
            }

            parts.push(String::new());
        }
    }

    let ath_market_cap = data.pump_fun_data.as_ref().and_then(|pf| pf.ath_market_cap).unwrap_or(0.0);
    let total_supply_pf = data.pump_fun_data.as_ref().and_then(|pf| pf.total_supply).unwrap_or(0);

    parts.push(format!("🧢 <b>MC (pf):</b> ${:.0}", market_cap));
    parts.push(format!("Market Cap (SOL): {:.2}", data.pump_fun_data.as_ref().and_then(|pf| pf.market_cap).unwrap_or(0.0)));
    parts.push(format!("🔥 <b>ATH (pf):</b> ${:.0}", ath_market_cap));
    parts.push(format!("📦 <b>Supply (pf):</b> {}", total_supply_pf));
    if fdv > 0.0 {
        parts.push(format!("💎 <b>FDV:</b> ${:.0}", fdv));
    }
    if liquidity_usd > 0.0 {
        parts.push(format!("💧 <b>Liq:</b> ${:.0}", liquidity_usd));
    }
    parts.push(String::new());

    // CONSOLIDATED Security & Dev Section
    parts.push("🔒 <b>Security & Dev</b>".to_string());

    // DEX Paid status (repeated here for consolidation)
    parts.push(format!("├ <b>DEX Paid (Dex):</b> {} {} <a href=\"{}\">[info]</a>", dex_paid_dot, dex_paid_status, info_link));

    // Mint/Freeze Authority from Jupiter audit if available
    if let Some(jupiter_data) = &data.jupiter_data {
        if let Some(audit) = &jupiter_data.audit {
            let mint_disabled = audit.mint_authority_disabled.unwrap_or(false);
            let freeze_disabled = audit.freeze_authority_disabled.unwrap_or(false);
            parts.push(format!("├ <b>Mint Authority (Jup):</b> {}", if mint_disabled { "Disabled ✅" } else { "Enabled ⚠️" }));
            parts.push(format!("├ <b>Freeze Authority (Jup):</b> {}", if freeze_disabled { "Disabled ✅" } else { "Enabled ⚠️" }));
        } else {
            parts.push("├ <b>Mint/Freeze Authority:</b> N/A".to_string());
        }
    } else {
        parts.push("├ <b>Mint/Freeze Authority:</b> N/A".to_string());
    }

    // Dev holdings and security info
    if let Some(pf) = &data.pump_fun_data {
        if let Some(creator) = &pf.creator {
            let short_addr = if creator.len() > 12 {
                format!("{}...{}", &creator[..6], &creator[creator.len()-6..])
            } else {
                creator.clone()
            };
            let creator_link = format!("https://solscan.io/account/{}", creator);
            let stats_link = format!("https://t.me/phanes_bot?start=pfdev_{}", creator);
            
            parts.push(format!("└ <b>Dev (pf):</b> <a href=\"{}\">{}</a> <a href=\"{}\">[Stats]</a>", creator_link, short_addr, stats_link));
        } else {
            parts.push("└ <b>Dev:</b> N/A".to_string());
        }
    } else {
        parts.push("└ <b>Dev:</b> N/A".to_string());
    }

    parts.push(String::new());

    // Timestamps (pf)
    if let Some(pf) = &data.pump_fun_data {
        parts.push("🗓️ <b>Timestamps (pf)</b>".to_string());
        if let Some(created_ts) = pf.created_timestamp {
            parts.push(format!("<b>Created:</b> {}", chrono::DateTime::from_timestamp_millis(created_ts).unwrap().format("%Y-%m-%d %H:%M")));
        }
        if let Some(last_trade_ts) = pf.last_trade_timestamp {
            parts.push(format!("<b>Last Trade:</b> {}", chrono::DateTime::from_timestamp_millis(last_trade_ts).unwrap().format("%Y-%m-%d %H:%M")));
        }
        if let Some(ath_ts) = pf.ath_market_cap_timestamp {
            parts.push(format!("<b>ATH Date:</b> {}", chrono::DateTime::from_timestamp_millis(ath_ts).unwrap().format("%Y-%m-%d %H:%M")));
        }
        if let Some(koth_ts) = pf.king_of_the_hill_timestamp {
            if koth_ts > 0 {
                parts.push(format!("<b>King of Hill:</b> {}", chrono::DateTime::from_timestamp_millis(koth_ts).unwrap().format("%Y-%m-%d %H:%M")));
            }
        }
        parts.push(String::new());
    }

    // Engagement (pf)
    if let Some(pf) = &data.pump_fun_data {
        parts.push("💬 <b>Engagement (pf)</b>".to_string());
        let replies = pf.reply_count.unwrap_or(0);
        let participants = pf.num_participants.unwrap_or(0);
        parts.push(format!("Replies: {} | Participants: {}", replies, participants));
        parts.push(String::new());
    }

    // Bonding Curve (pf)
    if let Some(pf) = &data.pump_fun_data {
        parts.push("🎢 <b>Bonding Curve (pf)</b>".to_string());
        let real_sol = pf.real_sol_reserves.unwrap_or(0.0) / 1e9;
        let virtual_sol = pf.virtual_sol_reserves.unwrap_or(0.0) / 1e9;
        let virtual_tokens = pf.virtual_token_reserves.unwrap_or(0.0);
        parts.push(format!("Real SOL: {:.2} | Virtual SOL: {:.2}", real_sol, virtual_sol));
        parts.push(format!("Virtual Tokens: {:.0}", virtual_tokens));
        let real_tokens = pf.real_token_reserves.unwrap_or(0.0);
        parts.push(format!("Real Tokens: {:.0}", real_tokens));
        if let Some(bonding_curve_addr) = &pf.bonding_curve {
            parts.push(format!("Address: <code>{}</code>", bonding_curve_addr));
        }
        if let Some(assoc_bonding_curve) = &pf.associated_bonding_curve {
            parts.push(format!("Assoc. Address: <code>{}</code>", assoc_bonding_curve));
        }
        parts.push(String::new());
    }

    // Status (pf)
    if let Some(pf) = &data.pump_fun_data {
        parts.push("🚦 <b>Status (pf)</b>".to_string());
        let mut status_parts = Vec::new();
        status_parts.push(if pf.is_currently_live.unwrap_or(false) { "🟢 Live" } else { "🔴 Not Live" }.to_string());
        status_parts.push(if pf.complete.unwrap_or(false) { "✅ Complete" } else { "❌ Incomplete" }.to_string());
        if pf.is_banned.unwrap_or(false) { status_parts.push("🚫 Banned".to_string()); }
        if pf.nsfw.unwrap_or(false) { status_parts.push("🔞 NSFW".to_string()); }
        if pf.hidden.unwrap_or(false) { status_parts.push("Hidden".to_string()); }
        if pf.show_name.unwrap_or(false) { status_parts.push("Show Name".to_string()); }
        if pf.inverted.unwrap_or(false) { status_parts.push("Inverted".to_string()); }
        if pf.initialized.unwrap_or(false) { status_parts.push("Initialized".to_string()); }
        parts.push(status_parts.join(" | "));
        parts.push(String::new());
    }

    // System Info (pf)
    if let Some(pf) = &data.pump_fun_data {
        parts.push("⚙️ <b>System Info (pf)</b>".to_string());
        if let Some(prog) = &pf.program { parts.push(format!("Program: {}", prog)); }
        if let Some(plat) = &pf.platform { parts.push(format!("Platform: {}", plat)); }
        if let Some(market) = &pf.market_id { parts.push(format!("Market ID: {}", market)); }
        if let Some(ts) = pf.last_reply { parts.push(format!("Last Reply: {}", chrono::DateTime::from_timestamp_millis(ts).unwrap().format("%Y-%m-%d %H:%M"))); }
        if let Some(ts) = pf.updated_at { parts.push(format!("Updated At: {}", chrono::DateTime::from_timestamp_millis(ts).unwrap().format("%Y-%m-%d %H:%M"))); }
        if pf.hide_banner.unwrap_or(false) { parts.push("Banner Hidden: ✅".to_string()); }
        parts.push(String::new());
    }

    // Livestream (pf)
    if let Some(pf) = &data.pump_fun_data {
        if pf.livestream_ban_expiry.unwrap_or(0) > 0 || pf.livestream_downrank_score.unwrap_or(0.0) > 0.0 {
            parts.push("📺 <b>Livestream (pf)</b>".to_string());
            if pf.livestream_ban_expiry.unwrap_or(0) > 0 {
                parts.push(format!("Ban Expiry: {}", chrono::DateTime::from_timestamp_millis(pf.livestream_ban_expiry.unwrap()).unwrap().format("%Y-%m-%d %H:%M")));
            }
            if pf.livestream_downrank_score.unwrap_or(0.0) > 0.0 {
                parts.push(format!("Downrank Score: {:.2}", pf.livestream_downrank_score.unwrap()));
            }
            parts.push(String::new());
        }
    }

    // Socials
    parts.push("🌐 <b>Socials</b>".to_string());
    if !social_links.is_empty() {
        let social_parts: Vec<String> = social_links.iter().map(|(name, url)| format!("<a href=\"{}\">{}</a>", url.as_ref().unwrap_or(&"".to_string()), name)).collect();
        parts.push(social_parts.join(" | "));
    } else {
        parts.push("No social links found.".to_string());
    }
    parts.push(String::new());

    // Description
    if !description.is_empty() {
        parts.push(format!("📝 {}", html::escape(&description)));
        parts.push(String::new());
    }

    // Jupiter Token Analysis
    if let Some(jup_data) = &data.jupiter_data {
        parts.push(String::new());
        parts.push(format_jupiter_data(jup_data));
    }

    // DexScreener Orders Data - EXPLICIT SECTION
    if let Some(orders_data) = &data.dexscreener_orders_data {
        if !orders_data.is_empty() {
            parts.push(String::new());
            parts.push("📜 <b>DexScreener Orders (Dex)</b>".to_string());
            for order in orders_data {
                let order_type = &order.r#type;
                let order_status = &order.status;
                let payment_date = chrono::DateTime::from_timestamp_millis(order.payment_timestamp)
                    .map(|dt| dt.format("%Y-%m-%d %H:%M").to_string())
                    .unwrap_or_else(|| "N/A".to_string());
                parts.push(format!("  - Type: `{}` | Status: `{}` | Paid: `{}`", order_type, order_status, payment_date));
            }
            parts.push(String::new());
        }
    }

    (parts.join("\n"), image_url)
}
