# Project Context

## Purpose
- Replace Python-based DexScreener fetching with Rust-powered API calls exposed via the `telegram_token_bot` HTTP endpoint.
- Drive all message templates from the new Rust data so operators can configure placeholders for any DexScreener field without manual edits.
- Provide two template modes (pump.fun vs non pump.fun) with fresh, non-cached data every request.

## Current Architecture Snapshot
- `telegram_token_bot` (Rust)
  - Exposes `/dex/{mint}` HTTP endpoint returning DexScreener pairs + paid order history.
  - Bot formatting code (`bot_fixed.rs`) demonstrates full placeholder usage and message layout.
- Python app (`app/`)
  - `PlaceholderService` now queries the Rust endpoint via `rust_dex_bridge.fetch_dex_payload` before falling back to legacy client.
  - Templates managed in the UI/DB use placeholders defined by `PlaceholderService`.
- Template workflow
  1. User selects template (pump.fun or generic) in UI.
  2. App collects placeholders, filling values from Rust payload, DB, and computed helpers.
  3. Template text is rendered and posted.

## Completed Work (Phase 1 – Dex Data Migration)
- Hooked Python placeholder service to Rust HTTP endpoint for Dex pairs + orders.
- Enumerated every DexScreener-derived placeholder (market data, volume, price deltas, txns, liquidity, pair metadata, paid info, websites/socials/boosts, order timelines).
- Delivered a “kitchen-sink” reference template using all placeholders so operators can copy into UI.
- Removed unused UI preview placeholders (Header/OpenGraph/websites/socials/boosts) per latest request.
- Limited Dex paid order placeholders consumed in templates to the first three entries to match product needs.
- Verified HTTP endpoint returns live data (example request against VPS IP showed expected JSON payload).

## Outstanding Work / Next Phases
1. **Pump.fun Specific Template Support**
   - Create dedicated placeholder sets that highlight pump.fun-only fields (bonding curve, livestream, dev stats, timestamps, engagement, status flags).
   - Provide default pump.fun template text mirroring Rust bot formatting but customizable.
   - Ensure template assignment UI allows toggling between pump.fun vs non pump.fun modes.
2. **Jupiter / Advanced Analysis Integration**
   - Map Jupiter token analysis fields (organic score, tags, social metrics, liquidity, price, holders, CEX listings, audit flags, per-interval stats) into placeholder service.
   - Update templates to expose these placeholders and educate operators on usage.
3. **Rust → Python Transport Hardening**
   - Add retries and error surfacing for Rust endpoint failures; avoid silent fallback to stale data if requirements insist on “100% fresh” responses.
   - Consider adding request parameters to explicitly select pump.fun vs non pump.fun template pipelines.
4. **Template Management UX**
   - Pre-load new template examples into DB (`add_example_templates.py`) or via migration so UI users can adopt quickly.
   - Provide inline documentation listing every placeholder and its data source for non-technical operators.
5. **Operational Runbooks**
   - Document how to build and run the Rust service in production (cargo build, systemd or docker instructions) since earlier commands showed missing toolchain on VPS.
   - Clarify deployment endpoints (public IP/port mappings) and how to stop/start the bot cleanly.

## Known Gaps / Open Questions
- Need confirmation on final production base URL/port for exposed Rust HTTP service.
- Clarify caching expectations: current placeholder service still allows fallback to internal client; may need to disable to guarantee “fresh only”.
- Determine storage plan for template variants (per group, per category) once pump.fun segregation is implemented.
- Establish testing strategy for verifying placeholder population (unit tests or integration tests hitting Rust endpoint).

## Immediate Next Actions
1. Extend `PlaceholderService` to include pump.fun fields currently only used inside Rust bot formatting.
2. Produce draft pump.fun and non pump.fun templates in UI using new placeholders.
3. Sync with ops on installing Rust toolchain on VPS (`cargo` missing) and define deployment commands.
4. Update documentation for stopping/starting Telegram bot processes to avoid stale handlers.
