# Gain Alerts UI Overhaul – Phase 1 Snapshot

## 1. Current Screens, Buttons, and Routes

- **Overview / Main Menu** (`app/ui/handlers/gain_alerts.py:31`, `app/ui/keyboards.py:951`)
  - Shows aggregated list of monitored chats with token counts and a “➕ Add Monitored Source” button.
  - Each row links to `gain_alerts:view:<chat_id>` detail view.
  - Footer buttons: `🗑️ Remove Monitored Source`, `🔙 Back` (settings menu).
- **Source Detail View** (`GainAlertsHandler.show_source_detail`)
  - Displays group/channel/DM info, token totals, and monitored user list (for groups).
  - Actions:
    - `➕ Add Monitored User(s)` → `gain_alerts:view:add_users:<chat_id>`
    - `🗑️ Remove <user_id>` → `gain_alerts:view:remove_user:<source_id>`
    - `🗑️ Remove Source` for non-group entries → `gain_alerts:view:remove_source:<source_id>`
    - `🔙 Back` → `gain_alerts:menu`
- **Add Flow**
  - Type selector: `gain_alerts:add:type:<group|channel|dm>`
  - Chat ID prompt: `gain_alerts:cancel` for abort.
  - Group user prompt accepts multiple IDs; confirmation uses `gain_alerts:add:confirm`.
- **Remove Flow**
  - Menu lists each monitored entry via `gain_alerts:remove:select:<source_id>`.
  - Confirmation: `gain_alerts:remove:confirm:<source_id>`.
- **Router Bindings** (`app/ui/routers/gain_alerts.py`)
  - Callback registrations for menu/add/type/view/cancel/confirm/remove.
  - Message handlers for chat ID and user ID input states.

## 2. Fields Needed Per Source

- `chat_id`, `chat_type` (existing)
- `display_name` (friendly label override)
- `is_enabled` (per-source alert toggle)
- `sensitivity_pct` (per-source gain threshold override)
- `assigned_userbot_id` (userbot responsible for posting alerts)
- `target_chat_ids` (list of destination chats/groups for alerts)
- `monitored_user_ids` (existing for groups; maintain add/remove flows)
- Derived stats: token count, last alert timestamp (optional), assigned userbot name.

## 3. Target Flow (High-Level)

1. **Overview** lists every source with status chips (enabled/disabled), sensitivity %, assigned userbot, token count, and entry point to detail view.
2. **Detail View** splits into sections:
   - Status & quick stats (name, chat id, enabled toggle, sensitivity summary).
   - Userbot & Targets (assign bot button, list of destinations with add/remove).
   - Monitored Users (for groups) with add/remove controls.
   - Danger zone (delete source).
3. **Editors** invoked via inline buttons:
   - Rename source, toggle enabled state.
   - Adjust sensitivity (preset buttons + numeric input).
   - Assign or clear userbot (list of available bots).
   - Manage target chats (multi-select, clear, add).
   - Add/remove monitored users via multi-ID input retained from existing flow.
4. **Navigation**: every editor returns to detail view; cancel/back always one step up.

## 4. Style & Copy Guidelines

- Prefix sections with bold emoji headers (e.g., `**🌙 Gain Alerts – Source Detail**`).
- Use short status lines (`Status: ✅ Enabled`, `Sensitivity: +40%`).
- Highlight warnings/destructive actions with `⚠️` and bold text.
- Stick to concise sentences; max two lines per section.
- Buttons should read as actions (“Edit Name”, “Toggle Alerts”, “Assign Userbot”).
- Maintain consistent spacing: blank line between sections, bullet lists for multiple entries.
