<feature>
  - Per-target alert toggles must be configurable from the management bot. Navigate: Main Menu → 🎯 Targets → pick a group.
  - For each target channel define:
    • `receive_gain_alerts` (standard /pnl gain alert)
    • `receive_ultimate_alerts` (long-form “ultimate” alert feed)
    • `gain_alert_sensitivity` (Off → +25% → +50% → +100% gain since last alert).
  - UI requirements: when viewing a group, include a “🎯 Targets” button that lists that group’s targets with their current settings and lets an admin toggle each option in-place.
  - Persist settings in the `targets` table (defaults: gain true, ultimate false, sensitivity null) and ensure Dex gain-alert dispatch only sends to targets where `receive_gain_alerts` is true.
</feature>

<future_work>
  - Implement “ultimate” gain alert rendering and submission.
  - Add sensitivity-based triggering and Jupiter MC verification before alerts send.
  - Only proceed with future items after the owner approves a detailed plan for each.
</future_work>

<guidelines>
  - Implement one feature at a time; produce a plan, await approval, then execute.
  - Ask for clarification if any requirement is ambiguous.
</guidelines>
