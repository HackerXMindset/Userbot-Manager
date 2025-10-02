
import asyncio
import logging
from app.db import db
from app.models.template import TemplateModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# The complete template string
TEMPLATE_NAME = "Complete Jupiter"
TEMPLATE_TEXT = """<pre>
🧿 JUPITER DEEP DIVE: {jup_name} ({jup_symbol}) 🧿
Icon: {jup_icon}
ID: {jup_id}

Core Info
- Price: ${jup_usd_price}
- MCAP: {jup_mcap} | FDV: {jup_fdv}
- Liquidity: {jup_liquidity}
- Holders: {jup_holder_count}

Tokenomics & Pools
- Supply: {jup_circ_supply} / {jup_total_supply}
- Decimals: {jup_decimals} | Program: {jup_token_program}
- Launchpad: {jup_launchpad} | Bonding: {jup_bonding_curve}%
- First Pool: {jup_first_pool_id} ({jup_first_pool_created_at})
- Graduated: {jup_graduated_pool} ({jup_graduated_at})

Social & Engagement
- Organic Score: {jup_organic_score} ({jup_organic_score_label})
- Tags: {jup_tags}
- CEXes: {jup_cexes}
- CT Likes: {jup_ct_likes} | Smart: {jup_smart_ct_likes}
- Links: <a href="{jup_website}">Website</a> | <a href="{jup_twitter}">Twitter</a> | <a href="{jup_telegram}">Telegram</a>

Audit & Dev
- Verified: {jup_is_verified}
- Mint/Freeze Disabled: {jup_audit_mint_authority_disabled}/{jup_audit_freeze_authority_disabled}
- Top Holder %: {jup_audit_top_holders_pct} | Snipers %: {jup_audit_snipers_pct}
- Dev: {jup_dev_address} ({jup_dev_sol_balance} SOL)
- Dev Migrations: {jup_audit_dev_migrations}

📊 JUPITER STATS (Updated: {jup_updated_at})

--- 5m Stats ---
Price Δ: {jup_stats_5m_price_change}% | Holder Δ: {jup_stats_5m_holder_change}%
Liq Δ: {jup_stats_5m_liquidity_change}% | Vol Δ: {jup_stats_5m_volume_change}%
Volume (Buy/Sell): {jup_stats_5m_buy_volume} / {jup_stats_5m_sell_volume}
Organic Vol (B/S): {jup_stats_5m_buy_organic_volume} / {jup_stats_5m_sell_organic_volume}
Trades (B/S): {jup_stats_5m_num_buys} / {jup_stats_5m_num_sells}
Traders: {jup_stats_5m_num_traders} | Org. Buyers: {jup_stats_5m_num_organic_buyers} | Net Buyers: {jup_stats_5m_num_net_buyers}

--- 1h Stats ---
Price Δ: {jup_stats_1h_price_change}% | Holder Δ: {jup_stats_1h_holder_change}%
Liq Δ: {jup_stats_1h_liquidity_change}% | Vol Δ: {jup_stats_1h_volume_change}%
Volume (Buy/Sell): {jup_stats_1h_buy_volume} / {jup_stats_1h_sell_volume}
Organic Vol (B/S): {jup_stats_1h_buy_organic_volume} / {jup_stats_1h_sell_organic_volume}
Trades (B/S): {jup_stats_1h_num_buys} / {jup_stats_1h_num_sells}
Traders: {jup_stats_1h_num_traders} | Org. Buyers: {jup_stats_1h_num_organic_buyers} | Net Buyers: {jup_stats_1h_num_net_buyers}

--- 6h Stats ---
Price Δ: {jup_stats_6h_price_change}% | Holder Δ: {jup_stats_6h_holder_change}%
Liq Δ: {jup_stats_6h_liquidity_change}% | Vol Δ: {jup_stats_6h_volume_change}%
Volume (Buy/Sell): {jup_stats_6h_buy_volume} / {jup_stats_6h_sell_volume}
Organic Vol (B/S): {jup_stats_6h_buy_organic_volume} / {jup_stats_6h_sell_organic_volume}
Trades (B/S): {jup_stats_6h_num_buys} / {jup_stats_6h_num_sells}
Traders: {jup_stats_6h_num_traders} | Org. Buyers: {jup_stats_6h_num_organic_buyers} | Net Buyers: {jup_stats_6h_num_net_buyers}

--- 24h Stats ---
Price Δ: {jup_stats_24h_price_change}% | Holder Δ: {jup_stats_24h_holder_change}%
Liq Δ: {jup_stats_24h_liquidity_change}% | Vol Δ: {jup_stats_24h_volume_change}%
Volume (Buy/Sell): {jup_stats_24h_buy_volume} / {jup_stats_24h_sell_volume}
Organic Vol (B/S): {jup_stats_24h_buy_organic_volume} / {jup_stats_24h_sell_organic_volume}
Trades (B/S): {jup_stats_24h_num_buys} / {jup_stats_24h_num_sells}
Traders: {jup_stats_24h_num_traders} | Org. Buyers: {jup_stats_24h_num_organic_buyers} | Net Buyers: {jup_stats_24h_num_net_buyers}
</pre>"""

async def main():
    """Connects to the database and adds or updates the template."""
    try:
        await db.connect()
        template_model = TemplateModel(db)

        # Check if a template with the same name already exists
        existing_template = await template_model.db.fetchrow(
            "SELECT id FROM post_templates WHERE name = $1", TEMPLATE_NAME
        )

        if existing_template:
            logger.info(f"Template '{TEMPLATE_NAME}' already exists. Updating its content.")
            await template_model.update(existing_template['id'], {"template_text": TEMPLATE_TEXT})
            logger.info("Template updated successfully.")
        else:
            logger.info(f"Creating new template: '{TEMPLATE_NAME}'.")
            await template_model.create({
                "name": TEMPLATE_NAME,
                "template_text": TEMPLATE_TEXT
            })
            logger.info("Template created successfully.")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
    finally:
        if db.pool:
            await db.disconnect()
            logger.info("Database connection closed.")

if __name__ == "__main__":
    # Ensure the script can be run from the project root
    import sys
    from pathlib import Path
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))
    
    asyncio.run(main())
