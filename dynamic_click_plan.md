# Dynamic Click Implementation Plan

## ✅ STATUS: FULLY IMPLEMENTED + ENHANCED

**Original Implementation:** Complete ✅
**Additional Features:** Custom names, enhanced debugging, improved UI ✅
**Last Updated:** 2025-01-XX

---

## Overview
Add "Dynamic Click" feature to auto_click menu. This allows monitoring specific users in specific chats and clicking buttons that match a configured list.

## Requirements
- **Target:** Specific chat_id + specific user_id ✅
- **Buttons:** Multiple button texts (comma-separated input), exact match only ✅
- **Behavior:** Click ALL matching buttons sequentially with 1 second delay ✅
- **Userbot:** User selects which userbot(s) perform the clicks ✅ (Enhanced: multi-userbot support)
- **Coexistence:** Old auto_click (static/CA-based) remains untouched ✅
- **Multiple Rules:** Can have multiple dynamic rules for same chat+user ✅

---

## Implementation Steps

### 1. Database Migration ✅ COMPLETED
**Files:**
- `migrations/046_add_dynamic_click_support.sql` ✅
- `migrations/049_multi_userbot_dynamic_clicks.sql` ✅ (Enhanced)

**Changes:**
- Add `rule_type` TEXT column to `auto_button_click_rules` (default 'static') ✅
  - Values: 'static' (old behavior) or 'dynamic' (new behavior)
- Add `user_id` BIGINT column (nullable, for dynamic rules only) ✅
- Add `button_texts` JSONB column (nullable, array of button texts for dynamic rules) ✅
- Add `clicking_userbot_id` INTEGER column (nullable, references userbots table) ✅
- **Enhanced:** Migrated to `clicking_userbot_ids` JSONB array for multi-userbot support ✅
- Backfill existing records with `rule_type = 'static'` ✅
- Add indexes on `rule_type`, `user_id`, `target_chat_id` ✅

**Notes:**
- Static rules use: `target_chat_id`, `bot_id`, `button_text` (singular)
- Dynamic rules use: `target_chat_id`, `user_id`, `button_texts` (array), `clicking_userbot_ids` (array)

---

### 2. Model Updates ✅ COMPLETED
**File:** `app/models/auto_button_click.py`

**New Methods:**
```python
async def get_dynamic_rules_for_chat_and_user(self, target_chat_id: int, user_id: int) -> List[asyncpg.Record]:
    """Get all enabled dynamic rules for specific chat and user"""
    query = """
        SELECT * FROM auto_button_click_rules
        WHERE rule_type = 'dynamic'
        AND target_chat_id = $1
        AND user_id = $2
        AND enabled = true
    """
    return await self.db.fetch(query, target_chat_id, user_id)

async def create_dynamic_rule(self, data: Dict) -> asyncpg.Record:
    """Create a dynamic click rule"""
    # Expects: target_chat_id, user_id, button_texts (list), clicking_userbot_id

async def get_all_rules_with_type(self) -> List[asyncpg.Record]:
    """Get all rules with type indicator for menu display"""
```

**Updates:**
- Modify `get_all_rules()` to include rule_type in display logic ✅
- Keep existing `get_rule_for_chat_and_bot()` for static rules (no changes) ✅
- **Note:** All methods implemented and working correctly ✅

---

### 3. FSM States ✅ COMPLETED
**File:** `app/ui/states.py`

**Add States:**
```python
# Dynamic Click wizard (Add)
adding_dynamic_click_rule_target = State() ✅
adding_dynamic_click_rule_user_id = State() ✅
adding_dynamic_click_rule_buttons = State() ✅
adding_dynamic_click_rule_userbot = State() ✅

# Dynamic Click wizard (Edit) - Enhanced
editing_dynamic_click_rule_user_id = State() ✅
editing_dynamic_click_rule_buttons = State() ✅
editing_dynamic_click_rule_userbots = State() ✅
editing_auto_click_rule_name = State() ✅  # NEW: Custom names
```

---

### 4. Keyboards ✅ COMPLETED
**File:** `app/ui/keyboards.py`

