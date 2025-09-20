import re
import json
import asyncio
import aiohttp
import os
from dotenv import load_dotenv
from io import BytesIO
from datetime import datetime
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes
from s import analyze_token

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

def detect_contract_address(text):
    """Detect Solana contract address in text (base58, 32-44 chars)"""
    pattern = r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'
    matches = re.findall(pattern, text)
    return matches[0] if matches else None

def escape_html(text):
    """Escape HTML special characters"""
    if not text:
        return text
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def format_token_data(data):
    """Formats token data into a clean, compact, and structured layout based on user templates."""
    try:
        # --- Data Extraction ---
        ca = data.get('mint_address', 'N/A')
        metadata = data.get('metadata_v1', {})
        asset_data = data.get('asset_data', {}).get('result', {})
        holders_data = data.get('largest_accounts', {}).get('result', {}).get('value', [])
        supply_info = data.get('supply_info', {}).get('result', {})
        price_data = data.get('price_data', {})
        creator_balance_data = data.get('creator_balance', {})
        creator_sol_balance_data = data.get('creator_sol_balance', {})
        livestream_data = data.get('livestream_status', {})
        advanced_pump_data = data.get('advanced_pump_analytics', {})

        # --- Data Processing ---
        name, symbol, description, image_url = "Unknown", "N/A", "", None
        supply, price, fdv, market_cap = 0, 0, 0, 0
        is_mutable = False

        if metadata.get('onChainMetadata', {}).get('metadata'):
            meta = metadata['onChainMetadata']['metadata']
            name = meta['data'].get('name', 'Unknown').strip()
            symbol = meta['data'].get('symbol', 'N/A').strip()
            is_mutable = meta.get('isMutable', False)

        if metadata.get('offChainMetadata', {}).get('metadata'):
            off_meta = metadata['offChainMetadata']['metadata']
            name = off_meta.get('name', name)
            symbol = off_meta.get('symbol', symbol)
            description = off_meta.get('description', '')
            image_url = off_meta.get('image')

        if metadata.get('onChainAccountInfo', {}).get('accountInfo'):
            supply = supply_info.get('value', {}).get('uiAmount', 0)

        if asset_data.get('content', {}).get('links', {}).get('image'):
            image_url = asset_data['content']['links']['image']

        volume_6h, volume_1h, price_change_6h, price_change_1h, liquidity_usd, dex_name, pool_age = 0, 0, 0, 0, 0, "N/A", "N/A"
        ath_market_cap = advanced_pump_data.get('allTimeHighMarketCap', 0)

        if price_data.get('pairs'):
            pair = price_data['pairs'][0]
            price = float(pair.get('priceUsd', 0))
            market_cap = float(pair.get('marketCap', 0))
            fdv = price * supply if supply > 0 else 0
            volume_6h = float(pair.get('volume', {}).get('h6', 0))
            volume_1h = float(pair.get('volume', {}).get('h1', 0))
            price_change_6h = float(pair.get('priceChange', {}).get('h6', 0))
            price_change_1h = float(pair.get('priceChange', {}).get('h1', 0))
            liquidity_usd = float(pair.get('liquidity', {}).get('usd', 0))
            dex_name = pair.get('dexId', 'N/A')
            created_at = pair.get('pairCreatedAt')
            if created_at:
                try:
                    created_time = datetime.fromtimestamp(created_at / 1000)
                    time_diff = datetime.utcnow() - created_time
                    days, seconds = time_diff.days, time_diff.seconds
                    if days > 0: pool_age = f'{days}d'
                    elif seconds >= 3600: pool_age = f'{seconds // 3600}h'
                    else: pool_age = f'{seconds // 60}m'
                except: pool_age = "N/A"

        # --- Formatting ---
        parts = []
        name_esc, symbol_esc, ca_esc = escape_html(name), escape_html(symbol), escape_html(ca)

        # Header
        parts.append(f'🚀 <b>{name_esc} ({symbol_esc})</b>')
        parts.append(f'<code>{ca_esc}</code>')
        parts.append(f'<a href="https://solscan.io/token/{ca}">Solscan</a> | <a href="https://dexscreener.com/solana/{ca}">DexScreener</a> | <a href="https://birdeye.so/token/{ca}?chain=solana">Birdeye</a>')
        parts.append('')

        # Market Data
        parts.append(f'🧢 <b>MC:</b> ${market_cap:,.0f} | 💧 <b>Liq:</b> ${liquidity_usd:,.0f}')
        parts.append(f'💎 <b>FDV:</b> ${fdv:,.0f} | 🔥 <b>ATH:</b> ${ath_market_cap:,.0f}')
        parts.append(f'📊 <b>Vol (6h):</b> ${volume_6h:,.0f} | <b>(1h):</b> ${volume_1h:,.0f}')
        parts.append(f'⏱️ <b>Age:</b> {pool_age}')
        parts.append('')

        # Price Change
        change_1h_emoji = "🚀" if price_change_1h > 0 else "📉" if price_change_1h < 0 else "😐"
        change_6h_emoji = "🔥" if price_change_6h > 0 else "💀" if price_change_6h < 0 else "😐"
        parts.append(f'📉 <b>Price Change (1h/6h)</b>')
        parts.append(f'{change_1h_emoji} {price_change_1h:+.1f}% / {change_6h_emoji} {price_change_6h:+.1f}%')
        parts.append('')

        # Holders
        num_holders = advanced_pump_data.get('numHolders')
        total_holders = num_holders if num_holders is not None else len(holders_data)
        top10_holders_data = holders_data[:10]
        top10_dist_percent = [ (h.get('uiAmount', 0) / supply * 100) for h in top10_holders_data ]
        top10_sum = sum(top10_dist_percent)
        parts.append(f'👥 <b>Holders:</b> {total_holders} | <b>Top 10:</b> {top10_sum:.1f}%')
        parts.append('')

        # Security & Dev
        parts.append('🔒 <b>Security & Dev</b>')

        sniper_count = advanced_pump_data.get('sniperCount')
        if sniper_count is not None:
            sniper_percentage = advanced_pump_data.get('sniperOwnedPercentage', 0)
            parts.append(f"⚠️ <b>Risk:</b> Snipers: {sniper_count} ({sniper_percentage:.2f}%)")

        creators = asset_data.get('creators', [])
        if creators:
            addr = creators[0].get('address', 'N/A')
            creator_link = f"https://solscan.io/account/{addr}"
            short_addr = f'{addr[:6]}...{addr[-6:]}' if len(addr) > 12 else addr
            stats_link = f"https://t.me/phanes_bot?start=pfdev_{addr}"
            
            dev_status, dev_dot, sol_balance_text = "N/A", "", ""
            dev_holdings_percentage = advanced_pump_data.get('devHoldingsPercentage')
            
            holding_percentage = -1
            if 'pump' in ca and dev_holdings_percentage is not None:
                holding_percentage = dev_holdings_percentage
            elif creator_balance_data.get('result', {}).get('value'):
                token_accounts = creator_balance_data['result']['value']
                total_bal = sum(float(acc['account']['data']['parsed']['info'].get('tokenAmount', {}).get('uiAmount', 0)) for acc in token_accounts)
                if total_bal > 0:
                    holding_percentage = (total_bal / supply * 100) if supply > 0 else 0
                else:
                    holding_percentage = 0
            
            if holding_percentage > 0:
                dev_status = f"holding {holding_percentage:.1f}%"
                dev_dot = "🔴"
            elif holding_percentage == 0:
                dev_status = "Sold"
                dev_dot = "🟢"

            sol_balance_str = ""
            if creator_sol_balance_data.get('result', {}).get('value') is not None:
                sol_lamports = creator_sol_balance_data['result']['value']
                sol_balance_str = f'| <b>Balance:</b> {(sol_lamports / 1_000_000_000):.2f} SOL'

            parts.append(f'🧑‍💻 <b>Dev:</b> <a href="{creator_link}">{escape_html(short_addr)}</a> {dev_dot} ({escape_html(dev_status)}) <a href="{stats_link}">[Stats]</a> {sol_balance_str}')

        dex_paid_dot = "🔴"
        if price_data.get('pairs') and price_data['pairs'][0].get('info', {}):
            dex_paid_dot = "🟢"
        info_link = f"https://t.me/phanespurplebot?start=dp_{ca}"
        parts.append(f'├ <b>DEX:</b> {escape_html(dex_name)} | <b>DEX Paid:</b> {dex_paid_dot} <a href="{info_link}">[info]</a>')
        
        parts.append(f'🔧 <b>Mutable:</b> {"✅" if is_mutable else "❌"}')
        parts.append('')

        # Socials
        parts.append("🌐 <b>Socials</b>")
        social_links = {}
        if metadata.get('offChainMetadata', {}).get('metadata'):
            off_meta = metadata['offChainMetadata']['metadata']
            for field in ['twitter', 'telegram', 'website']:
                if off_meta.get(field): social_links[field] = off_meta[field]
        if advanced_pump_data.get("found"):
            if advanced_pump_data.get('twitter'): social_links['twitter'] = advanced_pump_data['twitter']
            if advanced_pump_data.get('telegram'): social_links['telegram'] = advanced_pump_data['telegram']
            if advanced_pump_data.get('website'): social_links['website'] = advanced_pump_data['website']

        social_parts = []
        if social_links.get('twitter'): social_parts.append(f'<a href="{social_links["twitter"]}">X/Twitter</a>')
        if social_links.get('telegram'): social_parts.append(f'<a href="{social_links["telegram"]}">Telegram</a>')
        if social_links.get('website'): social_parts.append(f'<a href="{social_links["website"]}">Website</a>')
        
        if social_parts:
            parts.append(" | ".join(social_parts))
        else:
            parts.append("No social links found.")

        twitter_reuse_count = advanced_pump_data.get('twitterReuseCount')
        if twitter_reuse_count is not None:
            parts.append(f"<b>Twitter Reuse:</b> {twitter_reuse_count}")
        parts.append('')

        # Livestream Status
        if livestream_data and livestream_data.get('is_live'):
            participants = livestream_data.get('participants', 0)
            replies = livestream_data.get('replies', 0)
            parts.append("📺 <b>Livestream Status</b>")
            parts.append(f"└ 🟢 Live | 👥 {participants:,} participants | 💬 {replies:,} replies")
            parts.append('')

        # Description
        if description:
            parts.append(f"📝 {escape_html(description)}")
            parts.append('')

        # Holder Table
        if holders_data:
            dist_links = [f'<a href="https://solscan.io/account/{h.get("address")}">{p:.1f}</a>' for h, p in zip(top10_holders_data, top10_dist_percent)]
            parts.append(f'<code>{"|".join(dist_links)}</code>')

            table_parts = ["<b>Top 10 Holders</b>", "<code>User      | %Hold    | Amount", "---------------------------"]
            for i, holder in enumerate(top10_holders_data, 1):
                address = holder.get('address', 'N/A')
                ui_amount = holder.get('uiAmount', 0)
                short_addr = f'{address[:4]}..{address[-4:]}' if len(address) > 8 else address
                percentage = (ui_amount / supply * 100) if supply > 0 else 0
                amount_str = f'{ui_amount/1000000:.1f}M' if ui_amount >= 1000000 else f'{ui_amount/1000:.1f}K'
                table_parts.append(f'{i:<2}.{short_addr:<8} | {percentage:<7.2f}% | {amount_str}')
            table_parts.append("</code>")
            table_content = "\n".join(table_parts)
            parts.append(f'<blockquote expandable>{table_content}</blockquote>')

        return "\n".join(parts), image_url

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return f"❌ Error formatting data: {str(e)}", None


