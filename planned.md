x# Gain Alert Chart Gate Enhancements – Implementation Plan

## Objectives
- Introduce additional guardrails (age, liquidity, volume, stability) before fetching charts for gain alerts.
- Support both global defaults and per-source overrides to fine-tune behaviour.
- Surface configuration and status in the management bot’s Gain Alert Settings UI.
- Add a gain-alert template placeholder for the blockchain (SOL / BSC) so alerts can mention the chain explicitly.

## Six-Phase Implementation Guide

### Phase 1 – Foundations & Config
- [x] Extend `settings` with a `chart_guardrails` JSONB entry capturing global defaults (age, liquidity, volume, multiplier, price stability, checks required).
- [x] Add nullable override columns to `monitored_sources`:
  - `chart_min_age_minutes`
  - `chart_min_liquidity_usd`
  - `chart_min_volume_usd`
  - `chart_min_multiplier`
  - `chart_max_price_change_pct`
  - `chart_checks_required`
- [x] Update config helpers to load/save global guardrail JSON and resolve per-source overrides.

### Phase 2 – Placeholder & Template Readiness
- [x] Enhance placeholder service to surface `chain_code`, liquidity, volume, multiplier, price-change metrics, token age.
- [x] Introduce `{chain}` placeholder in gain alert templates and update default template documentation.
- [x] Ensure fallback handling for tokens lacking specific metrics (return “N/A” but keep pipeline stable).

### Phase 3 – Guardrail Evaluation Logic
- [x] Refactor chart gating (`DexScreenerService`) to gather required metrics per token.
- [x] Enforce market-cap threshold, compute multiplier, and evaluate new checks using global defaults.
- [x] Respect per-source overrides when present, falling back to global values otherwise.
- [x] Implement “N of M” pass logic with detailed logging for failed checks.

### Phase 4 – Global Settings UI/UX
- [x] Add a “📊 Chart Guardrails” block to Gain Alert Settings text.
- [x] Provide edit prompts for each threshold plus strategy selector; validate inputs.
- [x] Persist edits back to `settings` JSON and refresh summary copy.

### Phase 5 – Per-Source Overrides UI

**Sub-Phase 5.1: Display Overrides and UI Scaffolding**
- [x] **Locate Source View Handler:** Identify the `GainAlertsHandler` function for showing a single monitored source's details.
- [x] **Update Data Fetching:** Modify the handler to fetch both the `monitored_source` record and the global `chart_guardrails` settings.
- [x] **Extend UI Text:** Update the message text to include a "📊 Chart Guardrail Overrides" section, displaying the source-specific value or the global default for each metric.
- [x] **Update Keyboard:** Add "Edit" and "Reset" buttons to the keyboard for each guardrail metric.

**Sub-Phase 5.2: Implement Edit/Reset Functionality**
- [x] **Define New State:** Add an `awaiting_source_guardrail_override` state to the `ManagementStates` class.
- [x] **Create "Edit" Handlers:** Implement `prompt_edit_source_guardrail` to ask for user input and `save_source_guardrail` to validate and save the new value.
- [x] **Create "Reset" Handler:** Implement a `reset_source_guardrail` handler to clear the override value (set to `NULL`) in the database.
- [x] **Register New Routes:** Register the new callback query and message handlers in the `gain_alerts` router.

**Sub-Phase 5.3 (Optional): Surface Evaluation Outcome**
- [x] **Database Change:** Add a `last_guardrail_result` column to the `monitored_sources` table.
- [x] **Update Logic:** Modify the guardrail evaluation logic to store its pass/fail results in the new column.
- [x] **Display Result:** Show this result in the monitored source UI for admin visibility.

### Phase 6 – Validation & Rollout
- [ ] Unit tests: config loader, override resolution, `{chain}` placeholder rendering.
- [ ] Functional tests: chart gating scenarios (all pass, single fail, override success, missing data).
- [ ] Manual QA: management UI flows, alert output containing `{chain}`.
- [ ] Prepare operator comms; set lenient default thresholds; consider feature flag during rollout.