**Updates:**

#### `auto_click_menu(rules: List[Dict])` ✅
- Show rule type indicator: ✅
  - Static: `"✅ 📍 Chat: {chat_id}, Bot: {bot_id}"` (or custom name)
  - Dynamic: `"✅ 🔄 Chat: {chat_id}, User: {user_id}"` (or custom name)
- **Enhanced:** Shows custom rule name if set, otherwise fallback to chat/user display ✅
- Button labels updated to be more intuitive ✅

**Current Layout:**
```
[existing rules listed with type indicators or custom names]
[➕ Post → Reply → Click] [➕ User Post → Click]  # Enhanced labels
[🔙 Back]
```

#### `auto_click_rule_details(rule: Dict)` ✅
- Conditional rendering based on `rule['rule_type']`: ✅
  - **Static:** Show `target_chat_id`, `bot_id`, `button_text` ✅
  - **Dynamic:** Show `target_chat_id`, `user_id`, `button_texts` (list), `clicking_userbot_ids` (array) ✅
- **Enhanced:** Shows custom name in title if available ✅
- **Enhanced:** Added "✏️ Edit Name" button for all rules ✅

**New Keyboard:**
```python
def dynamic_click_select_userbot_keyboard(userbots: List[Dict], selected_ids: List[int]) -> InlineKeyboardMarkup:
    """Userbot multi-selection for dynamic click rule""" ✅
    # Enhanced: Multi-select with toggle functionality
```

---

### 5. Handler Updates ✅ COMPLETED
**File:** `app/ui/handlers/auto_click.py`

**New Methods (Add Wizard):**

#### `start_add_dynamic_rule(query, state)` ✅
- Show target group selection (reuse existing target list) ✅
- Set state: `adding_dynamic_click_rule_target` ✅

#### `wizard_process_dynamic_target(query, state)` ✅
- Save target_chat_id to state ✅
- Prompt: "Enter the User ID to monitor:" ✅
- Set state: `adding_dynamic_click_rule_user_id` ✅

#### `wizard_process_dynamic_user_id(message, state)` ✅
- Validate integer user_id ✅
- Save to state ✅
- Prompt: "Enter button texts separated by commas (e.g., Buy, Sell, Chart):" ✅
- Set state: `adding_dynamic_click_rule_buttons` ✅

#### `wizard_process_dynamic_buttons(message, state)` ✅
- Split by comma, strip whitespace, create list ✅
- Save button_texts to state ✅
- Show userbot multi-selection keyboard ✅
- Set state: `adding_dynamic_click_rule_userbot` ✅

#### `wizard_save_dynamic_rule(query, state)` ✅
- **Enhanced:** Multi-select userbots with toggle functionality ✅
- Save clicking_userbot_ids (array) to state ✅
- Create rule in DB ✅
- Clear state ✅
- Show success message ✅

**New Methods (Edit Wizard):** ✅ ENHANCED FEATURE
- `start_edit_dynamic_user(query, rule_id, state)` ✅
- `process_edit_dynamic_user(message, state)` ✅
- `start_edit_dynamic_buttons(query, rule_id, state)` ✅
- `process_edit_dynamic_buttons(message, state)` ✅
- `start_edit_dynamic_userbots(query, rule_id, state)` ✅
- `process_edit_dynamic_userbots(query, state)` ✅
- `start_edit_name(query, rule_id, state)` ✅ **NEW: Custom names**
- `process_edit_name(message, state)` ✅ **NEW: Custom names**

**Updates:**
- Modify `show_rule_details()` to render dynamic vs static differently ✅
- Add imports for `BotModel` to fetch userbots list ✅
- **Critical Bug Fix:** Added missing `import json` to fix edit functions ✅
- **Enhanced:** Comprehensive debug logging with `[AUTO_CLICK_DEBUG]` prefix ✅
- **Enhanced:** Handles both JSONB native lists and JSON strings ✅

---

### 6. Message Handler (Core Logic) ✅ COMPLETED
**File:** `app/userbot/message_handler.py`

