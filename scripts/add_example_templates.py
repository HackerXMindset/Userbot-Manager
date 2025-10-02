#!/usr/bin/env python3
"""
Script to add example templates to the database
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.db import db
from app.models.template import TemplateModel


async def add_example_templates():
    """Add the 4 example templates to the database"""

    template_model = TemplateModel(db)

    # Template 1: Simple Call
    simple_template = {
        "name": "🚀 Simple Call",
        "template_text": """🚀 NEW TOKEN ALERT!

💎 {token_name} ({token_symbol})
💰 Market Cap: {market_cap}
📊 24h Volume: {volume_h24}
⏰ Created: {pair_created_at}

🔗 {dexscreener_link}

#crypto #{token_symbol}"""
    }

    # Template 2: Detailed Stats
    detailed_template = {
        "name": "📊 Detailed Stats",
        "template_text": """📊 DETAILED TOKEN ANALYSIS

🔸 {token_name} ({token_symbol})
💰 Price: ${price_usd}
📈 Market Cap: {market_cap}
🚀 ATH: {ath}
⚡ Multiplier: {multiplier}x

📊 24H STATS:
Volume: {volume_h24}
Price Change: {price_change_h24}%
Buys: {txns_h24_buys} | Sells: {txns_h24_sells}

🔗 Analysis: {defined_link}
📱 Chart: {dexscreener_link}

{call_history}"""
    }

    # Template 3: Quick Alert
    quick_template = {
        "name": "⚡ Quick Alert",
        "template_text": """⚡ QUICK ALERT!

{token_symbol} | {market_cap}
📈 {price_change_h24}% (24h)
🔗 {dexscreener_link}"""
    }

    # Template 4: Premium Call
    premium_template = {
        "name": "🎯 Premium Call",
        "template_text": """🎯 PREMIUM TOKEN CALL

✨ {token_name} ({token_symbol})
💎 Current: ${price_usd}
🏆 ATH: {ath}
🚀 Multiplier: {multiplier}x from launch
⏰ Age: {pair_created_at}

📊 TRADING METRICS:
└ Volume (24h): {volume_h24}
└ Change (24h): {price_change_h24}%
└ Liquidity: {liquidity_usd}
└ Status: {bonding_status}

📞 Called {mention_count} times

🔗 RESEARCH:
└ Chart: {dexscreener_link}
└ Data: {defined_link}

⚠️ DYOR - Not Financial Advice"""
    }

    dev_holders_template = {
        "name": "🧑‍💻 Dev + Holders Breakdown",
        "template_text": """🧑‍💻 DEVELOPER SNAPSHOT

👤 Pump.fun Creator: {pf_creator} ({pf_creator_short})
🔗 Creator Solscan: {pf_creator_solscan}
📊 Creator Stats: {pf_creator_stats}

👨‍💻 Jupiter Dev Wallet: <a href=\"https://solscan.io/account/{jup_dev_address}\">{jup_dev_address}</a>
💼 Dev SOL Balance: {jup_dev_sol_balance}
🎯 Dev Holding Indicator: {dev_holdings_indicator}

📦 DEV TOKEN HOLDINGS
• Holding Tokens?: {helius_creator_is_holder}
• Balance (ui): {helius_creator_holding_ui_amount} ({helius_creator_holding_ui_amount_string})
• Raw Amount: {helius_creator_holding_raw_amount}
• % of Sample: {helius_creator_holding_percent_of_sample}%
• % of Supply: {helius_creator_holding_percent_of_supply}%

👥 HOLDERS SNAPSHOT
• Data Slot: {helius_data_slot}
• Holder Count: {helius_holder_count}
• Total UI Amount: {helius_holder_total_ui_amount}
• Remaining Share: {helius_remaining_share}%

🏆 TOP HOLDER AGGREGATES
• Top1: {helius_top1_ui_amount} ({helius_top1_share}%)
• Top5: {helius_top5_ui_amount} ({helius_top5_share}%)
• Top10: {helius_top10_ui_amount} ({helius_top10_share}%)
• Top20: {helius_top20_ui_amount} ({helius_top20_share}%)

🔗 Holder Breakdown: {helius_breakdown_1}|{helius_breakdown_2}|{helius_breakdown_3}|{helius_breakdown_4}|{helius_breakdown_5}|{helius_breakdown_6}|{helius_breakdown_7}|{helius_breakdown_8}|{helius_breakdown_9}|{helius_breakdown_10}

📋 HOLDER SNAPSHOT
User | Holdings | % Supply
{helius_holder_1_user} | {helius_holder_1_balance_short} | {helius_holder_1_percent_short}
{helius_holder_2_user} | {helius_holder_2_balance_short} | {helius_holder_2_percent_short}
{helius_holder_3_user} | {helius_holder_3_balance_short} | {helius_holder_3_percent_short}
{helius_holder_4_user} | {helius_holder_4_balance_short} | {helius_holder_4_percent_short}
{helius_holder_5_user} | {helius_holder_5_balance_short} | {helius_holder_5_percent_short}
{helius_holder_6_user} | {helius_holder_6_balance_short} | {helius_holder_6_percent_short}
{helius_holder_7_user} | {helius_holder_7_balance_short} | {helius_holder_7_percent_short}
{helius_holder_8_user} | {helius_holder_8_balance_short} | {helius_holder_8_percent_short}
{helius_holder_9_user} | {helius_holder_9_balance_short} | {helius_holder_9_percent_short}
{helius_holder_10_user} | {helius_holder_10_balance_short} | {helius_holder_10_percent_short}

1️⃣ {helius_holder_1_short} | {helius_holder_1_ui_amount} | {helius_holder_1_percent_of_supply}% (Sample: {helius_holder_1_percent_of_sample}%)
2️⃣ {helius_holder_2_short} | {helius_holder_2_ui_amount} | {helius_holder_2_percent_of_supply}% (Sample: {helius_holder_2_percent_of_sample}%)
3️⃣ {helius_holder_3_short} | {helius_holder_3_ui_amount} | {helius_holder_3_percent_of_supply}% (Sample: {helius_holder_3_percent_of_sample}%)
4️⃣ {helius_holder_4_short} | {helius_holder_4_ui_amount} | {helius_holder_4_percent_of_supply}% (Sample: {helius_holder_4_percent_of_sample}%)
5️⃣ {helius_holder_5_short} | {helius_holder_5_ui_amount} | {helius_holder_5_percent_of_supply}% (Sample: {helius_holder_5_percent_of_sample}%)
6️⃣ {helius_holder_6_short} | {helius_holder_6_ui_amount} | {helius_holder_6_percent_of_supply}% (Sample: {helius_holder_6_percent_of_sample}%)
7️⃣ {helius_holder_7_short} | {helius_holder_7_ui_amount} | {helius_holder_7_percent_of_supply}% (Sample: {helius_holder_7_percent_of_sample}%)
8️⃣ {helius_holder_8_short} | {helius_holder_8_ui_amount} | {helius_holder_8_percent_of_supply}% (Sample: {helius_holder_8_percent_of_sample}%)
9️⃣ {helius_holder_9_short} | {helius_holder_9_ui_amount} | {helius_holder_9_percent_of_supply}% (Sample: {helius_holder_9_percent_of_sample}%)
🔟 {helius_holder_10_short} | {helius_holder_10_ui_amount} | {helius_holder_10_percent_of_supply}% (Sample: {helius_holder_10_percent_of_sample}%)"""
    }

    templates = [
        simple_template,
        detailed_template,
        quick_template,
        premium_template,
        dev_holders_template,
    ]

    print("Adding example templates to database...")

    for template in templates:
        try:
            # Check if template already exists
            existing = await db.fetchrow(
                "SELECT id FROM post_templates WHERE name = $1",
                template['name']
            )

            if existing:
                print(f"✅ Template '{template['name']}' already exists")
                continue

            # Create the template
            created = await template_model.create(template)
            print(f"✅ Created template: {template['name']} (ID: {created['id']})")

        except Exception as e:
            print(f"❌ Error creating template '{template['name']}': {e}")

    print("\n🎉 Done! Example templates have been added to the database.")
    print("Users can now see these templates in the Templates menu.")


async def main():
    """Main function"""
    try:
        await add_example_templates()
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
