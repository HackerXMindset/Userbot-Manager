# Pump.fun Placeholder Catalogue (Phase 2)

The Rust HTTP endpoint now returns pump.fun token data alongside Dex pairs and orders. The Python `PlaceholderService` exposes every pump.fun field so templates can render pump.fun specific messaging without additional API calls.

## Identity & Metadata
- `pf_mint`
- `pf_name`
- `pf_symbol`
- `pf_description`
- `pf_image_uri`
- `pf_metadata_uri`
- `pf_twitter`
- `pf_telegram`
- `pf_website`

## Bonding Curve & Creator
- `pf_bonding_curve`
- `pf_associated_bonding_curve`
- `pf_creator`
- `pf_creator_short`
- `pf_creator_solscan`
- `pf_creator_stats`

## Time Markers
Each timestamp ships with three placeholders: raw (`*_timestamp`), ISO (`*_timestamp_iso`), and relative (`*_timestamp_ago`).
- `pf_created_timestamp`
- `pf_last_trade_timestamp`
- `pf_ath_market_cap_timestamp`
- `pf_koth_timestamp`
- `pf_livestream_ban_expiry`
- `pf_updated_at`
- `pf_last_reply`
- `pf_thumbnail_updated_at`

## Supply, Caps, and Reserves
- `pf_total_supply`
- `pf_market_cap_sol` (native units)
- `pf_market_cap_usd`
- `pf_ath_market_cap`
- `pf_real_sol_reserves`
- `pf_virtual_sol_reserves`
- `pf_virtual_token_reserves`
- `pf_real_token_reserves`

## Engagement & Participation
- `pf_reply_count`
- `pf_num_participants`

## Lifecycle Flags
(Boolean values render as `Yes` / `No`.)
- `pf_is_currently_live`
- `pf_complete`
- `pf_hidden`
- `pf_show_name`
- `pf_nsfw`
- `pf_inverted`
- `pf_is_banned`
- `pf_initialized`
- `pf_hide_banner`

## Pools & Routing
- `pf_raydium_pool`
- `pf_pump_swap_pool`

## Livestream & Ranking
- `pf_livestream_downrank_score`
- `pf_downrank_score`

## System Metadata
- `pf_program`
- `pf_platform`
- `pf_market_id`
- `pf_banner_uri`
- `pf_thumbnail_uri`
- `pf_video_uri`

## Usage Notes
- All placeholders default to `N/A` when data is missing, so templates can safely reference them without conditionals.
- Timestamps arrive in seconds or milliseconds from the API; the service normalizes them to ISO strings and human-friendly "time ago" values.
- Numeric fields use `format_market_cap`, `format_number`, or `format_int` to keep output readable while preserving raw strings where appropriate.
- Pump.fun data only flows through the Rust HTTP endpoint; if the Rust service returns `pump_fun: null`, the placeholders stay `N/A`.

Update your template text under the pump.fun preset to take advantage of these keys. The legacy pump.fun formatting inside the Rust bot UI can now be replicated entirely inside the Python template system.