**Implemented Method:** ✅
```python
async def _handle_dynamic_click(self, event):
    """
    Handle dynamic button clicking for monitored users

    Flow:
    1. Check if message has buttons ✅
    2. Get dynamic rules for this chat + sender ✅
    3. For each rule, find matching buttons (exact match) ✅
    4. **Enhanced:** Multi-userbot support with staggered clicking (2sec delay per bot) ✅
    5. **Enhanced:** Click with retry logic (3 attempts, 2sec between retries) ✅
    6. **Enhanced:** Refetch message before each click for fresh button reference ✅
    7. **Enhanced:** Graceful handling when buttons disappear (already clicked) ✅
    8. Click matching buttons with 1 sec delay between buttons ✅
    9. Log: "Clicked X buttons" with [DYNAMIC_CLICK] prefix ✅
    """

    # Key implementation details:
    - Checks if userbot is in clicking_userbot_ids array ✅
    - Deterministic turn order: sorted(ids), delay = my_index * 2 seconds ✅
    - Handles both JSON strings and native lists for button_texts ✅
    - Uses set() to avoid clicking same button twice ✅
    - 3 retry attempts per button with message refetch ✅
    - 1 second delay between different buttons ✅
    - Comprehensive error logging ✅
```

**Updates in `handle_message()`:** ✅
- Add call to `_handle_dynamic_click(event)` for incoming messages ✅
- Place it near existing `_handle_auto_click()` call (line ~131) ✅

```python
# Handle auto click (static)
if not is_edit and direction == "incoming":
    await self._handle_auto_click(event) ✅

# Handle dynamic click
if not is_edit and direction == "incoming":
    await self._handle_dynamic_click(event) ✅
```

**Imports:**
- `import asyncio` already present ✅

---

### 7. Registration & Routing ✅ COMPLETED
**File:** `app/management_bot.py`

**Updates:** ✅
- Register callback handlers for dynamic click wizard ✅
- Register message handlers for dynamic click wizard states ✅
- Register edit handlers for dynamic click (user, buttons, userbots) ✅
- Register name edit handlers ✅

**Implemented Registrations:**
```python
# Dynamic click add wizard
- auto_click_dynamic_wizard:target:{chat_id} ✅
- auto_click_dynamic_wizard:toggle_userbot:{bot_id} ✅
- auto_click_dynamic_wizard:userbots_done ✅
- ManagementStates.adding_dynamic_click_rule_user_id ✅
- ManagementStates.adding_dynamic_click_rule_buttons ✅
- ManagementStates.adding_dynamic_click_rule_userbot ✅

# Dynamic click edit handlers
- auto_click:edit_name:{rule_id} ✅
- auto_click:edit_user:{rule_id} ✅
- auto_click:edit_buttons:{rule_id} ✅
- auto_click:edit_userbots:{rule_id} ✅
- ManagementStates.editing_dynamic_click_rule_user_id ✅
- ManagementStates.editing_dynamic_click_rule_buttons ✅
- ManagementStates.editing_dynamic_click_rule_userbots ✅
- ManagementStates.editing_auto_click_rule_name ✅
```

---

## Files Changed Summary

### New Files: ✅
1. `migrations/046_add_dynamic_click_support.sql` - Initial schema ✅
2. `migrations/049_multi_userbot_dynamic_clicks.sql` - Multi-userbot enhancement ✅
3. `migrations/050_add_name_to_autoclick.sql` - Custom names feature ✅

### Modified Files: ✅
1. `app/models/auto_button_click.py` - Add dynamic rule methods ✅
2. `app/ui/states.py` - Add 8 wizard states (4 add + 3 edit + 1 name) ✅
3. `app/ui/keyboards.py` - Update menu, add dynamic keyboards, improved labels ✅
4. `app/ui/handlers/auto_click.py` - Add dynamic wizard flow + edit flows + name feature ✅
5. `app/userbot/message_handler.py` - Add dynamic click logic with enhancements ✅
6. `app/management_bot.py` - Register all dynamic click handlers ✅

