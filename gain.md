# Gain Alert Revamp Plan

This document lays out the exact steps for adding the new market-cap monitoring and gain alert flow requested by the user. Follow each step in order. Every milestone explains *what* to build, *where* the code lives, and *how* the pieces interact so anyone can implement it without guessing.

---

## 0. Goals & Constraints
- First snapshot comes from **Jupiter** when a token is detected.
- Ongoing monitoring uses **DexScreener** with tier-based polling intervals.
- Gain alerts fire on **30 %** jumps over the last alert’s market cap and reply to the original coin message.
- Monitoring stops if the token falls below **70 %** of its first market cap or under **$8 000** absolute.
- Each alert immediately moves the token back to **Tier B**; tier downgrades follow the normal age-based schedule.
- Gain/drop thresholds must be configurable from the existing alert menu; defaults load from the database.
- Operators should see each token’s tier and next poll time from a status view.

---

## 1. Data Model & Settings Prep
1. **Database columns** (migrations/):
   - Add to `tokens_tracked`:
     - `first_seen_at TIMESTAMPTZ DEFAULT NOW()`
     - `first_seen_mc NUMERIC(24,6)` (already present but ensure populated).
     - `last_alert_mc NUMERIC(24,6)` (stores MC that produced the most recent gain alert).
     - `current_tier TEXT` (values: `tier_a` … `tier_f`).
     - `next_poll_at TIMESTAMPTZ` (scheduler uses this).
     - `stop_reason TEXT` (null unless we halt monitoring).
     - `dex_screener_refreshed_at TIMESTAMPTZ` (optional for debugging).
   - Optional: add `original_message_id BIGINT` if not already tracked to support replies.
2. **Settings table seed**:
   - Insert defaults (`gain_threshold_pct=0.30`, `drop_threshold_pct=0.70`, `drop_floor_mc=8000`) via migration if they are not already present.
3. **Pydantic settings** (`app/config.py` or a config helper):
   - Add safe defaults (`gain_threshold_default_pct`, etc.) that read from DB or fall back to constants for bootstrapping.
4. **Model helpers** (`app/models/token.py`):
   - Expose CRUD helpers to update tiers, next poll time, last alert MC, stop reason, and to fetch tokens ordered by `next_poll_at`.

---

## 2. Jupiter Snapshot on Detection
1. **Service wiring**:
   - Instantiate one `JupiterAPIService` (singleton pattern similar to Dex service). Place the accessor in `app/services/__init__.py` or a new `app/services/jupiter.py`.
2. **`TokenMonitor` changes** (`app/userbot/token_monitor.py`):
   - After `dex_service.add_token` succeeds, fetch Jupiter token data (`use_cache=False` on the first call).
   - Parse market cap, price, ticker.
   - Call `TokenModel.update_market_cap` with real numbers.
   - Set `first_seen_mc`, `first_seen_at`, `last_alert_mc=first_seen_mc`, `current_tier='tier_a'`, `next_poll_at=NOW() + 10s`.
   - Handle Jupiter misses (log warning, keep `first_seen_mc=0` but still schedule Tier A to retry).

---

## 3. DexScreener Client
1. Create `app/services/dexscreener_api.py`:
   - Method: `async fetch_token(address: str) -> Optional[DexData]`.
   - Use the REST endpoint: `https://api.dexscreener.com/latest/dex/pairs/solana/{address}`.
   - Parse USD price, FDV/market cap, liquidity.
   - Add retry/backoff helper (respect 429s, network hiccups).
2. Include lightweight caches (≈60 s TTL) to avoid duplicate pulls when multiple consumers ask simultaneously.

---

## 4. Tier Scheduler Architecture
### Tier Rules
| Tier | Age Window | Poll Interval |
| ---- | ---------- | ------------- |
| A | 0–10 min | 10 s |
| B | 10–30 min | 30 s |
| C | 30 min–2 hr | 3 min |
| D | 2–6 hr | 5 min |
| E | 6–24 hr | 10 min |
| F | 1–7 days | 30 min (after 7 days fall back to 1 h or archive) |

