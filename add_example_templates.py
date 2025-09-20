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

    templates = [simple_template, detailed_template, quick_template, premium_template]

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