### No Changes:
- `app/userbot/call_executor.py` - Static tracking logic stays separate ✅
- `migrations/023_add_auto_button_click.sql` - Original static rules ✅
- `migrations/025_add_autoclick_tracking.sql` - Tracking only for static rules ✅

---

## 🎯 ADDITIONAL FEATURES IMPLEMENTED

Beyond the original plan, these enhancements were added:

### 1. Multi-Userbot Support ✅
- **Original:** Single userbot per rule (`clicking_userbot_id`)
- **Enhanced:** Multiple userbots per rule (`clicking_userbot_ids` JSONB array)
- **Benefits:** Multiple bots can click the same buttons with staggered timing
- **Implementation:** Migration 049, deterministic turn order (2sec delay per bot)

### 2. Custom Rule Names ✅
- **Feature:** Set custom names for rules instead of technical details
- **UI:** Shows name in list if set, otherwise fallback to chat/user display
- **Edit:** New "✏️ Edit Name" button, type "clear" to remove name
- **Benefits:** Much easier to identify and organize rules
- **Implementation:** Migration 050, new state and handlers

### 3. Edit Capabilities ✅
- **Original Plan:** Only add new rules
- **Enhanced:** Full edit functionality for all dynamic rule fields:
  - ✏️ Edit Monitored User
  - ✏️ Edit Button Texts
  - ✏️ Edit Clicking Bots
  - ✏️ Edit Name
- **Benefits:** No need to delete and recreate rules

### 4. Enhanced Debugging ✅
- **Feature:** Comprehensive debug logging with `[AUTO_CLICK_DEBUG]` prefix
- **Coverage:** All CRUD operations, wizard steps, button clicking
- **Handles:** JSONB type variations (strings vs native lists)
- **Benefits:** Easy troubleshooting and monitoring

### 5. Improved UI Labels ✅
- **Original:** "Add Static Rule" / "Add Dynamic Rule"
- **New:** "➕ Post → Reply → Click" / "➕ User Post → Click"
- **Benefits:** Immediately clear workflow, no technical jargon

### 6. Critical Bug Fixes ✅
- **Missing Import:** Added `import json` to `auto_click.py`
- **Impact:** Edit buttons and edit userbots were failing
- **Fixed:** All edit operations now work correctly

### 7. Race Condition Prevention ✅
- **Problem:** Multiple userbots clicking simultaneously
- **Solution:** Staggered clicking with deterministic turn order
- **Implementation:** Sort userbot IDs, delay = index * 2 seconds
- **Benefits:** Prevents button conflicts and click failures

### 8. Button Click Resilience ✅
- **Retry Logic:** 3 attempts per button with 2sec delay
- **Message Refetch:** Gets fresh button reference before each click
- **Graceful Degradation:** Continues if one button fails
- **Disappearing Buttons:** Handles buttons already clicked by others
- **Benefits:** Much more reliable clicking in real-world scenarios

---

## Testing Checklist

### Static Rules (Regression Test): ✅
- [x] Old auto_click rules still work ✅
- [x] CA posting → bot reply → button click works ✅
- [x] Existing rules display correctly ✅

### Dynamic Rules (Core): ✅
- [x] Can create dynamic rule via wizard ✅
- [x] Target chat selection works ✅
- [x] User ID input validates ✅
- [x] Button texts parse correctly (comma-separated) ✅
- [x] Multi-userbot selection works ✅
- [x] Rule saves to DB correctly ✅

### Dynamic Rules (Edit): ✅ NEW
- [x] Can edit monitored user ID ✅
- [x] Can edit button texts ✅
- [x] Can edit clicking userbots (multi-select) ✅
- [x] Can set/edit custom name ✅
- [x] Can clear custom name (type "clear") ✅

### Runtime Behavior: ✅
- [x] Monitored user posts message with buttons ✅
- [x] Only messages with buttons trigger logic ✅
- [x] Exact match works (partial matches ignored) ✅
- [x] Multiple matching buttons clicked sequentially ✅
- [x] 1 second delay between buttons ✅
- [x] Multi-userbot staggered clicking (2sec per bot) ✅
- [x] Log shows "[DYNAMIC_CLICK] Clicked X buttons" ✅
- [x] Only assigned userbots click (others ignore) ✅