### Implementation Steps
1. **Scheduler home**: expand `DexScreenerService` (`app/dex.py`).
   - On `start()`: boot up a background task `self._scheduler_task = asyncio.create_task(self._run_scheduler())`.
   - Maintain an in-memory min-heap keyed by `next_poll_at`.
   - On startup load all active tokens from DB plus their next poll. If missing, calculate using `first_seen_at`.
2. **Run loop** (`_run_scheduler`):
   - While running:
     - Pop any tokens whose `next_poll_at <= now`.
     - Fetch DexScreener data (batch 10–20 tokens per cycle to smooth load).
     - Update token via `TokenModel.update_market_cap` and `update_peak_mc`; store `dex_screener_refreshed_at`.
     - Re-evaluate tier by age and set the next poll time accordingly; write `current_tier` + `next_poll_at` back to DB.
     - For tokens whose tier changed due to age or alert override, mirror the new tier in both queue and DB.
     - Sleep briefly (≈1 s) before checking the heap again.
3. **Alert feedback**:
   - Provide `DexScreenerService.promote_to_tier_b(token_id)` to reset tier/next poll when a gain alert fires.
4. **Stop conditions**:
   - If market cap `<= first_seen_mc * drop_threshold_pct` **or** `<= drop_floor_mc`, mark token `status='stopped'`, set `stop_reason`, remove from heap, and skip rescheduling.

---

## 5. Gain Alert Trigger Flow
1. **Threshold source**:
   - Pull current `gain_threshold_pct` from the settings cache or DB on each evaluation.
2. **Evaluator** (inside scheduler loop or a companion worker):
   - When DexScreener update returns `last_mc`, compare against `last_alert_mc`.
   - If `last_alert_mc == 0`, treat as baseline (no alert yet).
   - Fire alert when `last_mc >= last_alert_mc * (1 + gain_threshold_pct)`.
3. **Alert emission**:
   - Use the existing dispatcher responsible for posting to target groups.
   - Fetch the original message ID for reply (store during detection if not already).
   - Format exactly: `🌙${TICKER} {multiplier:.1f}x | 💹From {old_mc:$,.0f} ↗️ {new_mc:$,.0f} within {elapsed}`.
     - `multiplier = last_mc / first_seen_mc`.
     - `elapsed` uses compact units (`14m`, `3h`, `2d`).
4. **Post-alert bookkeeping**:
   - Update `last_alert_mc = last_mc`.
   - Call `promote_to_tier_b` (sets `current_tier='tier_b'`, `next_poll_at=now+30s`).
   - Log alert event; optionally insert into `token_alert_history`.

---

## 6. Drop / Stop Logic
1. On each DexScreener refresh evaluate:
   - `last_mc <= max(first_seen_mc * drop_threshold_pct, drop_floor_mc)`.
2. If true:
   - `TokenModel.set_status(token_id, 'stopped')`.
   - `TokenModel.set_stop_reason(token_id, 'mc_drop_70'` or `'mc_below_floor')`.
   - Remove from scheduler queue and avoid rescheduling.
   - Do **not** send alerts (per requirements); just log an info entry.
3. Allow re-adding without cooldown: `TokenMonitor` should register the token anew if rediscovered.

---

## 7. Configurable Thresholds via Existing UI
1. Identify the alert menu module (under `app/ui/handlers/`).
2. Add controls for:
   - “Gain alert threshold (%)”.
   - “Stop-loss threshold (%)”.
   - “Minimum market cap ($)”.
3. Persist edits to `settings` table.
4. Ensure `DexScreenerService` reloads thresholds (poll DB periodically or subscribe to an internal event).

---

## 8. Status & Telemetry
1. Extend management bot status command to show:
   - `current_tier`.
   - `next_poll_at` (localized).
   - `last_mc`, `first_seen_mc`, `last_alert_mc`.
   - `dex_screener_refreshed_at`.
   - `stop_reason` for inactive tokens.
