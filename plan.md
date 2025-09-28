# Sensitivity-Based Gain Alerts – Master Implementation Blueprint

This blueprint expands the original plan with explicit substeps, file touchpoints, validation queries, and hand-off notes so that **any** agent—regardless of familiarity with the codebase—can execute it flawlessly. Work must proceed sequentially through the six phases. Each phase contains:

- **Objectives** – what we achieve.
- **Step-by-step tasks** – granular actions, including file names and code pointers.
- **Acceptance checks** – how to verify success before moving forward.
- **Handoff notes** – context the next agent needs.

> 💡 **TIP:** Keep a notebook (or task log) open. After each bullet, jot down the command/file/PR link you touched. Future agents will thank you.

---

## Phase 1 – Database & Model Foundations
**Objectives:** Extend persistence layer to store per-target alert configuration and per-token-per-target alert history.

### Step-by-step tasks
1. **Create Alembic migration** (or raw SQL script if that’s the project standard) named `XXXX_add_target_alert_settings`. Update using `migrations/` folder.
   - Add columns to `targets` table:
     - `alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE`
     - `alerts_modes JSONB NOT NULL DEFAULT '{"pnl": true, "dynamic": true, "threshold": true, "sensitivity": true}'`
     - `alerts_thresholds JSONB NOT NULL DEFAULT '[2,7,25]'`
     - `alerts_sensitivity_percent NUMERIC(6,4) NOT NULL DEFAULT 0.50`
   - Use `ALTER TABLE ...` commands with `IF NOT EXISTS` guards to allow reruns.
   - Immediately `UPDATE targets SET ...` to populate existing rows with defaults.
2. **Create new table `target_token_alert_state`.**
   ```sql
   CREATE TABLE IF NOT EXISTS target_token_alert_state (
       id BIGSERIAL PRIMARY KEY,
       target_id BIGINT REFERENCES targets(id) ON DELETE CASCADE,
       token_id BIGINT REFERENCES tokens_tracked(id) ON DELETE CASCADE,
       first_message_id BIGINT,
       first_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
       initial_market_cap NUMERIC,
       last_alert_multiplier NUMERIC NOT NULL DEFAULT 1,
       last_alert_at TIMESTAMPTZ,
       UNIQUE(target_id, token_id)
   );
   ```
   - Add index on `(token_id)` to accelerate lookups during Dex scans.
3. **Update Python models.**
   - In `app/models/target.py` (or equivalent), expose getters/setters for new columns. Add helper like `parse_alert_modes` returning dict with defaults.
   - Add new DAO/model file `app/models/target_alert_state.py` with CRUD helpers (`get_or_create`, `update_after_alert`, `clear_first_message`).
4. **Document environment defaults.** Update `context.md` tables to list new columns and table. Mention default sensitivity = 50%.

### Acceptance checks
- Run migration locally: `alembic upgrade head` or `psql -f migrations/XXXX.sql`.
- Confirm schema via `\\d targets` and `
SELECT * FROM target_token_alert_state LIMIT 1;` (should show empty result, proving table exists).
- `pytest`/`python -m compileall` to ensure models still import.

**Status: COMPLETE**

### Handoff notes
- Pass along migration filename + SHA to the Phase 2 agent.
- Highlight that defaults must remain in sync with UI (Phase 2 will reference them).

---

## Phase 2 – Target Configuration UX Upgrade
**Objectives:** Allow admins to configure alert behavior per target through management bot.

### Step-by-step tasks
1. **FSM additions.** In `app/ui/states.py`, add states:
   - `target_edit_alert_mode`
   - `target_edit_sensitivity`
   - `target_edit_thresholds`
2. **Keyboard helpers.** In `app/ui/keyboards.py`, add methods:
   - `target_alerts_menu(target)` – shows enabled status, modes, sensitivity, thresholds.
   - `target_alerts_mode_keyboard(target)` – toggles for `/pnl`, `dynamic`, `threshold`, `sensitivity`.
3. **TargetsHandler enhancements (`app/ui/handlers/targets.py`).**
   - When listing targets, append alert summary lines, e.g. `Alerts: ON (pnl✅ dynamic✅ threshold✅ sensitivity✅) S=50% T=[2,7,25]`.
   - Implement callback branches:
     - `targets:alerts_menu:<target_id>` → show config panel.
     - `targets:alerts_toggle:<target_id>:<mode>` to flip booleans within `alerts_modes`.
     - `targets:alerts_enable:<target_id>` to switch master `alerts_enabled`.
     - `targets:alerts_set_sensitivity:<target_id>` – prompt for decimal input; parse and clamp to 0.05–5.00.
     - `targets:alerts_set_thresholds:<target_id>` – prompt for comma-separated numbers; dedupe & sort.
   - Ensure DB updates use JSON operations (`jsonb_set`, etc.) to avoid race conditions.
