# Telegram Token Analysis Bot

A comprehensive Solana token analysis bot for Telegram with clickable Solscan links.

## Files

- **`telegram_bot.py`** - Main Telegram bot with HTML formatting and clickable links
- **`s.py`** - Token analysis functions using Helius APIs and DexScreener

## Features

- 🔗 **Clickable Solscan links** for all wallet addresses and transactions
- 📊 **Complete token analysis** using multiple Helius API endpoints
- 💰 **Price & FDV data** from DexScreener API
- 👥 **Holder breakdown** with percentages and amounts
- 🌐 **Social links** extraction from metadata
- 📈 **Recent transaction activity**
- 🔒 **Security & governance** information

## Setup

1. Install dependencies:
```bash
pip install python-telegram-bot requests
```

2. Update bot token in `telegram_bot.py`:
```python
BOT_TOKEN = "your_bot_token_here"
```

3. Update Helius API key in `s.py`:
```python
API_KEY = "your_helius_api_key_here"
```

## Usage

### Run Telegram Bot
```bash
python telegram_bot.py
```

### Run CLI Analysis
```bash
python s.py
```

## API Endpoints Used

- **Helius APIs**: queryMetadataV1, getTokenLargestAccounts, getAsset, getTransactionHistory, getTokenSupply, getAccountInfo
- **DexScreener API**: Token price and market data

## Output Format

The bot provides beautifully formatted token analysis with:
- HTML formatted text with bold headers
- Clickable wallet addresses linking to Solscan
- Market data (price, FDV, market cap)
- Complete holder breakdown with percentages
- Social media links
- Recent transaction activity
- Security and governance information

All wallet addresses, transaction signatures, and token contracts are clickable links to Solscan for easy blockchain exploration.

## Bot Commands

Simply send any Solana token contract address to the bot and it will automatically:
1. Detect the contract address
2. Fetch comprehensive token data
3. Display formatted analysis with clickable links

## Example Output

```
motion (motion)
DVLd349zCzrSHxWGQrut46f1EffwHoaiwqQVyjixpump

💰 Market Data
📊 Price: $0.00012120
💎 FDV: $121,200
📈 MC: $121,206

⚙️ Token Info
🔢 Supply: 999,999,922,784,307
🔸 Decimals: 6
🔒 Mutable: ❌

👥 Holders Analysis
Distribution: 20.0%|3.4%|3.1% [Sum: 40.5%]

Top 10 Details:
1. B5..ktrV: 199.7M (20.0%) [clickable]
2. EK..ccHE: 34.0M (3.4%) [clickable]
...

🔒 Security & Governance
Creator: 9CRdct...8JGbCe (100% ❌) [clickable]
Authority: TSLvdd...t1eokM [clickable]
```

## Notes

- All wallet addresses are automatically converted to clickable Solscan links
- Bot supports HTML parsing for proper link formatting
- Comprehensive debugging included for troubleshooting
- Rate limiting and error handling built-in