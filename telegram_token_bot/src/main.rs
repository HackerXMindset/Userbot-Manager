use std::env;
use std::sync::Arc;

use anyhow::Result;
use dotenv::dotenv;
use tokio::{signal, sync::watch};
use tracing::info;

mod api;
mod bot;
mod http_server;
mod social;
mod types;

#[tokio::main]
async fn main() -> Result<()> {
    // Load environment variables from .env file
    dotenv().ok();

    // Initialize logging
    tracing_subscriber::fmt::init();

    println!("🤖 Starting Telegram Token Bot (Rust version)...");

    // Get environment variables and validate them
    let bot_token = env::var("BOT_TOKEN").map_err(|_| {
        anyhow::anyhow!("❌ FATAL: BOT_TOKEN environment variable not set. Please create a .env file and add it.")
    })?;

    let api_key = env::var("HELIUS_API_KEY").map_err(|_| {
        anyhow::anyhow!("❌ FATAL: HELIUS_API_KEY environment variable not set. Please create a .env file and add it.")
    })?;

    let api_client = Arc::new(api::ApiClient::new(api_key).await?);

    let (shutdown_tx, shutdown_rx) = watch::channel(false);

    // HTTP server task
    let http_api = Arc::clone(&api_client);
    let http_handle =
        tokio::spawn(async move { http_server::run_http_server(http_api, shutdown_rx).await });

    // Telegram bot task
    let bot_api = Arc::clone(&api_client);
    let shutdown_for_bot = shutdown_tx.clone();
    let bot_shutdown_rx = shutdown_for_bot.subscribe();
    let bot_handle = tokio::spawn(async move {
        let res = bot::start_bot(bot_token, bot_api, bot_shutdown_rx).await;
        let _ = shutdown_for_bot.send(true);
        res
    });

    // Ctrl+C handler
    let shutdown_for_signal = shutdown_tx.clone();
    tokio::spawn(async move {
        if signal::ctrl_c().await.is_ok() {
            info!("Ctrl+C received, initiating shutdown...");
            let _ = shutdown_for_signal.send(true);
        }
    });

    drop(shutdown_tx);

    let (bot_res, http_res) = tokio::try_join!(bot_handle, http_handle)?;

    bot_res?;
    http_res?;

    Ok(())
}