2. Group display by tier or allow filtering (e.g., `/dex_status tier_a`).
3. Add structured logging:
   - `INFO` for tier transitions, alerts, stop events.
   - `WARNING` for API errors/backoffs.
   - `DEBUG` toggles for detailed scheduler ops.

---

## 9. Resilience & Backoff
1. Limit concurrent DexScreener requests via `asyncio.Semaphore(5)` or similar.
2. Implement exponential backoff (sleep 5 s → 15 s → 30 s) on HTTP errors/429s and adjust queue scheduling accordingly.
3. Persist `next_poll_at` so restarts resume without reloading all tokens into Tier A.
4. On shutdown cancel scheduler task gracefully and flush any pending updates.

---

## 10. Testing Checklist
1. **Unit Tests**:
   - Mock Jupiter/DexScreener to verify tier assignment, alert math, drop logic, and tier promotion after alert.
   - Ensure scheduler respects tier intervals by simulating time jumps.
2. **Integration Tests**:
   - Use staged Postgres to confirm migrations, DB updates, and status reporting.
   - Run scheduler against mocked HTTP server to simulate rate limits.
3. **Manual QA**:
   - Age sample tokens through tiers; confirm intervals.
   - Trigger gain alert and verify Telegram reply formatting.
   - Force stop-loss conditions; ensure token disappears from active status and logs stop reason.
   - Tweak thresholds via UI and confirm they apply without restart.

---

## Rollout Notes
1. Run new migrations.
2. Restart services so scheduler starts with fresh `next_poll_at`.
3. Monitor logs for rate limiting or missing DexScreener data.
4. Coordinate with operators to populate the alert menu defaults if the migration cannot auto-seed.

---

## Rollout Phases & To‑Do Breakdown

### Phase 1 — Data Foundations
- [ ] Write migration adding new columns to `tokens_tracked` and seeding default thresholds in `settings`.
- [ ] Update `TokenModel` to read/write the new fields (tier, next poll, alert MC, stop reason).
- [ ] Ensure config layer loads gain/drop defaults from DB with fallback constants.

### Phase 2 — Jupiter Snapshot Integration
- [ ] Provide a shared Jupiter service accessor.
- [ ] Extend `TokenMonitor` to call Jupiter on first detection and store initial metrics plus Tier A schedule.
- [ ] Handle missing data paths (retry via scheduler but avoid crashes).

### Phase 3 — DexScreener Client & Scheduler
- [ ] Implement DexScreener REST client with caching and backoff.
- [ ] Rebuild `DexScreenerService` with background scheduler, min-heap queue, and tier evaluation.
- [ ] Persist `current_tier`, `next_poll_at`, and refresh timestamps after each poll.
- [ ] Enforce stop-loss logic and remove halted tokens from the queue.

### Phase 4 — Gain Alert Logic
- [ ] Compare `last_mc` vs `last_alert_mc` using configurable threshold.
- [ ] Format and send alert replies to original coin messages.
- [ ] Update `last_alert_mc` and promote token to Tier B post-alert.
- [ ] Log/record alert events for future auditing.

### Phase 5 — UI & Operator Controls
- [ ] Extend existing alert menu to view/edit thresholds.
- [ ] Wire menu actions to `settings` table updates and notify running services.
- [ ] Add status command showing tier, next poll, and recent MC data.

### Phase 6 — Testing & Hardening
- [ ] Cover tiering/alert logic with unit tests (mocked services).
- [ ] Run integration tests against staged DB and mocked HTTP APIs.
- [ ] Perform manual QA flows: tier aging, gains, drop stops, UI updates, restarts.
- [ ] Tune rate limiting/backoff based on observed behavior.

Follow this phased blueprint exactly and the gain-alert system will behave as specified. If anything unexpected comes up (missing schema, new API errors), document it in this file and adjust before deploying to production.