async def download_and_send_image(update, image_url):
    """Download image and send to Telegram"""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(image_url, timeout=20) as response: # Increased timeout
                response.raise_for_status()
                image_data = BytesIO(await response.read())
                image_data.name = 'token_logo.jpg'
                await update.message.reply_photo(photo=image_data)
                return True
        except Exception as e:
            print(f"Error downloading/sending image: {e}")
            return False

async def process_analysis(update: Update, ca: str):
    """Process the token analysis and send the result."""
    try:
        result = await analyze_token(ca)
        formatted_data, image_url = format_token_data(result)

        if image_url:
            image_sent = await download_and_send_image(update, image_url)
            if not image_sent:
                # If image fails, add a link to the text message
                formatted_data = f'<a href="{image_url}">🖼️</a>\n{formatted_data}'

        await update.message.reply_text(formatted_data, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        await update.message.reply_text(f"❌ Error analyzing token: {str(e)}")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages, analyze token, and send a single message with image and caption."""
    if not update.message or not update.message.text:
        return

    ca = detect_contract_address(update.message.text)
    if not ca:
        await update.message.reply_text("🪙 Send me a contract address to analyze token data!")
        return

    await update.message.reply_text(f"🔍 Analyzing token: `{ca}`", parse_mode='MarkdownV2')

    # Run the analysis in the background
    asyncio.create_task(process_analysis(update, ca))

def main():
    """Start the Telegram bot"""
    if not BOT_TOKEN:
        print("❌ BOT_TOKEN not found. Please set it in your .env file.")
        return

    print("🤖 Starting Telegram bot...")
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot is running! Send contract addresses to analyze tokens.")
    application.run_polling()

if __name__ == "__main__":
    main()
