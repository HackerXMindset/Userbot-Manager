import re
import json
import asyncio
import requests
from io import BytesIO
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from s import analyze_token

BOT_TOKEN = "8328427086:AAFNiYaB9xWT9HyayIW_SEImJ8pHoCk9L-s"

def detect_contract_address(text):
    """Detect Solana contract address in text (base58, 32-44 chars)"""
    pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def escape_markdown_v2(text):
    """Escape special characters for MarkdownV2"""
    if not text:
        return text
    # Characters that need escaping in MarkdownV2
    escape_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in escape_chars:
        text = text.replace(char, f'\\{char}')
    return text

def escape_html(text):
    """Escape HTML special characters"""
    if not text:
        return text
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def format_supply(supply):
    """Format supply in shorthand notation"""
    if supply >= 1_000_000_000_000:  # Trillion
        value = supply / 1_000_000_000_000
        return f"{value:.1f}T" if value != int(value) else f"{int(value)}T"
    elif supply >= 1_000_000_000:  # Billion
        value = supply / 1_000_000_000
        return f"{value:.1f}B" if value != int(value) else f"{int(value)}B"
    elif supply >= 1_000_000:  # Million
        value = supply / 1_000_000
        return f"{value:.1f}M" if value != int(value) else f"{int(value)}M"
    else:
        return f"{supply:,}"


