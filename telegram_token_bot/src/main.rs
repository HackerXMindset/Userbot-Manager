use anyhow::Result;
use dotenv::dotenv;
use std::env;

mod api;
mod bot;
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

    // Initialize API client
    let api_client = api::ApiClient::new(api_key).await?;

    // Start Telegram bot
    bot::start_bot(bot_token, api_client).await?;

    Ok(())
}