4. **Input validation.** For thresholds, reject invalid entries with callback answer `❌ Provide numbers like 2,3.5,5`.
5. **Persistence helper.** Add small util to merge defaults when `alerts_modes` is missing keys.

### Acceptance checks
- Use management bot in dev environment: navigate `Menu → Target → {choose target}`.
- Toggle each setting; query DB after each to ensure values changed.
- Validate state transitions (no stuck FSM states, `/cancel` works).

**Status: COMPLETE**

### Handoff notes
- Provide JSON snippet of final target row as example (for Phase 3 agent to mimic in tests).

---

## Phase 3 – Recording First Call & Maintaining Alert State
**Objectives:** Ensure each target+token pair stores baseline data required for sensitivity calculations.

### Step-by-step tasks
1. **Hook into call dispatch.** Identify the module responsible for sending messages to targets (`app/userbot/call_executor.py` or similar).
   - After a call is successfully sent, call new helper `ensure_alert_state(target_id, token_id, message_id, market_cap)`.
   - `market_cap` should come from same data used for template rendering (Dex payload).
2. **Implement helper in new DAO (`app/models/target_alert_state.py`).**
   - `async def ensure_state(target_id, token_id, message_id, initial_mc)` – create row if missing; if exists, only update `first_message_id` when currently NULL.
   - Store `initial_market_cap` if this is first insert.
   - Set `first_sent_at` to existing value (do not overwrite).
3. **Update when message deletion detected (optional but recommended).** If send operation raises `MessageIdInvalidError`, set `first_message_id=NULL` so future alerts send standalone.
4. **Unit tests/mock** – Write tests to cover:
   - New state creation on first call.
   - No duplicate rows on subsequent calls.
   - Graceful handling when message fails.

### Acceptance checks
- Manually trigger a call in dev; inspect `target_token_alert_state` row for message ID and MC.
- Confirm `first_sent_at` aligns with call timestamp.

**Status: COMPLETE**

### Handoff notes
- Provide sample JSON from state table that Phase 4 will rely on.
- Note any test fixtures created.

---

## Phase 4 – Alert Trigger Logic & Delivery
**Objectives:** Extend Dex monitoring loop to respect per-target configuration and send dynamic alerts.

### Step-by-step tasks
1. **Refactor Dex loop (`app/dex.py`).**
   - When evaluating a token update, fetch targets for its `source_group_id` with: `SELECT * FROM targets WHERE group_id=$1 AND alerts_enabled=true`.
   - Load alert state for each target (`target_token_alert_state`). If missing, call `ensure_state` with `message_id=None` and `initial_mc=new_mc` to bootstrap.
2. **Threshold mechanism per target.**
   - Use target’s `alerts_thresholds` if available. Fallback to global `gain_multipliers` only when the target field is null/empty.
   - Track last fired multiplier per target (possible to reuse `last_hit_multiplier` field on token? If not, add separate JSON to state). For simplicity, reuse `target_token_alert_state.last_alert_multiplier_threshold`. If adding column, update migration accordingly.
3. **Sensitivity trigger.**
   - Compute: `target_multiplier = last_alert_multiplier * (1 + sensitivity_percent)`.
   - If `current_multiplier >= target_multiplier`, it’s time to alert.
   - After sending, set `last_alert_multiplier = current_multiplier` and `last_alert_at = NOW()`.
4. **Message generation.**
   - Compose dynamic string using helper function `format_sensitivity_alert(state, token)`. Include: emoji, symbol (`token['ticker']`), `current_multiplier`, `initial_market_cap`, `last_market_cap` etc.
   - Calculate elapsed time via `now - first_sent_at`; format to `Xd yh:zm` style (reuse existing time formatter if present, else write new helper).
5. **Delivery.**
   - Use same userbot that dispatches standard calls: `worker.session_manager.get_client()`.
   - If `first_message_id` exists, send as reply by passing `reply_to=first_message_id`. On `MessageIdInvalidError`, retry without reply and set `first_message_id=NULL`.
   - Log success (`INFO`) and failure (`ERROR`) with target ID, chat ID, multiplier.
6. **No cooldown rule.**
   - Do not implement suppression checks; threshold and sensitivity alerts can both fire in same loop.
7. **Update state.** After each successful send, update `target_token_alert_state` via DAO.