### Edge Cases: ✅
- [x] No buttons in message → no action ✅
- [x] No matching buttons → no action ✅
- [x] Disabled rule → no action ✅
- [x] Multiple rules for same user → both execute ✅
- [x] Button click fails → logged error, continues to next button ✅
- [x] Button disappears (clicked by another bot) → graceful handling ✅
- [x] Multiple userbots → no race conditions ✅

### UI/UX: ✅ NEW
- [x] Rules show custom names in list ✅
- [x] Rules show type icons (🔄 dynamic, 📍 static) ✅
- [x] Button labels are clear and workflow-focused ✅
- [x] Debug logging shows detailed error messages ✅

---

## Rollout Steps

1. **Create migrations** → ✅ DONE (046, 049, 050 created and tested)
2. **Update model** → ✅ DONE (queries tested and working)
3. **Add states** → ✅ DONE (8 states added)
4. **Update keyboards** → ✅ DONE (menu rendering tested)
5. **Implement handler** → ✅ DONE (wizard flow working)
6. **Update message handler** → ✅ DONE (click logic tested)
7. **Register routes** → ✅ DONE (all handlers registered)
8. **Run tests** → ✅ DONE (all checklist items verified)
9. **Fix bugs** → ✅ DONE (missing json import fixed)
10. **Add enhancements** → ✅ DONE (multi-userbot, names, edits, debugging)
11. **Deploy** → ⚠️ PENDING (run migrations on production)
12. **Monitor logs** → ⚠️ ONGOING (watch for `[DYNAMIC_CLICK]` and `[AUTO_CLICK_DEBUG]`)

---

## 📚 IMPLEMENTATION NOTES FOR AI ASSISTANTS

### Key Technical Details:

**1. Data Type Handling:**
- `button_texts` and `clicking_userbot_ids` are JSONB columns
- PostgreSQL may return them as native Python lists OR JSON strings
- Always check type with `isinstance()` before processing
- Use `json.loads()` for strings, direct use for lists

**2. Multi-Userbot Race Condition Prevention:**
```python
# Deterministic turn order to prevent simultaneous clicks
sorted_ids = sorted(clicking_userbot_ids)
my_turn_index = sorted_ids.index(self.userbot_id)
delay = my_turn_index * 2  # seconds
```

**3. Button Click Resilience:**
```python
# Always refetch message before clicking
fresh_msg = await client.get_messages(event.chat_id, ids=event.message.id)
# Then find and click button from fresh_msg.buttons
```

**4. Debug Logging:**
- All auto_click operations use `[AUTO_CLICK_DEBUG]` prefix
- Dynamic click runtime uses `[DYNAMIC_CLICK]` prefix
- Makes filtering logs easy: `grep AUTO_CLICK_DEBUG app.log`

**5. Import Requirements:**
- `import json` is CRITICAL in `auto_click.py` for edit operations
- `import asyncio` is needed in `message_handler.py` for delays

### Common Pitfalls to Avoid:

❌ **Don't** assume JSONB fields are always lists
✅ **Do** check type and handle both strings and lists

❌ **Don't** click buttons without refetching the message
✅ **Do** refetch for fresh button references

❌ **Don't** let multiple userbots click simultaneously
✅ **Do** use staggered delays based on sorted userbot IDs

❌ **Don't** stop clicking if one button fails
✅ **Do** catch exceptions and continue to next button

### Architecture Decisions:

**Why separate static and dynamic?**
- Static rules use CA tracking (different database table)
- Dynamic rules monitor any user (simpler, no tracking needed)
- Coexistence maintains backward compatibility

**Why JSONB arrays instead of separate tables?**
- Simpler data model for small lists (buttons, userbots)
- Easier to query (no joins needed)
- Faster for typical use case (< 10 items)

**Why multi-userbot support?**
- Redundancy: if one bot fails, others can click
- Load distribution: multiple bots can handle more rules
- Reliability: staggered clicking prevents conflicts

---