def format_token_data(data):
    """Format token data in compact tree structure using HTML format"""
    try:
        ca = data.get('mint_address', 'N/A')
        metadata = data.get('metadata_v1', {})
        asset_data = data.get('asset_data', {}).get('result', {})
        holders_data = data.get('largest_accounts', {}).get('result', {}).get('value', [])
        tx_history = data.get('transaction_history', {}).get('result', [])
        supply_info = data.get('supply_info', {}).get('result', {})
        price_data = data.get('price_data', {})
        creator_balance_data = data.get('creator_balance', {})
        creator_sol_balance_data = data.get('creator_sol_balance', {})
        livestream_data = data.get('livestream_status', {})
        advanced_pump_data = data.get('advanced_pump_analytics', {})

        # Extract data
        name = "Unknown"
        symbol = "N/A"
        description = ""
        decimals = 0
        supply = 0
        image_url = None
        update_authority = ""
        primary_sale = False
        is_mutable = False
        royalty_percent = 0
        price = 0
        fdv = 0
        market_cap = 0

        # Get basic info
        if metadata.get('onChainMetadata', {}).get('metadata'):
            meta = metadata['onChainMetadata']['metadata']
            name = meta['data'].get('name', 'Unknown').strip()
            symbol = meta['data'].get('symbol', 'N/A').strip()
            update_authority = meta.get('updateAuthority', '')
            primary_sale = meta.get('primarySaleHappened', False)
            is_mutable = meta.get('isMutable', False)

        if metadata.get('offChainMetadata', {}).get('metadata'):
            off_meta = metadata['offChainMetadata']['metadata']
            name = off_meta.get('name', name)
            symbol = off_meta.get('symbol', symbol)
            description = off_meta.get('description', '')
            image_url = off_meta.get('image')

        if metadata.get('onChainAccountInfo', {}).get('accountInfo'):
            account_info = metadata['onChainAccountInfo']['accountInfo']['data']['parsed']['info']
            decimals = account_info.get('decimals', 0)
            supply = supply_info.get('value', {}).get('uiAmount', 0)

        if asset_data.get('content', {}).get('links', {}).get('image'):
            image_url = asset_data['content']['links']['image']

        if asset_data.get('royalty'):
            royalty_percent = asset_data['royalty'].get('percent', 0) * 100

        # Price/FDV calculation and additional DexScreener data
        volume_24h = 0
        volume_1h = 0
        price_change_24h = 0
        price_change_1h = 0
        liquidity_usd = 0
        dex_name = "N/A"
        pool_age = "N/A"
        txns_24h_buys = 0
        txns_24h_sells = 0

        if price_data.get('pairs'):
            pair = price_data['pairs'][0] if price_data['pairs'] else {}
            price = float(pair.get('priceUsd', 0))
            market_cap = float(pair.get('marketCap', 0))
            fdv = price * supply if supply > 0 else 0

            # Volume data
            volume_24h = float(pair.get('volume', {}).get('h24', 0))
            volume_1h = float(pair.get('volume', {}).get('h1', 0))

            # Price change data
            price_change_24h = float(pair.get('priceChange', {}).get('h24', 0))
            price_change_1h = float(pair.get('priceChange', {}).get('h1', 0))

            # Liquidity data
            liquidity_usd = float(pair.get('liquidity', {}).get('usd', 0))

            # DEX info
            dex_name = pair.get('dexId', 'N/A')

            # Pool age (created timestamp)
            created_at = pair.get('pairCreatedAt')
            if created_at:
                from datetime import datetime
                try:
                    created_time = datetime.fromtimestamp(created_at / 1000)
                    time_diff = datetime.now() - created_time
                    total_seconds = int(time_diff.total_seconds())

                    if total_seconds < 3600:  # Less than 1 hour
                        minutes = total_seconds // 60
                        pool_age = f"{minutes}m" if minutes > 0 else "<1m"
                    elif total_seconds < 86400:  # Less than 1 day
                        hours = total_seconds // 3600
                        minutes = (total_seconds % 3600) // 60
                        if minutes > 0:
                            pool_age = f"{hours}h {minutes}m"
                        else:
                            pool_age = f"{hours}h"
                    else:  # 1+ days
                        days = time_diff.days
                        hours = (total_seconds % 86400) // 3600
                        if hours > 0 and days < 7:  # Show hours for first week
                            pool_age = f"{days}d {hours}h"
                        else:
                            pool_age = f"{days}d"
                except:
                    pool_age = "N/A"

            # Transaction counts
            txns_24h = pair.get('txns', {}).get('h24', {})
            txns_24h_buys = int(txns_24h.get('buys', 0))
            txns_24h_sells = int(txns_24h.get('sells', 0))

        creators = asset_data.get('creators', [])

        # Extract social links
        social_links = {}
        # Start with Helius metadata
        if metadata.get('offChainMetadata', {}).get('metadata'):
            off_meta = metadata['offChainMetadata']['metadata']
            social_fields = ['twitter', 'discord', 'telegram', 'website', 'github', 'homepage']
            for field in social_fields:
                if off_meta.get(field):
                    social_links[field] = off_meta[field]
        
        # For pump.fun tokens, overwrite with more reliable data from pump APIs
        is_pump_token = 'pump' in ca
        if is_pump_token and advanced_pump_data.get("found"):
            if advanced_pump_data.get('twitter'):
                social_links['twitter'] = advanced_pump_data['twitter']
            if advanced_pump_data.get('telegram'):
                social_links['telegram'] = advanced_pump_data['telegram']
            if advanced_pump_data.get('website'):
                social_links['website'] = advanced_pump_data['website']


        # Format compact message with HTML
        name_esc = escape_html(str(name))
        symbol_esc = escape_html(str(symbol))
        ca_esc = escape_html(str(ca))

        # Create Solscan link for token
        token_link = f"https://solscan.io/token/{ca}"

        # Format price changes with colors
        change_24h_emoji = "🔥" if price_change_24h > 0 else "💀" if price_change_24h < 0 else "😐"
        change_1h_emoji = "🚀" if price_change_1h > 0 else "📉" if price_change_1h < 0 else "😐"

        # Advanced pump.fun analytics (only for pump.fun tokens)
        dex_paid = "❌"
        ath_market_cap = 0
        
        # Data from the new reliable endpoint
        if is_pump_token and advanced_pump_data.get("found"):
            ath_market_cap = advanced_pump_data.get('allTimeHighMarketCap', 0)

            # Check if DEX has paid for enhanced info
            if price_data.get('pairs'):
                pair = price_data['pairs'][0]
                info = pair.get('info', {})
                is_paid = any(key in info for key in ["imageUrl", "header", "openGraph", "websites", "socials"])
                dex_paid = "✅" if is_paid else "❌"
            else:
                dex_paid = "❌"
        
        # Data from the old unreliable endpoint (will be mostly absent now)
        num_holders = advanced_pump_data.get('numHolders')
        sniper_count = advanced_pump_data.get('sniperCount') # Use .get() to avoid KeyError
        sniper_percentage = advanced_pump_data.get('sniperOwnedPercentage')
        twitter_reuse_count = advanced_pump_data.get('twitterReuseCount')
        top_holders_percentage = advanced_pump_data.get('topHoldersPercentage')
        buy_transactions = advanced_pump_data.get('buyTransactions')
        sell_transactions = advanced_pump_data.get('sellTransactions')
        total_transactions = advanced_pump_data.get('transactions')


        formatted = f"""🚀 <b>{name_esc}</b> ({symbol_esc})
└ <a href="{token_link}">{ca_esc}</a>

💰 <b>Market Data</b>
├ Price: {escape_html(f"${price:.8f}" if price > 0 else "N/A")}
├ FDV: {escape_html(f"${fdv:,.0f}" if fdv > 0 else "N/A")}
└ MC: {escape_html(f"${market_cap:,.0f}" if market_cap > 0 else "N/A")} """


        formatted += f"""

📊 <b>Trading Activity</b>
├ Volume (24h): {escape_html(f"${volume_24h:,.0f}" if volume_24h > 0 else "N/A")}
├ Volume (1h): {escape_html(f"${volume_1h:,.0f}" if volume_1h > 0 else "N/A")}
├ {change_24h_emoji} 24h: {escape_html(f"{price_change_24h:+.1f}%" if price_change_24h != 0 else "0.0%")}
└ {change_1h_emoji} 1h: {escape_html(f"{price_change_1h:+.1f}%" if price_change_1h != 0 else "0.0%")} """

        # Conditionally add Risk Assessment and Advanced Market Data if available
        # Note: With the new endpoint, this data is no longer available, so these sections won't be shown.
        # This is better than showing incorrect "0" values.
        if sniper_count is not None:
            formatted += f"""

🔍 <b>Risk Assessment</b>
├ Total Holders: {escape_html(f"{num_holders}" if num_holders is not None else 'N/A')}
├ Snipers: {escape_html(f"{sniper_count}")} wallets ({escape_html(f"{sniper_percentage:.2f}%" if sniper_percentage is not None else 'N/A')})
├ Twitter Reuse: {escape_html(f"{twitter_reuse_count}")} {"🚨" if twitter_reuse_count is not None and twitter_reuse_count > 1 else "✅" if twitter_reuse_count is not None else "N/A"}
└ Top Holders: {escape_html(f"{top_holders_percentage:.1f}%" if top_holders_percentage is not None else 'N/A')} concentration"""

        if ath_market_cap > 0 or buy_transactions is not None:
             formatted += f"""

📊 <b>Advanced Market Data</b>
├ ATH Market Cap: {escape_html(f"${ath_market_cap:,.0f}" if ath_market_cap > 0 else "N/A")} """
             if buy_transactions is not None:
                formatted += f"""
├ Buy/Sell Txns: {escape_html(f"{buy_transactions}B/{sell_transactions}S" if buy_transactions is not None else 'N/A')}
└ Total Txns: {escape_html(f"{total_transactions:,}" if total_transactions is not None else 'N/A')} """


        formatted += f"""

💰 <b>Pool Info</b>
├ Liquidity: {escape_html(f"${liquidity_usd:,.0f}" if liquidity_usd > 0 else "N/A")}
├ DEX Paid: {dex_paid}
├ DEX: {escape_html(dex_name)}
├ Age: {escape_html(pool_age)}
 """

        # Description
        if description:
            formatted += f"\n\n📝 {escape_html(description)}"

        # Holders breakdown
        if holders_data:
            # Get total holders count from pump.fun data if available
            total_holders = num_holders if num_holders is not None else len(holders_data)

            # Calculate top 10 percentage for distribution (excluding liquidity wallet)
            top10_percentages = []
            percentage_links = []
            for holder in holders_data[1:11]:  # Skip first (liquidity), take next 10 for distribution
                ui_amount = holder.get('uiAmount', 0)
                percentage = (ui_amount / supply * 100) if supply > 0 else 0
                address = holder.get('address', 'N/A')

                top10_percentages.append(percentage)
                # Create clickable percentage link
                holder_link = f"https://solscan.io/account/{address}"
                percentage_links.append(f"<a href=\"{holder_link}\">{percentage:.1f}</a>")

            total_top10_percent = sum(top10_percentages)
            percentage_list = "|".join(percentage_links)

            # New header format
            formatted += f"\n\n👥 <b>TH: {total_holders} (total) | Top 10: {total_top10_percent:.1f}%</b>"
            formatted += f"\n └{percentage_list}"

            # Table header
            formatted += f"\n<blockquote expandable>Top 20 in detail"
            formatted += f"\nUser      | %Hold    | Left"

            # Table rows for top 20 (excluding liquidity)
            for i, holder in enumerate(holders_data[1:21], 1):
                address = holder.get('address', 'N/A')
                ui_amount = holder.get('uiAmount', 0)

                short_addr = f"{address[:1]}..{address[-4:]}" if len(address) > 8 else address

                # Calculate percentage holding
                percentage = (ui_amount / supply * 100) if supply > 0 else 0
                percent_str = f"{percentage:.1f}%"

                # Format token amounts
                amount_str = f"{ui_amount/1000000:.1f}M" if ui_amount >= 1000000 else f"{ui_amount/1000:.1f}K"

                # Format row with fixed width columns
                formatted += f"\n{i:<2}.{short_addr:<8} | {percent_str:<8} | {amount_str}"

            formatted += "\n</blockquote>"

        # Social links
        if social_links:
            formatted += f"\n\n🌐 <b>Social Links</b>"

            # Add existing social links from metadata
            if social_links:
                social_emojis = {'twitter': '🐦', 'discord': '💬', 'telegram': '📱', 'website': '🌐', 'github': '💻', 'homepage': '🏠'}
                social_items = list(social_links.items())
                for i, (platform, url) in enumerate(social_items):
                    emoji = social_emojis.get(platform, '🔗')
                    platform_name = platform.capitalize()
                    tree_symbol = "├" if i < len(social_items) - 1 else "└"
                    # Ensure URL is a valid URL
                    if url and 'https://' in url:
                        formatted += f"\n{tree_symbol} {emoji} <a href=\"{url}\">{escape_html(platform_name)}</a>"


        # Security/Creator info
        formatted += f"\n\n🔒 <b>Security & Governance</b>"
        if creators:
            creator = creators[0]
            addr = creator.get('address', 'N/A')
            short_addr = f"{addr[:6]}...{addr[-6:]}" if len(addr) > 12 else addr
            # Create Solscan link for creator
            creator_link = f"https://solscan.io/account/{addr}"

            # Check creator's token balance and SOL balance
            dev_status = ""
            sol_balance_text = ""

            # Use enhanced dev holdings from pump.fun if available, otherwise fallback to Helius data
            dev_holdings_percentage = advanced_pump_data.get('devHoldingsPercentage')
            if is_pump_token and dev_holdings_percentage is not None:
                dev_status = f"🟢 Dev Holding ({dev_holdings_percentage:.1f}%)"
            elif creator_balance_data.get('result', {}).get('value'):
                token_accounts = creator_balance_data['result']['value']
                total_token_balance = 0
                for account in token_accounts:
                    if account.get('account', {}).get('data', {}).get('parsed', {}).get('info'):
                        token_amount = float(account['account']['data']['parsed']['info'].get('tokenAmount', {}).get('uiAmount', 0))
                        total_token_balance += token_amount

                if total_token_balance > 0:
                    token_percentage = (total_token_balance / supply * 100) if supply > 0 else 0
                    dev_status = f"🟢 Dev Holding ({token_percentage:.1f}%)"
                else:
                    dev_status = "🔴 Dev Sold"
            else:
                dev_status = "🔴 Dev Sold"

            # Get creator's SOL balance
            if creator_sol_balance_data.get('result', {}).get('value') is not None:
                sol_lamports = creator_sol_balance_data['result']['value']
                sol_amount = sol_lamports / 1_000_000_000  # Convert lamports to SOL
                sol_balance_text = f" | 💰 {sol_amount:.2f} SOL"

            formatted += f"\n└ Creator: <a href=\"{creator_link}\">{escape_html(short_addr)}</a> | {escape_html(dev_status)}{escape_html(sol_balance_text)}"

        # Livestream status
        if livestream_data:
            is_live = livestream_data.get('is_live', False)
            participants = livestream_data.get('participants', 0)
            replies = livestream_data.get('replies', 0)

            if is_live:
                formatted += f"\n\n📺 <b>Livestream Status</b>"
                formatted += f"\n└ 🟢 Live | 👥 {escape_html(f'{participants:,}')} participants | 💬 {escape_html(f'{replies:,}')} replies"
            elif participants > 0 or replies > 0:  # Was live but now offline
                formatted += f"\n\n📺 <b>Livestream Status</b>"
                formatted += f"\n└ ⚫ Offline | 👥 {escape_html(f'{participants:,}')} participants | 💬 {escape_html(f'{replies:,}')} replies"

        formatted += f"\n\n🔍 <b>MRX Token Analysis Bot</b>"

        return formatted, image_url

    except Exception as e:
        return f"❌ Error formatting data: {str(e)}", None