### Acceptance checks
- Simulate MC progression (write small script or modify Dex loop temporarily) to hit multiples: 1.5x → 2x → 3x → 4.5x with sensitivity 50%. Check logs & Telegram channel for alerts at correct checkpoints.
- Ensure `target_token_alert_state` multipliers update accordingly.
- Confirm threshold alert still uses old format or new dynamic format per requirements.

**Status: COMPLETE**

### Handoff notes
- Provide sample log lines + DB snapshots to Phase 5 agent for UI verification.

---

## Phase 5 – Admin UI Refinements & Feedback
**Objectives:** Surface alert configuration clearly and offer quick toggles across management menus.

### Step-by-step tasks
1. **Targets overview enhancements.**
   - In `TargetsHandler.show_targets_menu`, render summary block: `Alerts: ✅ modes[pnl✅ dyn✅ thr✅ sens✅] S=50% T=[2,7,25]`.
   - Highlight disabled state (e.g., `Alerts: ❌ OFF`).
2. **Alerts submenu.**
   - Add new callback `targets:alerts_menu:<target_id>` accessible from each target entry (button text “⚙️ Alerts”).
   - Show current settings with inline buttons for toggles & edits (from Phase 2 keyboards).
3. **Alerts dashboard integration.** In `app/ui/handlers/alerts.py`:
   - Add quick summary counts: number of targets with dynamic alerts on, average sensitivity, etc.
   - Provide button linking to `menu:targets` for per-target management.
4. **Validation & messaging.**
   - After each update, send callback answer `✅ Sensitivity set to 40%` or `❌ Invalid threshold list`.
   - Ensure `/cancel` returns to previous menu gracefully.

### Acceptance checks
- Via management bot, toggle settings for two targets and confirm immediate UI refresh.
- Ensure logs show updates (if logging added).

**Status: COMPLETE**

---

## Phase 6 – Testing, Logging, Documentation, Rollout
**Objectives:** Guarantee quality, update docs, and prep deployment.

### Step-by-step tasks
1. **Automated tests (if test suite exists).**
   - Add tests for new DAO functions (`ensure_state`, `update_after_alert`).
   - Add unit test for `format_sensitivity_alert` (emoji selection, message text, time formatting).
   - Add integration test covering Dex loop -> alert send -> state update using mocks/fakes.
2. **Manual playbook.**
   - Create a `tests/manual/sensitivity_alerts.md` checklist with steps: configure target, simulate MC raises, verify Telegram output, inspect DB state.
3. **Logging audit.**
   - Ensure all new logging statements include token address prefixes and target IDs for easier debugging.
   - Use consistent prefixes (`[SENS_ALERT]`, `[THRESH_ALERT]`).
4. **Documentation updates.**
   - `context.md`: describe new alert types, mention state table, configuration options.  
   - `README.md` or operator guide: add section “Configuring Gain Alerts Per Target” with screenshots or sample commands.
5. **Deployment checklist.**
   - Apply migration on staging/test DB first.  
   - Restart services: Dex monitor, management bot, userbot workers.  
   - Tail logs for 10 minutes (`tail -f runner.log | grep SENS_ALERT`).
6. **Post-deployment validation.**
   - For first live token, confirm state rows created and alerts behave as expected.
   - Record metrics in project tracker (time to first alert, number of alerts fired).

### Acceptance checks
- All tests passing, manual checklist completed, docs merged.
- Production run observed with no errors.

### Final handoff
- Summarize outcomes in release notes: new capabilities, default behavior, config instructions.
- Mark project ticket complete.

---

## Appendix – Reference Snippets & Utilities

- **Emoji selection helper:**
  ```python
  def select_gain_emoji(multiplier: float) -> str:
      if multiplier < 2:
          return "🎉"
      if multiplier < 3:
          return "🔥"
      if multiplier < 5:
          return "🚀"
      if multiplier < 10:
          return "🌙"
      return "🌕"
  ```
- **Time delta formatting:** reuse `format_time_diff` from `b7.py` example if ported; otherwise implement `humanize_timedelta(start, end)` returning `5h:25m`, `10h:14m`, etc.
- **Default configuration JSON:**
  ```json
  {
    "alerts_enabled": true,
    "alerts_modes": {"pnl": true, "dynamic": true, "threshold": true, "sensitivity": true},
    "alerts_thresholds": [2, 7, 25],
    "alerts_sensitivity_percent": 0.5
  }
  ```

Keep this document updated as work progresses. Each agent should annotate the sections they complete (with commit hashes) before handing off to the next.
