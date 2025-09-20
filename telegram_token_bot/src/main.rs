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

    // #COMPLETION_DRIVE: Assuming environment variables are set
    // #SUGGEST_VERIFY: Add validation for required env vars (BOT_TOKEN, API_KEY)

    // Initialize logging
    tracing_subscriber::fmt::init();

    println!("🤖 Starting Telegram Token Bot (Rust version)...");

    // Get environment variables
    let bot_token = env::var("BOT_TOKEN")
        .expect("BOT_TOKEN environment variable must be set");

    let api_key = env::var("HELIUS_API_KEY")
        .expect("HELIUS_API_KEY environment variable must be set");

    // Initialize API client
    let api_client = api::ApiClient::new(api_key).await?;

    // Start Telegram bot
    bot::start_bot(bot_token, api_client).await?;

    Ok(())
}