async def download_and_send_image(update, image_url):
    """Download image and send to Telegram"""
    try:
        response = requests.get(image_url, timeout=10)
        response.raise_for_status()

        # Create BytesIO object from image data
        image_data = BytesIO(response.content)
        image_data.name = 'token_logo.jpg'

        await update.message.reply_photo(photo=image_data)
        return True
    except Exception as e:
        print(f"Error downloading/sending image: {e}")
        return False

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages and detect contract addresses"""
    # Safety checks
    if not update.message or not update.message.text:
        return

    message_text = update.message.text
    chat_id = update.message.chat_id

    # Detect contract address in message
    ca = detect_contract_address(message_text)

    if ca:
        # Send "analyzing" message
        await update.message.reply_text(f"🔍 Analyzing token: `{ca}`", parse_mode='MarkdownV2')

        try:
            # Get token data
            result = analyze_token(ca)

            # Format the data
            formatted_data, image_url = format_token_data(result)

            # Send image first if available
            if image_url:
                image_sent = await download_and_send_image(update, image_url)
                if not image_sent:
                    formatted_data = f"🖼️ *Image:* [View Logo]({image_url})\n\n" + formatted_data

            # Comprehensive debugging
            print("=== DEBUG: Formatted message ===")
            print(formatted_data)
            print("=== END DEBUG ===")

            # Check for unescaped characters
            print("=== MARKDOWN VALIDATION ===")
            problematic_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']

            for i, char in enumerate(formatted_data):
                if char in problematic_chars:
                    # Check if it's properly escaped (preceded by \)
                    if i == 0 or formatted_data[i-1] != '\\':
                        context_start = max(0, i-10)
                        context_end = min(len(formatted_data), i+10)
                        context = formatted_data[context_start:context_end]
                        print(f"❌ UNESCAPED '{char}' at position {i}: ...{context}...")

            # Count specific problem characters
            dot_count = formatted_data.count('.')
            escaped_dot_count = formatted_data.count('\\.')
            unescaped_dots = dot_count - escaped_dot_count

            print(f"Dot analysis: {dot_count} total dots, {escaped_dot_count} escaped, {unescaped_dots} unescaped")
            print("=== END VALIDATION ===")

            # Send formatted message with HTML parsing
            await update.message.reply_text(formatted_data, parse_mode='HTML', disable_web_page_preview=True)

        except Exception as e:
            await update.message.reply_text(f"❌ Error analyzing token: {str(e)}")
    else:
        await update.message.reply_text("🪙 Send me a contract address to analyze token data!")

def main():
    """Start the Telegram bot"""
    print("🤖 Starting Telegram bot...")

    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add message handler
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the bot
    print("✅ Bot is running! Send contract addresses to analyze tokens.")
    application.run_polling()

if __name__ == "__main__":
    main()
