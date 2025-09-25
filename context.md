# Project Context
#
# Mission
- Serve all token intelligence through the Rust microservice (`telegram_token_bot`) so the Python automation app uses fresh, uncached data on every run.
- Expose every data point as a placeholder in `PlaceholderService`, letting operators craft pump.fun and non pump.fun templates without code changes.
- Keep legacy Python fetchers only as emergency fallbacks; the Rust bridge now owns DexScreener, pump.fun, Jupiter, and Helius data collection.
#
# Components
- **Rust service (`telegram_token_bot`)**
  - HTTP endpoint `/dex/{mint}` (binds to `RUST_HTTP_ADDR`, default `0.0.0.0:8080`).
  - Payload fields:
    - `pairs`: DexScreener pools
    - `orders`: DexScreener paid orders
    - `pump_fun`: pump.fun metadata
    - `jupiter`: Jupiter token analysis
    - `dev_sol_balance`: SOL balance of the Jupiter dev address (when available)
    - `holders`: Helius `getTokenLargestAccounts` result
    - `supply_ui_amount`: Helius `getTokenSupply` UI amount
- **Python automation app**
  - `app/services/rust_bridge.py` – aiohttp client calling the Rust endpoint.
  - `app/services/placeholder_service.py` – merges Rust payloads with DB context to produce placeholders.
  - `app/services/call_dispatcher.py` – resolves templates and sends messages (now without Telegram parse mode to avoid Markdown issues).
  - `app/ui/handlers/templates.py` – operator UI for template management.
#
# Placeholder Coverage
(All placeholders are plain strings; missing data remains `N/A`.)
#
- **DexScreener**: metadata (`dex_id`, `dex_pair_chain_id`, ...), pricing (`price_usd`, `market_cap`, ...), liquidity, volume/price deltas, transaction counts, info blocks (`dex_info_*`), paid orders (`dex_order_{1..20}_*`), CTO detection (`cto_status`, `cto_time`, `dex_time`), links (`dexscreener_link`, `defined_link`), `bonding_status`, `pair_created_at`.
- **pump.fun (`pf_`)**: identity/media, bonding + creator links, timestamp triples (raw/ISO/ago), economics (supply, reserves, ATH), engagement flags, pool/system metadata (`pf_program`, `pf_market_id`, ...), combined social links (`pf_social`), ATH comparison (`pf_ath_comparison`).
- **Jupiter (`jup_`)**: identity & supply, market metrics, audit/dev info, engagement and social fields, plus interval stats for `5m`, `1h`, `6h`, `24h` (`jup_stats_<tf>_*`).
- **Helius (`helius_`)**: snapshot (`helius_data_slot`, `helius_holder_count`, `helius_holder_total_ui_amount`, `helius_remaining_share`), aggregate shares (`helius_top{1|5|10|20}_*`), per-holder fields for top 20, creator holding stats, and `helius_holder_table` for preformatted output.
- **General helpers**: `token_symbol`, `token_name`, `address`, `multiplier`, `mention_count`, `call_history`, `dexscreener_link`, `defined_link`, `bonding_status`, `pair_created_at`.
#
# Reference Inventories
- `pumpfun_placeholders.md`
- `jupiter_placeholders.md`
- `helius_placeholders.md`
#
# Template Execution Flow
1. Dispatcher pulls a queued call, fetches the assigned template.
2. `PlaceholderService.get_all_placeholders()` calls the Rust endpoint, merges DB fallbacks, and produces placeholder values.
3. Template text is rendered **without** Telegram parse mode (no Markdown parsing).
4. Message is sent via management bot or userbot depending on template settings.
#
# Operational Notes
- Run the Rust service with `cargo run`; build with `cargo build` after code changes. Manage the process via tmux/systemd.
- Required secrets: Helius API key, `PUMP_FUN_JWT`. Missing values degrade placeholders to `N/A` but keep execution safe.
- Python still contains a Dex fallback; disable it if “always fresh” becomes mandatory.
- Management bot occasionally logs “call queue schema outdated” for curated alpha flows—cosmetic warning.
#
# Phase History
- **Phase 1** – Rust bridge + Dex placeholders + `/dex/{mint}` integration.
- **Phase 2** – pump.fun payload/placeholder coverage, reference templates.
- **Phase 3** – Jupiter analytics placeholders (organic score, audit, socials, interval stats) and compact Jupiter template.
- **Phase 4** – Removed Telegram parse mode to avoid Markdown errors.
- **Phase 5** – Integrated Helius holders + supply; exposed creator holdings and aggregate shares.
- **Phase 6** – Added CTO detection (`cto_status`, `cto_time`, `dex_time`), combined social links (`pf_social`), ATH comparison (`pf_ath_comparison`), and fixed type conversion errors in placeholder calculations.
#
# Pending Enhancements
- UI control to switch pump.fun vs generic templates.
- Retries & telemetry in `rust_bridge` for better error surfacing.
- Optional: extend payload with additional Solana analytics if ops requires.
- Automated placeholder tests using fixture payloads.
- Deployment runbook for installing Rust toolchain, managing service lifecycle, and monitoring.
#
# Debug Snippets
- Dump all placeholders:
  ```
python - <<'PY'
from app.services.placeholder_service import PlaceholderService
import asyncio
async def main():
    ps = PlaceholderService('MINT_ADDRESS', {})
    data = await ps.get_all_placeholders()
    for key in sorted(data):
        print(key, ':', data[key])
asyncio.run(main())
PY
  ```
- Inspect raw Rust payload:
  ```
curl http://<server>:8080/dex/<mint>
  ```
#
# This dossier lets future engineers or AI assistants recreate the scanner output purely from templates, extend placeholder coverage, and debug end-to-end without trawling commit history.
