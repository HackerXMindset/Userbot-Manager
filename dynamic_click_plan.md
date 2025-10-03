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

**New Method:**
```python
async def _handle_dynamic_click(self, event):
    """
    Handle dynamic button clicking for monitored users

    Flow:
    1. Check if message has buttons
    2. Get dynamic rules for this chat + sender
    3. For each rule, find matching buttons
    4. Click matching buttons with 1 sec delay
    5. Log: "Clicked X buttons"
    """

    if not event.buttons:
        return

    # Get dynamic rules for this chat and sender
    rules = await self.rule_model.get_dynamic_rules_for_chat_and_user(
        event.chat_id,
        event.sender_id
    )

    if not rules:
        return

    for rule in rules:
        # Check if this userbot is assigned to click
        if rule['clicking_userbot_id'] != self.userbot_id:
            continue

        button_texts = rule['button_texts']  # JSONB array
        matched_buttons = []

        # Find all matching buttons
        for row in event.buttons:
            for button in row:
                if hasattr(button, 'text') and button.text in button_texts:
                    matched_buttons.append(button)

        if not matched_buttons:
            continue

        # Click all matched buttons with 1 sec delay
        clicked_count = 0
        for button in matched_buttons:
            try:
                await button.click()
                clicked_count += 1
                if clicked_count < len(matched_buttons):
                    await asyncio.sleep(1)  # 1 sec delay between clicks
            except Exception as e:
                logger.error(f"Error clicking button in dynamic rule {rule['id']}: {e}")

        logger.info(f"[DYNAMIC_CLICK] Clicked {clicked_count} buttons for rule {rule['id']} in chat {event.chat_id}")
```

**Updates in `handle_message()`:**
- Add call to `_handle_dynamic_click(event)` for incoming messages
- Place it near existing `_handle_auto_click()` call

```python
# Handle auto click (static)
if not is_edit and direction == "incoming":
    await self._handle_auto_click(event)

# Handle dynamic click
if not is_edit and direction == "incoming":
    await self._handle_dynamic_click(event)
```

**Imports:**
- Add `import asyncio` at top of file

---

### 7. Registration & Routing
**File:** `app/management_bot.py`

**Updates:**
- Register new callback handlers for dynamic click wizard
- Register new message handlers for dynamic click wizard states

**Example:**
```python
# Dynamic click callbacks
router.callback_query.register(
    lambda c: c.data.startswith('auto_click:add_dynamic'),
    auto_click_handler.start_add_dynamic_rule
)

# Dynamic click wizard states
router.message.register(
    auto_click_handler.wizard_process_dynamic_user_id,
    ManagementStates.adding_dynamic_click_rule_user_id
)
```

---

## Files Changed Summary

### New Files:
1. `migrations/046_add_dynamic_click_support.sql` - Database schema changes

### Modified Files:
1. `app/models/auto_button_click.py` - Add dynamic rule methods
2. `app/ui/states.py` - Add 4 new wizard states
3. `app/ui/keyboards.py` - Update menu, add dynamic keyboards
4. `app/ui/handlers/auto_click.py` - Add dynamic wizard flow
5. `app/userbot/message_handler.py` - Add dynamic click logic
6. `app/management_bot.py` - Register dynamic click handlers

### No Changes:
- `app/userbot/call_executor.py` - Static tracking logic stays separate
- `migrations/023_add_auto_button_click.sql` - Original static rules
- `migrations/025_add_autoclick_tracking.sql` - Tracking only for static rules

---

## Testing Checklist

### Static Rules (Regression Test):
- [ ] Old auto_click rules still work
- [ ] CA posting → bot reply → button click works
- [ ] Existing rules display correctly

### Dynamic Rules:
- [ ] Can create dynamic rule via wizard
- [ ] Target chat selection works
- [ ] User ID input validates
- [ ] Button texts parse correctly (comma-separated)
- [ ] Userbot selection works
- [ ] Rule saves to DB correctly

### Runtime Behavior:
- [ ] Monitored user posts message with buttons
- [ ] Only messages with buttons trigger logic
- [ ] Exact match works (partial matches ignored)
- [ ] Multiple matching buttons clicked sequentially
- [ ] 1 second delay between clicks
- [ ] Log shows "Clicked X buttons"
- [ ] Only assigned userbot clicks (others ignore)

### Edge Cases:
- [ ] No buttons in message → no action
- [ ] No matching buttons → no action
- [ ] Disabled rule → no action
- [ ] Multiple rules for same user → both execute
- [ ] Button click fails → logged error, continues to next button

---

## Rollout Steps

1. **Create migration** → Run on test DB first
2. **Update model** → Test queries in isolation
3. **Add states** → Update states enum
4. **Update keyboards** → Test menu rendering
5. **Implement handler** → Test wizard flow
6. **Update message handler** → Test click logic
7. **Register routes** → Test end-to-end
8. **Run tests** → Verify all checklist items
9. **Deploy** → Run migration on production
10. **Monitor logs** → Watch for `[DYNAMIC_CLICK]` entries
