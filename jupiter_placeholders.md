# Jupiter Placeholder Catalogue (Phase 3)

The Rust HTTP payload now exposes Jupiter token data (`jupiter`) plus the developer SOL balance, and the Python placeholder service maps everything into `jup_*` placeholders.

## Identity & Metadata
- `jup_id`
- `jup_name`
- `jup_symbol`
- `jup_icon`
- `jup_decimals`
- `jup_token_program`
- `jup_launchpad`
- `jup_first_pool_id`
- `jup_first_pool_created_at`
- `jup_graduated_pool`
- `jup_graduated_at`
- `jup_updated_at`

## Supply & Market Metrics
- `jup_circ_supply`
- `jup_total_supply`
- `jup_usd_price`
- `jup_mcap`
- `jup_fdv`
- `jup_liquidity`
- `jup_bonding_curve`
- `jup_price_block_id`
- `jup_holder_count`

## Verification & Audit
- `jup_is_verified`
- `jup_audit_mint_authority_disabled`
- `jup_audit_freeze_authority_disabled`
- `jup_audit_top_holders_pct`
- `jup_audit_snipers_pct`
- `jup_audit_dev_migrations`
- `jup_audit_dev_balance_pct`

## Dev Information
- `jup_dev_address`
- `jup_dev_sol_balance`

## Engagement & Social
- `jup_organic_score`
- `jup_organic_score_label`
- `jup_tags`
- `jup_ct_likes`
- `jup_smart_ct_likes`
- `jup_twitter`
- `jup_telegram`
- `jup_website`
- `jup_cexes`

## Interval Stats
For each timeframe (`5m`, `1h`, `6h`, `24h`):
- `jup_stats_<tf>_price_change`
- `jup_stats_<tf>_holder_change`
- `jup_stats_<tf>_liquidity_change`
- `jup_stats_<tf>_volume_change`
- `jup_stats_<tf>_buy_volume`
- `jup_stats_<tf>_sell_volume`
- `jup_stats_<tf>_buy_organic_volume`
- `jup_stats_<tf>_sell_organic_volume`
- `jup_stats_<tf>_num_buys`
- `jup_stats_<tf>_num_sells`
- `jup_stats_<tf>_num_traders`
- `jup_stats_<tf>_num_organic_buyers`
- `jup_stats_<tf>_num_net_buyers`

## Formatting Notes
- Floats/percentages are formatted via `format_number`; large values use `format_market_cap`; counts rely on `format_int`.
- Tags and CEX listings join lists with commas; empty sequences default to `N/A`.
- Audit booleans leverage `format_bool` so templates show `Yes/No` (or `N/A` when unknown).
- `jup_dev_sol_balance` comes from the Rust bridge’s SOL balance call; if unavailable, it stays `N/A`.

Use these placeholders alongside the Dex and pump.fun sets to recreate the scanner’s Jupiter sections in templates.
