# Gain Alert System Redesign - Monitored People

## Overview
Complete redesign of the gain alert trigger mechanism. Instead of alerts triggering from source→target forwarding, alerts now trigger from **monitored people/channels/DMs** posting contract addresses directly in destination groups.

**Key Change**: Forwarding system remains unchanged. Only the gain alert initialization and delivery logic is being modified.

---

## Core Principles

### 1. One Token, One Tracking Entry
- `tokens_tracked` table maintains **single entry per token** regardless of how many groups monitor it
- Shared polling/monitoring across all groups
- Prevents duplicate API calls and maintains single tier-based scheduler entry

### 2. Per-Group Independent Baselines
- `token_group_alerts` junction table stores **group-specific tracking**
- Each group has its own `first_seen_mc` (market cap when they first detected the token)
- Each group's alerts fire based on their unique baseline
- Same token can be at different alert stages in different groups

### 3. Monitored Source Types
Three types of monitored sources:

**GROUPS**: Monitor specific people
- Must configure individual user_id to track
- Only messages from specified users trigger token detection
- Multiple people can be monitored in same group

**CHANNELS**: Monitor all messages
- No specific user needed
- Every CA posted in channel triggers detection
- Alerts reply to original channel message

**DMs**: Monitor all messages
- No specific user needed
- Every CA posted in DM triggers detection
- Alerts reply to original DM message

---

## Database Schema

### New Table: `monitored_sources`
```sql
CREATE TABLE monitored_sources (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    chat_type TEXT NOT NULL CHECK (chat_type IN ('group', 'channel', 'dm')),
    user_id BIGINT,  -- NULL for channels/DMs, required for groups
    added_by_admin_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chat_id, user_id)  -- Prevent duplicate person-group pairs
);

CREATE INDEX idx_monitored_sources_chat ON monitored_sources(chat_id);
CREATE INDEX idx_monitored_sources_user ON monitored_sources(user_id) WHERE user_id IS NOT NULL;
```

### New Table: `token_group_alerts`
```sql
CREATE TABLE token_group_alerts (
    id SERIAL PRIMARY KEY,
    token_id INT NOT NULL REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    first_seen_mc NUMERIC(20, 2) NOT NULL,
    last_alert_mc NUMERIC(20, 2),
    original_message_id BIGINT NOT NULL,  -- Message to reply to for alerts
    original_user_id BIGINT,  -- User who first posted this CA in this group
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(token_id, chat_id)  -- One tracking entry per token per group
);

CREATE INDEX idx_token_group_alerts_token ON token_group_alerts(token_id);
CREATE INDEX idx_token_group_alerts_chat ON token_group_alerts(chat_id);
CREATE INDEX idx_token_group_alerts_lookup ON token_group_alerts(token_id, chat_id);
```

### Schema Changes to Existing Tables
**NO CHANGES** to `tokens_tracked` - keep all existing columns including `source_group_id` for backwards compatibility.

---

## Detection & Tracking Flow

### Flow Diagram
```
Monitored Person/Channel/DM posts message
    ↓
Userbot receives message
    ↓
Check: Is sender monitored in this chat? (for groups)
OR: Is this chat monitored? (for channels/DMs)
    ↓ YES
Extract CA addresses (SOL/BNB pattern matching)
    ↓
For each CA:
    ↓
Check: Does token exist in tokens_tracked?
    ↓
    ├─ NO → Create new tokens_tracked entry
    │        Start tier-based polling
    │        ↓
    └─ YES → Token already being tracked
             ↓
Check: Does token_group_alerts(token_id, chat_id) exist?
    ↓
    ├─ YES → Ignore (group already tracking this token)
    │
    └─ NO → Fetch current MC from Jupiter/OKX
             ↓
             Create token_group_alerts entry:
             - first_seen_mc = current MC
             - last_alert_mc = NULL
             - original_message_id = message.id
             - original_user_id = sender.id
```

### Detailed Logic Examples

#### Example 1: Brand New Token
```
Event: Alice (monitored in Group1) posts ABC123
Current MC: $5,000

Actions:
1. tokens_tracked: INSERT (ABC123, status=active, current_tier=tier_a)
2. token_group_alerts: INSERT (ABC123, Group1, first_seen_mc=$5K, msg_id=123, user_id=Alice)
3. Start tier-based polling for ABC123

Future Alert:
- When ABC123 reaches $6,500 (30% gain)
- Alert sent to Group1, replying to message 123
```

#### Example 2: Existing Token, New Group
```
Event: Bob (monitored in Group2) posts ABC123
Token Status: Already tracked since $5K, currently at $50K

Actions:
1. tokens_tracked: No change (already exists)
2. token_group_alerts: INSERT (ABC123, Group2, first_seen_mc=$50K, msg_id=456, user_id=Bob)

Future Alerts:
- Group1 continues alerts from their $5K baseline
- Group2 gets first alert at $65K (30% from their $50K baseline)
```

#### Example 3: Same Token, Same Group, Different People
```
Event: Alice posts ABC123 in Group1 at $10K
Later: Bob posts same ABC123 in Group1 at $15K

Actions (Alice's post):
1. tokens_tracked: INSERT ABC123
2. token_group_alerts: INSERT (ABC123, Group1, first_seen_mc=$10K, msg_id=Alice's)

Actions (Bob's post):
1. Check token_group_alerts(ABC123, Group1) → EXISTS
2. IGNORE Bob's post (group already tracking this token)

Alert Behavior:
- Alert fires at $13K (30% from $10K)
- Alert replies to Alice's original message (msg_id stored)
- Bob's message ignored
```

#### Example 4: Channel Monitoring
```
Event: Channel123 (monitored) posts XYZ789
Current MC: $20K

Actions:
1. tokens_tracked: INSERT XYZ789
2. token_group_alerts: INSERT (XYZ789, Channel123, first_seen_mc=$20K, msg_id=789)

Alert Behavior:
- Alert sent to Channel123 itself
- Replies to message 789
```

---

## Alert Dispatch Logic

### Current Behavior (OLD - Being Replaced)
```python
# OLD: Alert sent to target groups based on source_group_id
target_groups = await get_target_groups_for_source(token.source_group_id)
for target in target_groups:
    send_alert(target.chat_id, alert_message)
```

### New Behavior
```python
# NEW: Alert sent to all groups tracking this token
tracking_groups = await db.fetch("""
    SELECT chat_id, original_message_id, first_seen_mc, last_alert_mc
    FROM token_group_alerts
    WHERE token_id = $1
""", token_id)

for group in tracking_groups:
    # Calculate if this group should receive alert based on THEIR baseline
    baseline_mc = group['last_alert_mc'] if group['last_alert_mc'] else group['first_seen_mc']
    gain_pct = (current_mc - baseline_mc) / baseline_mc

    if gain_pct >= 0.30:  # 30% threshold
        # Send alert to this group
        await send_alert(
            chat_id=group['chat_id'],
            message=alert_message,
            reply_to=group['original_message_id']
        )

        # Update baseline for this group
        await db.execute("""
            UPDATE token_group_alerts
            SET last_alert_mc = $1
            WHERE token_id = $2 AND chat_id = $3
        """, current_mc, token_id, group['chat_id'])
```

### Alert Message Format
**No change** - Use existing gain alert format:
```
🚀 GAIN ALERT

{ticker} (SOL)
CA: {address}

💰 Current MC: ${current_mc}
📈 Gain: +{gain_pct}%
⏰ {time}
```

Alert **replies to original message** where CA was posted.

---

## Management Bot UI

### Menu Structure

Two new sections added to **Settings** menu:

**1. 📈 Gain Alerts** (Monitored Source Management)
- View all monitored chats with stats
- Add new monitored source
- Remove monitored source

**2. ⚙️ Gain Alert Settings** (Global Thresholds)
- Configure gain threshold (default 30%)
- Configure drop threshold (default 70%)
- Configure drop floor MC (default $8,000)

---

### Main Gain Alerts Menu

```
User: Settings → "📈 Gain Alerts"
    ↓
Bot: "📈 Gain Alerts - Monitored Sources"

     Monitoring 3 chats tracking 12 tokens:

     👥 Group: Alpha Calls
        • 2 people monitored
        • 8 tokens tracked

     📢 Channel: Premium Signals
        • All messages monitored
        • 3 tokens tracked

     💬 DM: John (ID: 123456)
        • All messages monitored
        • 1 token tracked

     [➕ Add Monitored Source]
     [🗑️ Remove Monitored Source]
     [🔙 Back to Settings]
```

---

### Add Monitored Source Flow

```
User: Clicks [➕ Add Monitored Source]
    ↓
Bot: "➕ Add Monitored Source"

     What type of source are you adding?

     📢 Channel - Monitors ALL posts from a channel
     👥 Group - Monitors SPECIFIC people in a group
     💬 DM - Monitors ALL messages from a DM

     [📢 Channel] [👥 Group]
     [💬 DM]
     [❌ Cancel]
    ↓
User: Selects type (e.g., Group)
    ↓
Bot: "➕ Add 👥 Group Source"

     Please enter the Group Chat ID (negative number):

     Example: -1001234567890

     💡 Must be negative

     [❌ Cancel]
    ↓
User: Types chat ID (e.g., -1001234567890)
    ↓
Bot: "➕ Add User to Monitor"

     Group: Alpha Calls (-1001234567890)

     Enter the User ID to monitor in this group:

     Example: 123456789

     💡 Must be positive

     [❌ Cancel]
    ↓
User: Types user ID (e.g., 987654321)
    ↓
Bot: "✅ Confirm Monitored Source"

     Group: Alpha Calls (-1001234567890)
     Monitor User ID: 987654321

     When this user posts a CA in this group, gain alerts will be sent to the same group.

     [✅ Confirm] [❌ Cancel]
    ↓
User: Clicks [✅ Confirm]
    ↓
INSERT INTO monitored_sources (chat_id, chat_type, user_id, added_by_admin_id)
    ↓
Bot: "✅ Monitored Source Added!"

     👥 Group: Alpha Calls
     Monitoring User: 987654321

     Gain alerts will be sent when this user posts contract addresses.

     [📈 View All] [➕ Add Another] [🏠 Main Menu]
```

**For Channel/DM (no user_id needed):**
```
User: Selects Channel
    ↓
Bot: "➕ Add 📢 Channel Source"

     Please enter the Channel Chat ID (negative number):

     Example: -1001234567890

     [❌ Cancel]
    ↓
User: Types -1001234567890
    ↓
Bot: "✅ Confirm Monitored Source"

     Channel ID: -1001234567890

     ALL messages with CAs in this channel will trigger gain alerts.

     [✅ Confirm] [❌ Cancel]
    ↓
INSERT INTO monitored_sources (chat_id, chat_type, user_id=NULL, added_by_admin_id)
```

---

### View Monitored Sources (Detailed)

```
User: Opens "📈 Gain Alerts" menu
    ↓
Bot shows list with expandable details:

     👥 Alpha Calls
        User 987654321 - 5 tokens tracked
        User 111222333 - 2 tokens tracked
        [View Tokens] [Add Person] [Remove Person]

     📢 Premium Signals
        All messages - 3 tokens tracked
        [View Tokens] [Remove Source]

     💬 DM: John (123456)
        All messages - 1 token tracked
        [View Tokens] [Remove Source]
```

---

### Remove Monitored Source Flow

```
User: Clicks [🗑️ Remove Monitored Source]
    ↓
Bot: "🗑️ Remove Monitored Source"

     Select source to remove:

     [👥 Alpha Calls - User 987654321 (5 tokens)]
     [👥 Alpha Calls - User 111222333 (2 tokens)]
     [📢 Premium Signals (3 tokens)]
     [💬 DM: John (1 token)]
     [🔙 Back]
    ↓
User: Clicks source (e.g., User 987654321)
    ↓
Bot: "⚠️ Confirm Removal"

     Source: Alpha Calls
     User: 987654321
     Tokens Tracked: 5

     ⚠️ This will DELETE:
     • Monitored source entry
     • All 5 token tracking entries for this user in this group
     • All gain alert history

     This action CANNOT be undone!

     [⚠️ Confirm Delete] [❌ Cancel]
    ↓
User: Clicks [⚠️ Confirm Delete]
    ↓
DELETE FROM monitored_sources WHERE id = X;
DELETE FROM token_group_alerts WHERE chat_id = Y AND original_user_id = 987654321;
    ↓
Bot: "✅ Monitored Source Removed"

     User 987654321 removed from Alpha Calls
     5 token tracking entries deleted

     [📈 View All] [🏠 Main Menu]
```

---

### Gain Alert Settings Menu

```
User: Settings → "⚙️ Gain Alert Settings"
    ↓
Bot: "⚙️ Gain Alert Settings"

     Current Configuration:

     📈 Gain Threshold: 30%
        (Alert fires when token gains 30% from baseline)

     📉 Drop Threshold: 70%
        (Stop tracking if token drops to 70% of first_seen_mc)

     💰 Drop Floor: $8,000
        (Absolute floor - stop tracking below this MC)

     [Edit Gain Threshold]
     [Edit Drop Threshold]
     [Edit Drop Floor]
     [🔙 Back to Settings]
```

**Edit Flow (Example: Gain Threshold):**
```
User: Clicks [Edit Gain Threshold]
    ↓
Bot: "Edit Gain Threshold"

     Current: 30%

     Enter new gain threshold percentage (1-1000):

     Example: 50 (for 50% gain alerts)

     [❌ Cancel]
    ↓
User: Types 50
    ↓
UPDATE settings SET value = '0.50' WHERE key = 'gain_threshold_pct';
    ↓
Bot: "✅ Gain Threshold Updated"

     New threshold: 50%

     Future alerts will fire when tokens gain 50% from baseline.

     [⚙️ Settings] [🏠 Main Menu]
```

---

### Permissions & Access Control

- **Admin-only access** to both sections
- Check `settings.admin_telegram_ids` before showing buttons
- Non-admins see "🔒 Admin access required" message
- All database modifications logged with `added_by_admin_id`

---

## Userbot Handler Changes

### Current Flow (OLD)
```python
@client.on(events.NewMessage)
async def handler(event):
    # Check if message from SOURCE chat
    if event.chat_id in source_chat_ids:
        addresses = extract_addresses(event.message.text)
        await process_and_forward(addresses, target_groups)
```

### New Flow
```python
@client.on(events.NewMessage)
async def handler(event):
    chat_id = event.chat_id
    sender_id = event.sender_id

    # Check if this is a monitored source
    monitored = await db.fetchrow("""
        SELECT * FROM monitored_sources
        WHERE chat_id = $1
        AND (user_id = $2 OR user_id IS NULL)
    """, chat_id, sender_id)

    if not monitored:
        return  # Not monitoring this chat/person

    # For groups: check user_id match
    if monitored['chat_type'] == 'group' and monitored['user_id'] != sender_id:
        return  # Different person in group

    # Extract CA addresses
    addresses = extract_token_addresses(event.message.text)

    for address, blockchain in addresses:
        await process_monitored_token(
            address=address,
            blockchain=blockchain,
            chat_id=chat_id,
            message_id=event.message.id,
            user_id=sender_id
        )
```

### New Function: `process_monitored_token()`
```python
async def process_monitored_token(address, blockchain, chat_id, message_id, user_id):
    """
    Process a token posted by a monitored source
    """
    # Check if token already exists in tokens_tracked
    token = await db.fetchrow("SELECT id FROM tokens_tracked WHERE address = $1", address)

    if not token:
        # New token - create tracking entry
        token_id = await create_token_tracking(address, blockchain)
    else:
        token_id = token['id']

    # Check if this group is already tracking this token
    existing = await db.fetchrow("""
        SELECT id FROM token_group_alerts
        WHERE token_id = $1 AND chat_id = $2
    """, token_id, chat_id)

    if existing:
        logger.debug(f"Group {chat_id} already tracking token {address}, ignoring duplicate")
        return

    # Get current market cap
    current_mc = await fetch_current_mc(address, blockchain)

    if not current_mc or current_mc < MIN_VALID_MARKET_CAP or current_mc > MAX_VALID_MARKET_CAP:
        logger.warning(f"Invalid MC for {address}: {current_mc}, skipping")
        return

    # Create group-specific alert tracking
    await db.execute("""
        INSERT INTO token_group_alerts
        (token_id, chat_id, first_seen_mc, original_message_id, original_user_id)
        VALUES ($1, $2, $3, $4, $5)
    """, token_id, chat_id, current_mc, message_id, user_id)

    logger.info(f"Started monitoring {address} for group {chat_id} at MC ${current_mc:,.2f}")
```

---

## Implementation Plan - 6 Phases

---

### Phase 1: Database Schema & Migration

**Objective:** Create new tables for monitored sources and per-group alert tracking

**Files to create:**
- `migrations/064_add_monitored_sources.sql`

**Migration content:**
```sql
-- Create monitored_sources table
CREATE TABLE IF NOT EXISTS monitored_sources (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    chat_type TEXT NOT NULL CHECK (chat_type IN ('group', 'channel', 'dm')),
    user_id BIGINT,  -- NULL for channels/DMs, required for groups
    added_by_admin_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chat_id, user_id)  -- Prevent duplicate person-group pairs
);

CREATE INDEX idx_monitored_sources_chat ON monitored_sources(chat_id);
CREATE INDEX idx_monitored_sources_user ON monitored_sources(user_id) WHERE user_id IS NOT NULL;

-- Create token_group_alerts table
CREATE TABLE IF NOT EXISTS token_group_alerts (
    id SERIAL PRIMARY KEY,
    token_id INT NOT NULL REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    first_seen_mc NUMERIC(20, 2) NOT NULL,
    last_alert_mc NUMERIC(20, 2),
    original_message_id BIGINT NOT NULL,
    original_user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(token_id, chat_id)  -- One tracking entry per token per group
);

CREATE INDEX idx_token_group_alerts_token ON token_group_alerts(token_id);
CREATE INDEX idx_token_group_alerts_chat ON token_group_alerts(chat_id);
CREATE INDEX idx_token_group_alerts_lookup ON token_group_alerts(token_id, chat_id);
```

**Acceptance Criteria:**
- [ ] Migration file created
- [ ] Run migration on database: `psql $DATABASE_URL -f migrations/064_add_monitored_sources.sql`
- [ ] Verify tables exist: `\dt monitored_sources token_group_alerts`
- [ ] Verify indexes created: `\di idx_monitored_*` and `\di idx_token_group_*`
- [ ] Test UNIQUE constraints (attempt duplicate insert should fail)
- [ ] Test foreign key constraint (delete token → cascades to token_group_alerts)

---

### Phase 2: Management Bot UI - Gain Alerts Section

**Objective:** Add "📈 Gain Alerts" section to Settings menu for managing monitored sources

**Files to create:**
- `app/ui/handlers/gain_alerts.py` - Main handler for gain alerts management
- `app/models/monitored_source.py` - Model for database operations

**Files to modify:**
- `app/ui/keyboards.py` - Add gain alerts buttons
- `app/ui/handlers/settings.py` - Add gain alerts menu item
- `app/ui/states.py` - Add FSM states for gain alerts
- `app/management_bot.py` - Register gain alerts handlers

**Features to implement:**

1. **Main Menu** (`show_gain_alerts_menu`):
   - Query all monitored sources with stats
   - Display grouped by chat (groups, channels, DMs)
   - Show token counts per source
   - Buttons: [➕ Add] [🗑️ Remove] [🔙 Back]

2. **Add Flow** (`start_add_monitored_source`):
   - Type selection: [📢 Channel] [👥 Group] [💬 DM]
   - Chat ID input with validation (negative for groups/channels, positive for DMs)
   - For groups: additional user_id input step
   - Confirmation screen with details
   - Database insert with admin_id tracking

3. **View Details** (`show_monitored_source_details`):
   - List all monitored entries per chat
   - Show token counts per entry
   - Buttons: [View Tokens] [Add Person] [Remove]

4. **Remove Flow** (`remove_monitored_source`):
   - Selection list of all monitored sources
   - Show token counts in selection
   - Confirmation with warning about data deletion
   - Hard delete from both tables

5. **Admin Access Control**:
   - Check `settings.admin_telegram_ids` before all actions
   - Show "🔒 Admin access required" for non-admins

**Acceptance Criteria:**
- [ ] "📈 Gain Alerts" appears in Settings menu
- [ ] Add flow works for all 3 types (group/channel/dm)
- [ ] Chat ID validation (negative for groups/channels, positive for DMs)
- [ ] User ID validation for groups (positive integers only)
- [ ] View shows accurate stats (source count, token count)
- [ ] Remove performs hard delete with confirmation
- [ ] Admin-only access enforced
- [ ] FSM states transition correctly
- [ ] Cancel buttons work at every step

---

### Phase 3: Management Bot UI - Gain Alert Settings Section

**Objective:** Add "⚙️ Gain Alert Settings" section for global threshold configuration

**Files to modify:**
- `app/ui/handlers/settings.py` - Add gain alert settings menu
- `app/ui/states.py` - Add FSM states for settings editing

**Features to implement:**

1. **Settings Menu** (`show_gain_alert_settings`):
   - Query current values from `settings` table
   - Display:
     - Gain threshold (default 30%)
     - Drop threshold (default 70%)
     - Drop floor MC (default $8,000)
   - Buttons for each: [Edit X]

2. **Edit Gain Threshold** (`edit_gain_threshold`):
   - Show current value
   - Input validation: 1-1000 (percentage)
   - Update `settings` table: `gain_threshold_pct`
   - Show confirmation with new value

3. **Edit Drop Threshold** (`edit_drop_threshold`):
   - Show current value
   - Input validation: 1-100 (percentage)
   - Update `settings` table: `drop_threshold_pct`
   - Show confirmation

4. **Edit Drop Floor** (`edit_drop_floor`):
   - Show current value
   - Input validation: 100-1000000 (dollars)
   - Update `settings` table: `drop_floor_mc`
   - Show confirmation

**Acceptance Criteria:**
- [ ] "⚙️ Gain Alert Settings" appears in Settings menu
- [ ] Current values load from database correctly
- [ ] Edit gain threshold validates 1-1000
- [ ] Edit drop threshold validates 1-100
- [ ] Edit drop floor validates 100-1000000
- [ ] Database updates persist correctly
- [ ] Confirmation shows new values
- [ ] Admin-only access enforced
- [ ] Cancel works at every step

---

### Phase 4: Userbot Handler - Monitored Source Detection

**Objective:** Update userbot to detect monitored sources and create token_group_alerts entries

**Files to modify:**
- `app/userbot/handlers.py` - Add monitored source check in message handler
- `app/userbot/token_monitor.py` - Add `process_monitored_token()` function

**Logic to implement:**

1. **Message Handler Check** (in `handlers.py`):
```python
@client.on(events.NewMessage)
async def handler(event):
    chat_id = event.chat_id
    sender_id = event.sender_id

    # Check if this is a monitored source
    monitored = await db.fetchrow("""
        SELECT * FROM monitored_sources
        WHERE chat_id = $1
        AND (user_id = $2 OR user_id IS NULL)
    """, chat_id, sender_id)

    if not monitored:
        return  # Not monitoring this chat/person

    # For groups: verify user_id match
    if monitored['chat_type'] == 'group' and monitored['user_id'] != sender_id:
        return

    # Extract CA addresses
    addresses = extract_token_addresses(event.message.text)

    for address, blockchain in addresses:
        await process_monitored_token(
            address=address,
            blockchain=blockchain,
            chat_id=chat_id,
            message_id=event.message.id,
            user_id=sender_id
        )
```

2. **Process Monitored Token** (in `token_monitor.py`):
```python
async def process_monitored_token(address, blockchain, chat_id, message_id, user_id):
    # Check if token exists
    token = await db.fetchrow("SELECT id FROM tokens_tracked WHERE address = $1", address)

    if not token:
        # Create new token tracking via dex service
        from app.dex import get_dex_service
        dex = get_dex_service()
        result = await dex.add_token(address)
        token_id = result['token_id']
    else:
        token_id = token['id']

    # Check if this group is already tracking
    existing = await db.fetchrow("""
        SELECT id FROM token_group_alerts
        WHERE token_id = $1 AND chat_id = $2
    """, token_id, chat_id)

    if existing:
        logger.debug(f"[GROUP_ALERT_DUP] {chat_id} already tracking {address}")
        return

    # Fetch current MC
    current_mc = await fetch_current_mc(address, blockchain)

    if not current_mc or current_mc < MIN_VALID_MARKET_CAP:
        logger.warning(f"[MONITOR_DETECT] Invalid MC for {address}: {current_mc}")
        return

    # Create group-specific tracking
    await db.execute("""
        INSERT INTO token_group_alerts
        (token_id, chat_id, first_seen_mc, original_message_id, original_user_id)
        VALUES ($1, $2, $3, $4, $5)
    """, token_id, chat_id, current_mc, message_id, user_id)

    logger.info(f"[GROUP_ALERT_NEW] {address} tracking started for chat {chat_id} at ${current_mc:,.2f}")
```

**Acceptance Criteria:**
- [ ] Userbot detects messages from monitored sources
- [ ] Groups verify user_id match correctly
- [ ] Channels/DMs monitor all messages (user_id IS NULL)
- [ ] CA extraction works (SOL/BNB patterns)
- [ ] Token creation via dex service if not exists
- [ ] Duplicate check prevents multiple entries for same token+group
- [ ] MC validation rejects invalid values
- [ ] Logging shows [MONITOR_DETECT] [GROUP_ALERT_NEW] [GROUP_ALERT_DUP]
- [ ] Database inserts successful

---

### Phase 5: Alert Dispatch - Per-Group Baselines

**Objective:** Update alert dispatch logic to use token_group_alerts instead of source_group_id

**Files to modify:**
- `app/dex.py` - Update `_dispatch_gain_alert()` method

**Changes to implement:**

1. **Replace source_group_id lookup** with token_group_alerts query:
```python
async def _dispatch_gain_alert(self, token_id: int, address: str, current_mc: Decimal, ticker: str):
    # OLD: Get target groups from source_group_id
    # NEW: Get all groups tracking this token
    tracking_groups = await db.fetch("""
        SELECT chat_id, original_message_id, first_seen_mc, last_alert_mc, original_user_id
        FROM token_group_alerts
        WHERE token_id = $1
    """, token_id)

    if not tracking_groups:
        logger.debug(f"[GROUP_ALERT_FIRE] No groups tracking {address}")
        return

    # Load global threshold
    settings = await get_gain_alert_settings()
    gain_threshold = settings['gain_threshold_pct']

    for group in tracking_groups:
        # Calculate per-group baseline
        baseline_mc = group['last_alert_mc'] if group['last_alert_mc'] else group['first_seen_mc']
        gain_pct = (current_mc - baseline_mc) / baseline_mc

        if gain_pct >= gain_threshold:
            # Build alert message
            alert_msg = self._build_gain_alert_message(
                ticker=ticker,
                address=address,
                current_mc=current_mc,
                gain_pct=gain_pct * 100
            )

            # Persist to alert_queue
            alert_id = await db.fetchval("""
                INSERT INTO alert_queue
                (token_id, token_address, alert_message, target_chat_id, reply_to_message_id, status)
                VALUES ($1, $2, $3, $4, $5, 'pending')
                RETURNING id
            """, token_id, address, alert_msg, group['chat_id'], group['original_message_id'])

            # Send alert
            try:
                await send_message(
                    chat_id=group['chat_id'],
                    message=alert_msg,
                    reply_to=group['original_message_id']
                )

                # Update alert_queue status
                await db.execute("UPDATE alert_queue SET status = 'sent' WHERE id = $1", alert_id)

                # Update baseline for this group
                await db.execute("""
                    UPDATE token_group_alerts
                    SET last_alert_mc = $1
                    WHERE token_id = $2 AND chat_id = $3
                """, current_mc, token_id, group['chat_id'])

                logger.info(f"[GROUP_ALERT_FIRE] {address} alert sent to {group['chat_id']}, baseline updated to ${current_mc:,.2f}")

            except Exception as e:
                logger.error(f"[GROUP_ALERT_FIRE] Failed to send alert: {e}")
                await db.execute("UPDATE alert_queue SET status = 'failed', error = $1 WHERE id = $2", str(e), alert_id)
```

2. **Keep backward compatibility:**
   - Don't delete source_group_id column
   - Old forwarding continues working
   - Only gain alert routing changes

**Acceptance Criteria:**
- [ ] Alert dispatch queries token_group_alerts instead of source_group_id
- [ ] Per-group baseline calculated correctly (last_alert_mc OR first_seen_mc)
- [ ] Gain percentage calculated against group-specific baseline
- [ ] Alert sent to correct chat_id
- [ ] Alert replies to original_message_id
- [ ] Baseline updates after alert fires
- [ ] Multiple groups receive independent alerts
- [ ] Alert persisted to alert_queue before sending
- [ ] Logging shows [GROUP_ALERT_FIRE] with details
- [ ] Error handling updates alert_queue status

---

### Phase 6: Testing & Validation

**Objective:** End-to-end testing of all 5 examples and edge cases

**Test Scenarios:**

**Test 1: Brand New Token**
- Setup: Add monitored person in Group1
- Action: Person posts new token ABC123 at $5K MC
- Expected:
  - `tokens_tracked` entry created
  - `token_group_alerts` entry created with first_seen_mc=$5K
  - Alert fires when token reaches $6.5K (30% gain)
  - Alert replies to original message

**Test 2: Existing Token, New Group**
- Setup: Token ABC123 already tracked from $5K, currently at $50K
- Action: Add monitored person in Group2, person posts ABC123
- Expected:
  - No new `tokens_tracked` entry
  - New `token_group_alerts` entry with first_seen_mc=$50K
  - Group1 continues getting alerts from $5K baseline
  - Group2 gets first alert at $65K (30% from $50K baseline)

**Test 3: Same Token, Same Group, Different People**
- Setup: Alice monitored in Group1
- Action 1: Alice posts ABC123 at $10K
- Action 2: Bob posts same ABC123 in Group1 at $15K
- Expected:
  - Alice's post creates `token_group_alerts` entry
  - Bob's post ignored (duplicate check)
  - Alert fires at $13K, replies to Alice's message
  - Bob's message not used for alerts

**Test 4: Channel Monitoring**
- Setup: Add monitored channel
- Action: Any message with CA in channel
- Expected:
  - Token tracking starts
  - Alert sent to channel itself
  - Alert replies to original channel message

**Test 5: Multiple People, Same Group**
- Setup: Alice AND Bob both monitored in Group1
- Action 1: Alice posts XYZ at $8K
- Action 2: Bob posts DEF at $12K
- Expected:
  - Both tokens tracked independently
  - Both get alerts in Group1
  - Alerts reply to respective original messages

**Test 6: Remove Monitored Source**
- Setup: User monitored with 3 tokens tracked
- Action: Remove monitored source
- Expected:
  - `monitored_sources` entry deleted
  - All 3 `token_group_alerts` entries deleted
  - No more alerts for that user in that group

**Test 7: Global Settings Change**
- Setup: Change gain threshold from 30% to 50%
- Action: Token gains 40%
- Expected:
  - No alert fires (below 50% threshold)
  - Alert fires when token reaches 50% gain

**Test 8: MC Validation**
- Setup: Add monitored source
- Action: Post token with MC < $1K or > $1T
- Expected:
  - Token rejected
  - No `token_group_alerts` entry created
  - Log warning about invalid MC

**Acceptance Criteria:**
- [ ] All 8 test scenarios pass
- [ ] Database state correct after each test
- [ ] Logging shows correct prefixes
- [ ] No duplicate alerts sent
- [ ] Baselines update correctly
- [ ] Hard deletes cascade properly
- [ ] Admin access enforced in UI
- [ ] FSM states clean up properly

**Performance Testing:**
- [ ] Add 10 monitored sources
- [ ] Track 50 tokens across 5 groups
- [ ] Verify alert dispatch handles multiple groups efficiently
- [ ] Check database query performance on token_group_alerts lookups

---

## Phase Execution Order

**Sequential (must complete in order):**
1. Phase 1 → Phase 2 → Phase 3 (can swap 2 and 3)
2. Phase 4 (requires Phase 1 complete)
3. Phase 5 (requires Phase 1 and 4 complete)
4. Phase 6 (requires all phases complete)

**Critical Path:**
Phase 1 → Phase 4 → Phase 5 → Phase 6

**Optional Parallel:**
Phase 2 and Phase 3 can be developed in parallel after Phase 1

---

## Step-by-Step Implementation Todo List

**READ THIS FIRST:**
- Complete tasks in EXACT order listed
- Do NOT skip any task
- Verify each task before moving to next
- If a task fails, STOP and fix before continuing

---

### PHASE 1: Database Schema

#### Task 1.1: Create Migration File
```bash
# Command to run:
touch migrations/064_add_monitored_sources.sql

# Verification:
ls -la migrations/064_add_monitored_sources.sql
# Should show file exists
```

#### Task 1.2: Write monitored_sources Table SQL
```bash
# Open file:
# migrations/064_add_monitored_sources.sql

# Copy this EXACT content into the file:
```
```sql
-- Migration 064: Add Monitored Sources for Gain Alerts
-- Created: 2025-XX-XX

-- Create monitored_sources table
CREATE TABLE IF NOT EXISTS monitored_sources (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    chat_type TEXT NOT NULL CHECK (chat_type IN ('group', 'channel', 'dm')),
    user_id BIGINT,
    added_by_admin_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(chat_id, user_id)
);

-- Create indexes for monitored_sources
CREATE INDEX idx_monitored_sources_chat ON monitored_sources(chat_id);
CREATE INDEX idx_monitored_sources_user ON monitored_sources(user_id) WHERE user_id IS NOT NULL;
```
```bash
# Save and close file

# Verification:
grep "CREATE TABLE IF NOT EXISTS monitored_sources" migrations/064_add_monitored_sources.sql
# Should return the line
```

#### Task 1.3: Write token_group_alerts Table SQL
```bash
# Open file:
# migrations/064_add_monitored_sources.sql

# Append this EXACT content to the file:
```
```sql
-- Create token_group_alerts table
CREATE TABLE IF NOT EXISTS token_group_alerts (
    id SERIAL PRIMARY KEY,
    token_id INT NOT NULL REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    first_seen_mc NUMERIC(20, 2) NOT NULL,
    last_alert_mc NUMERIC(20, 2),
    original_message_id BIGINT NOT NULL,
    original_user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(token_id, chat_id)
);

-- Create indexes for token_group_alerts
CREATE INDEX idx_token_group_alerts_token ON token_group_alerts(token_id);
CREATE INDEX idx_token_group_alerts_chat ON token_group_alerts(chat_id);
CREATE INDEX idx_token_group_alerts_lookup ON token_group_alerts(token_id, chat_id);
```
```bash
# Save and close file

# Verification:
grep "CREATE TABLE IF NOT EXISTS token_group_alerts" migrations/064_add_monitored_sources.sql
# Should return the line
```

#### Task 1.4: Run Migration on Database
```bash
# Command to run (replace $DATABASE_URL with actual connection string):
psql $SUPABASE_POOLER_URL -f migrations/064_add_monitored_sources.sql

# Expected output:
# CREATE TABLE
# CREATE INDEX
# CREATE INDEX
# CREATE TABLE
# CREATE INDEX
# CREATE INDEX
# CREATE INDEX

# If you see errors, STOP and fix them before continuing
```

#### Task 1.5: Verify Tables Created
```bash
# Command to run:
psql $SUPABASE_POOLER_URL -c "\dt monitored_sources"

# Expected output:
# Should show table "monitored_sources"

# Command to run:
psql $SUPABASE_POOLER_URL -c "\dt token_group_alerts"

# Expected output:
# Should show table "token_group_alerts"
```

#### Task 1.6: Verify Indexes Created
```bash
# Command to run:
psql $SUPABASE_POOLER_URL -c "\di idx_monitored_sources_chat"

# Should show index exists

# Command to run:
psql $SUPABASE_POOLER_URL -c "\di idx_token_group_alerts_lookup"

# Should show index exists
```

#### Task 1.7: Test UNIQUE Constraint
```bash
# Command to run:
psql $SUPABASE_POOLER_URL -c "INSERT INTO monitored_sources (chat_id, chat_type, user_id, added_by_admin_id) VALUES (-12345, 'group', 99999, 1);"

# Expected output: INSERT 0 1

# Command to run (duplicate insert):
psql $SUPABASE_POOLER_URL -c "INSERT INTO monitored_sources (chat_id, chat_type, user_id, added_by_admin_id) VALUES (-12345, 'group', 99999, 1);"

# Expected output: ERROR: duplicate key value violates unique constraint

# Cleanup:
psql $SUPABASE_POOLER_URL -c "DELETE FROM monitored_sources WHERE chat_id = -12345;"
```

#### Task 1.8: Test Foreign Key Cascade
```bash
# This test is optional but recommended
# Insert test token, insert test alert, delete token, verify alert deleted

# Skip if confident, mark as DONE
```

**PHASE 1 COMPLETE - Verify all 8 tasks marked DONE before proceeding**

---

### PHASE 2: Management Bot UI - Gain Alerts Section

#### Task 2.1: Create monitored_source Model File
```bash
# Command to run:
touch app/models/monitored_source.py

# Verification:
ls -la app/models/monitored_source.py
# Should show file exists
```

#### Task 2.2: Write MonitoredSourceModel Class
```bash
# Open file: app/models/monitored_source.py

# Copy this EXACT content:
```
```python
"""
Monitored Source Model - Database operations for gain alert monitored sources
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class MonitoredSourceModel:
    """Model for monitored_sources table operations"""

    def __init__(self, db):
        self.db = db

    async def get_all_with_stats(self) -> List[Dict[str, Any]]:
        """Get all monitored sources with token tracking stats"""
        return await self.db.fetch("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) as token_count
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            GROUP BY ms.id
            ORDER BY ms.created_at DESC
        """)

    async def get_by_chat(self, chat_id: int) -> List[Dict[str, Any]]:
        """Get all monitored sources for a specific chat"""
        return await self.db.fetch("""
            SELECT
                ms.*,
                COUNT(DISTINCT tga.token_id) as token_count
            FROM monitored_sources ms
            LEFT JOIN token_group_alerts tga ON tga.chat_id = ms.chat_id
                AND (tga.original_user_id = ms.user_id OR ms.user_id IS NULL)
            WHERE ms.chat_id = $1
            GROUP BY ms.id
            ORDER BY ms.created_at DESC
        """, chat_id)

    async def add_source(self, chat_id: int, chat_type: str, user_id: Optional[int], admin_id: int) -> Dict[str, Any]:
        """Add new monitored source"""
        return await self.db.fetchrow("""
            INSERT INTO monitored_sources (chat_id, chat_type, user_id, added_by_admin_id)
            VALUES ($1, $2, $3, $4)
            RETURNING *
        """, chat_id, chat_type, user_id, admin_id)

    async def remove_source(self, source_id: int) -> bool:
        """Remove monitored source and all related token_group_alerts"""
        # Get source details for cleanup
        source = await self.db.fetchrow("SELECT * FROM monitored_sources WHERE id = $1", source_id)
        if not source:
            return False

        # Delete token_group_alerts entries
        await self.db.execute("""
            DELETE FROM token_group_alerts
            WHERE chat_id = $1
            AND (original_user_id = $2 OR $2 IS NULL)
        """, source['chat_id'], source['user_id'])

        # Delete monitored source
        result = await self.db.execute("DELETE FROM monitored_sources WHERE id = $1", source_id)
        return result == "DELETE 1"

    async def get_by_id(self, source_id: int) -> Optional[Dict[str, Any]]:
        """Get monitored source by ID"""
        return await self.db.fetchrow("SELECT * FROM monitored_sources WHERE id = $1", source_id)

    async def is_monitored(self, chat_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Check if chat/user combination is monitored"""
        return await self.db.fetchrow("""
            SELECT * FROM monitored_sources
            WHERE chat_id = $1
            AND (user_id = $2 OR user_id IS NULL)
        """, chat_id, user_id)
```
```bash
# Save and close file

# Verification:
grep "class MonitoredSourceModel" app/models/monitored_source.py
# Should return the class definition line
```

#### Task 2.3: Add FSM States for Gain Alerts
```bash
# Open file: app/ui/states.py

# Find the ManagementStates class

# Add these lines INSIDE the class (after existing states):
```
```python
    # Gain Alerts states
    gain_alerts_add_chat_id = State()
    gain_alerts_add_user_id = State()
    gain_alerts_add_confirm = State()
```
```bash
# Save and close file

# Verification:
grep "gain_alerts_add_chat_id" app/ui/states.py
# Should return the line
```

#### Task 2.4: Create gain_alerts Handler File
```bash
# Command to run:
touch app/ui/handlers/gain_alerts.py

# Verification:
ls -la app/ui/handlers/gain_alerts.py
```

#### Task 2.5: Write Gain Alerts Handler - Part 1 (Imports and Main Menu)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Copy this EXACT content:
```
```python
"""
Gain Alerts Handler - Management UI for monitored sources
"""

import logging
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.ui.states import ManagementStates
from app.models.monitored_source import MonitoredSourceModel
from app.config import settings

logger = logging.getLogger(__name__)


class GainAlertsHandler:
    """Handler for gain alerts monitored sources management"""

    def __init__(self, db, keyboards):
        self.db = db
        self.keyboards = keyboards
        self.model = MonitoredSourceModel(db)

    def is_admin(self, user_id: int) -> bool:
        """Check if user is admin"""
        return user_id in settings.admin_telegram_ids_list

    async def show_main_menu(self, query: types.CallbackQuery):
        """Show main gain alerts menu with monitored sources list"""
        try:
            if not self.is_admin(query.from_user.id):
                await query.answer("🔒 Admin access required", show_alert=True)
                return

            # Get all monitored sources with stats
            sources = await self.model.get_all_with_stats()

            # Group by chat_id
            chats = {}
            total_tokens = 0
            for source in sources:
                chat_id = source['chat_id']
                if chat_id not in chats:
                    chats[chat_id] = {
                        'chat_id': chat_id,
                        'chat_type': source['chat_type'],
                        'sources': [],
                        'total_tokens': 0
                    }
                chats[chat_id]['sources'].append(source)
                chats[chat_id]['total_tokens'] += source['token_count'] or 0
                total_tokens += source['token_count'] or 0

            # Build message
            type_emojis = {'group': '👥', 'channel': '📢', 'dm': '💬'}

            text = "<b>📈 Gain Alerts - Monitored Sources</b>\n\n"

            if not sources:
                text += "No monitored sources configured.\n\n"
                text += "Add a monitored source to start receiving gain alerts when specific people post contract addresses."
            else:
                text += f"Monitoring <b>{len(chats)}</b> chats tracking <b>{total_tokens}</b> tokens:\n\n"

                for chat_id, chat_data in chats.items():
                    emoji = type_emojis.get(chat_data['chat_type'], '📡')
                    text += f"{emoji} <b>Chat {chat_id}</b>\n"

                    for source in chat_data['sources']:
                        if source['user_id']:
                            text += f"   • User {source['user_id']} - {source['token_count']} tokens\n"
                        else:
                            text += f"   • All messages - {source['token_count']} tokens\n"

                    text += "\n"

            # Build keyboard
            keyboard_rows = [
                [InlineKeyboardButton(text="➕ Add Monitored Source", callback_data="gain_alerts:add")],
            ]

            if sources:
                keyboard_rows.append([
                    InlineKeyboardButton(text="🗑️ Remove Monitored Source", callback_data="gain_alerts:remove")
                ])

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back to Settings", callback_data="menu:settings")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing gain alerts menu: {e}", exc_info=True)
            await query.answer("❌ Error loading gain alerts menu")
```
```bash
# Save file (DO NOT CLOSE YET - more content coming)

# Verification:
grep "async def show_main_menu" app/ui/handlers/gain_alerts.py
# Should return the method definition
```

#### Task 2.6: Write Gain Alerts Handler - Part 2 (Add Flow Start)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Append this content to the END of the file (inside the class):
```
```python
    async def start_add_source(self, query: types.CallbackQuery, state: FSMContext):
        """Start add monitored source flow - show type selection"""
        try:
            if not self.is_admin(query.from_user.id):
                await query.answer("🔒 Admin access required", show_alert=True)
                return

            await state.clear()

            text = "<b>➕ Add Monitored Source</b>\n\n"
            text += "What type of source are you adding?\n\n"
            text += "📢 <b>Channel</b> - Monitors ALL posts from a channel\n"
            text += "👥 <b>Group</b> - Monitors SPECIFIC people in a group\n"
            text += "💬 <b>DM</b> - Monitors ALL messages from a DM"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📢 Channel", callback_data="gain_alerts:type:channel"),
                    InlineKeyboardButton(text="👥 Group", callback_data="gain_alerts:type:group")
                ],
                [InlineKeyboardButton(text="💬 DM", callback_data="gain_alerts:type:dm")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:menu")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error starting add source: {e}", exc_info=True)
            await query.answer("❌ Error starting add flow")
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def start_add_source" app/ui/handlers/gain_alerts.py
# Should return the method definition
```

#### Task 2.7: Write Gain Alerts Handler - Part 3 (Type Selection)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Append this content to the END of the file (inside the class):
```
```python
    async def handle_type_selection(self, query: types.CallbackQuery, state: FSMContext):
        """Handle chat type selection"""
        try:
            chat_type = query.data.split(':')[2]

            await state.update_data(chat_type=chat_type)
            await state.set_state(ManagementStates.gain_alerts_add_chat_id)

            type_info = {
                'channel': {
                    'emoji': '📢',
                    'name': 'Channel',
                    'id_format': 'Channel ID (negative):',
                    'example': '-1001234567890',
                    'validation': 'Must be negative and typically start with -100'
                },
                'group': {
                    'emoji': '👥',
                    'name': 'Group',
                    'id_format': 'Group ID (negative):',
                    'example': '-1001234567890',
                    'validation': 'Must be negative'
                },
                'dm': {
                    'emoji': '💬',
                    'name': 'DM',
                    'id_format': 'User ID (positive):',
                    'example': '123456789',
                    'validation': 'Must be positive'
                }
            }

            info = type_info[chat_type]

            text = f"<b>➕ Add {info['emoji']} {info['name']} Source</b>\n\n"
            text += f"Please enter the {info['id_format']}\n\n"
            text += f"<b>Example:</b> <code>{info['example']}</code>\n\n"
            text += f"💡 <i>{info['validation']}</i>"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:menu")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error handling type selection: {e}", exc_info=True)
            await query.answer("❌ Error processing type selection")
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def handle_type_selection" app/ui/handlers/gain_alerts.py
# Should return the method definition
```

#### Task 2.8: Write Gain Alerts Handler - Part 4 (Chat ID Input)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Append this content to the END of the file (inside the class):
```
```python
    async def process_chat_id_input(self, message: types.Message, state: FSMContext):
        """Process chat ID input from user"""
        try:
            data = await state.get_data()
            chat_type = data.get('chat_type')

            if not chat_type:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return

            # Parse and validate chat ID
            try:
                chat_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid ID. Please enter a valid number.")
                return

            # Validation based on type
            if chat_type == 'dm':
                if chat_id <= 0:
                    await message.reply("❌ DM user IDs must be positive numbers.")
                    return
            elif chat_type in ['channel', 'group']:
                if chat_id >= 0:
                    await message.reply(f"❌ {chat_type.title()} IDs must be negative numbers.")
                    return

            await state.update_data(chat_id=chat_id)

            # For groups, ask for user_id
            if chat_type == 'group':
                await state.set_state(ManagementStates.gain_alerts_add_user_id)

                text = "<b>➕ Add User to Monitor</b>\n\n"
                text += f"Group: <code>{chat_id}</code>\n\n"
                text += "Enter the User ID to monitor in this group:\n\n"
                text += "<b>Example:</b> <code>123456789</code>\n\n"
                text += "💡 <i>Must be positive</i>"

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:menu")]
                ])

                await message.reply(text, reply_markup=keyboard)
            else:
                # For channel/dm, go straight to confirmation
                await self.show_confirmation(message, state, chat_id, None, chat_type)

        except Exception as e:
            logger.error(f"Error processing chat ID input: {e}", exc_info=True)
            await message.reply("❌ Error processing input")
            await state.clear()
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def process_chat_id_input" app/ui/handlers/gain_alerts.py
# Should return the method definition
```

#### Task 2.9: Write Gain Alerts Handler - Part 5 (User ID Input for Groups)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Append this content to the END of the file (inside the class):
```
```python
    async def process_user_id_input(self, message: types.Message, state: FSMContext):
        """Process user ID input for group monitoring"""
        try:
            data = await state.get_data()
            chat_id = data.get('chat_id')
            chat_type = data.get('chat_type')

            if not chat_id or not chat_type:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return

            # Parse and validate user ID
            try:
                user_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid user ID. Please enter a valid number.")
                return

            if user_id <= 0:
                await message.reply("❌ User IDs must be positive numbers.")
                return

            # Show confirmation
            await self.show_confirmation(message, state, chat_id, user_id, chat_type)

        except Exception as e:
            logger.error(f"Error processing user ID input: {e}", exc_info=True)
            await message.reply("❌ Error processing input")
            await state.clear()

    async def show_confirmation(self, message: types.Message, state: FSMContext, chat_id: int, user_id: Optional[int], chat_type: str):
        """Show confirmation screen before adding monitored source"""
        try:
            type_emojis = {'group': '👥', 'channel': '📢', 'dm': '💬'}
            emoji = type_emojis.get(chat_type, '📡')

            text = "<b>✅ Confirm Monitored Source</b>\n\n"
            text += f"{emoji} <b>{chat_type.title()}</b>\n"
            text += f"Chat ID: <code>{chat_id}</code>\n"

            if user_id:
                text += f"Monitor User ID: <code>{user_id}</code>\n\n"
                text += "When this user posts a CA in this group, gain alerts will be sent to the same group."
            else:
                text += "\n"
                text += f"ALL messages with CAs in this {chat_type} will trigger gain alerts."

            await state.update_data(user_id=user_id)
            await state.set_state(ManagementStates.gain_alerts_add_confirm)

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Confirm", callback_data="gain_alerts:confirm"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:menu")
                ]
            ])

            await message.reply(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing confirmation: {e}", exc_info=True)
            await message.reply("❌ Error showing confirmation")
            await state.clear()
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def show_confirmation" app/ui/handlers/gain_alerts.py
# Should return the method definition
```

#### Task 2.10: Write Gain Alerts Handler - Part 6 (Confirm and Save)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Append this content to the END of the file (inside the class):
```
```python
    async def confirm_add_source(self, query: types.CallbackQuery, state: FSMContext):
        """Confirm and save monitored source to database"""
        try:
            data = await state.get_data()
            chat_id = data.get('chat_id')
            chat_type = data.get('chat_type')
            user_id = data.get('user_id')

            if not chat_id or not chat_type:
                await query.answer("❌ Session expired")
                await state.clear()
                return

            # Add to database
            source = await self.model.add_source(
                chat_id=chat_id,
                chat_type=chat_type,
                user_id=user_id,
                admin_id=query.from_user.id
            )

            type_emojis = {'group': '👥', 'channel': '📢', 'dm': '💬'}
            emoji = type_emojis.get(chat_type, '📡')

            text = f"✅ <b>Monitored Source Added!</b>\n\n"
            text += f"{emoji} <b>{chat_type.title()}</b>\n"
            text += f"Chat ID: <code>{chat_id}</code>\n"

            if user_id:
                text += f"Monitoring User: <code>{user_id}</code>\n\n"
            else:
                text += "\n"

            text += "Gain alerts will be sent when contract addresses are posted."

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 View All", callback_data="gain_alerts:menu")],
                [InlineKeyboardButton(text="➕ Add Another", callback_data="gain_alerts:add")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            await state.clear()

            logger.info(f"[GAIN_ALERTS] Added monitored source: chat={chat_id}, type={chat_type}, user={user_id}, admin={query.from_user.id}")

        except Exception as e:
            logger.error(f"Error confirming add source: {e}", exc_info=True)
            await query.answer("❌ Error adding source")
            await state.clear()
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def confirm_add_source" app/ui/handlers/gain_alerts.py
# Should return the method definition
```

#### Task 2.11: Write Gain Alerts Handler - Part 7 (Remove Flow)
```bash
# Open file: app/ui/handlers/gain_alerts.py

# Append this content to the END of the file (inside the class):
```
```python
    async def show_remove_menu(self, query: types.CallbackQuery):
        """Show list of monitored sources to remove"""
        try:
            if not self.is_admin(query.from_user.id):
                await query.answer("🔒 Admin access required", show_alert=True)
                return

            sources = await self.model.get_all_with_stats()

            if not sources:
                await query.answer("No monitored sources to remove")
                return

            text = "<b>🗑️ Remove Monitored Source</b>\n\n"
            text += "Select source to remove:\n"

            type_emojis = {'group': '👥', 'channel': '📢', 'dm': '💬'}

            keyboard_rows = []
            for source in sources:
                emoji = type_emojis.get(source['chat_type'], '📡')
                if source['user_id']:
                    label = f"{emoji} Chat {source['chat_id']} - User {source['user_id']} ({source['token_count']} tokens)"
                else:
                    label = f"{emoji} Chat {source['chat_id']} ({source['token_count']} tokens)"

                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=label[:64],  # Telegram button text limit
                        callback_data=f"gain_alerts:remove_confirm:{source['id']}"
                    )
                ])

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="gain_alerts:menu")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing remove menu: {e}", exc_info=True)
            await query.answer("❌ Error loading remove menu")

    async def confirm_remove_source(self, query: types.CallbackQuery):
        """Show confirmation before removing source"""
        try:
            source_id = int(query.data.split(':')[2])

            source = await self.model.get_by_id(source_id)
            if not source:
                await query.answer("❌ Source not found")
                return

            # Get token count
            stats = await self.db.fetchrow("""
                SELECT COUNT(*) as token_count
                FROM token_group_alerts
                WHERE chat_id = $1
                AND (original_user_id = $2 OR $2 IS NULL)
            """, source['chat_id'], source['user_id'])

            token_count = stats['token_count'] if stats else 0

            type_emojis = {'group': '👥', 'channel': '📢', 'dm': '💬'}
            emoji = type_emojis.get(source['chat_type'], '📡')

            text = "<b>⚠️ Confirm Removal</b>\n\n"
            text += f"{emoji} <b>{source['chat_type'].title()}</b>\n"
            text += f"Chat ID: <code>{source['chat_id']}</code>\n"

            if source['user_id']:
                text += f"User: <code>{source['user_id']}</code>\n"

            text += f"Tokens Tracked: {token_count}\n\n"
            text += "⚠️ <b>This will DELETE:</b>\n"
            text += "• Monitored source entry\n"
            text += f"• All {token_count} token tracking entries\n"
            text += "• All gain alert history\n\n"
            text += "❗ <b>This action CANNOT be undone!</b>"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚠️ Confirm Delete", callback_data=f"gain_alerts:delete:{source_id}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_alerts:remove")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error confirming remove: {e}", exc_info=True)
            await query.answer("❌ Error loading confirmation")

    async def delete_source(self, query: types.CallbackQuery):
        """Delete monitored source and related data"""
        try:
            source_id = int(query.data.split(':')[2])

            source = await self.model.get_by_id(source_id)
            if not source:
                await query.answer("❌ Source not found")
                return

            # Delete source (cascades to token_group_alerts via model)
            success = await self.model.remove_source(source_id)

            if success:
                text = "✅ <b>Monitored Source Removed</b>\n\n"
                text += f"Chat {source['chat_id']}"
                if source['user_id']:
                    text += f" - User {source['user_id']}"
                text += " removed successfully.\n\n"
                text += "All token tracking entries have been deleted."

                await query.answer("✅ Source deleted")

                logger.info(f"[GAIN_ALERTS] Removed monitored source: id={source_id}, chat={source['chat_id']}, user={source['user_id']}")
            else:
                text = "❌ <b>Delete Failed</b>\n\nCould not delete source."
                await query.answer("❌ Failed to delete")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 View All", callback_data="gain_alerts:menu")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error deleting source: {e}", exc_info=True)
            await query.answer("❌ Error deleting source")

    async def handle_callback(self, query: types.CallbackQuery, state: FSMContext):
        """Route callback queries to appropriate handlers"""
        try:
            parts = query.data.split(':')
            action = parts[1] if len(parts) > 1 else 'menu'

            if action == 'menu':
                await self.show_main_menu(query)
            elif action == 'add':
                await self.start_add_source(query, state)
            elif action == 'type':
                await self.handle_type_selection(query, state)
            elif action == 'confirm':
                await self.confirm_add_source(query, state)
            elif action == 'remove':
                await self.show_remove_menu(query)
            elif action == 'remove_confirm':
                await self.confirm_remove_source(query)
            elif action == 'delete':
                await self.delete_source(query)

        except Exception as e:
            logger.error(f"Error handling gain alerts callback: {e}", exc_info=True)
            await query.answer("❌ Error processing request")
```
```bash
# Save and close file

# Verification:
grep "async def handle_callback" app/ui/handlers/gain_alerts.py
# Should return the method definition

# Verify file has all methods:
grep "async def" app/ui/handlers/gain_alerts.py | wc -l
# Should return 13 (13 async methods defined)
```

#### Task 2.12: Add Gain Alerts Button to Settings Handler
```bash
# Open file: app/ui/handlers/settings.py

# Find the settings menu keyboard building section

# Add this button to the keyboard (after existing buttons):
```
```python
[InlineKeyboardButton(text="📈 Gain Alerts", callback_data="gain_alerts:menu")],
```
```bash
# Save file

# Verification:
grep "📈 Gain Alerts" app/ui/handlers/settings.py
# Should return the line
```

#### Task 2.12: Register Gain Alerts Handler in Management Bot
```bash
# Open file: app/management_bot.py

# Find where other handlers are initialized (look for SourcesHandler, TargetsHandler, etc)

# Add this import at the top:
```
```python
from app.ui.handlers.gain_alerts import GainAlertsHandler
```
```python
# Add initialization (where other handlers are initialized):
gain_alerts_handler = GainAlertsHandler(db, keyboards)
```
```python
# Find where callback handlers are registered

# Add these registrations:
```
```python
# Gain alerts callbacks
@dp.callback_query(lambda c: c.data and c.data.startswith('gain_alerts:'))
async def gain_alerts_callback(query: types.CallbackQuery, state: FSMContext):
    await gain_alerts_handler.handle_callback(query, state)

# Gain alerts message handlers (for FSM states)
@dp.message(ManagementStates.gain_alerts_add_chat_id)
async def gain_alerts_chat_id_input(message: types.Message, state: FSMContext):
    await gain_alerts_handler.process_chat_id_input(message, state)

@dp.message(ManagementStates.gain_alerts_add_user_id)
async def gain_alerts_user_id_input(message: types.Message, state: FSMContext):
    await gain_alerts_handler.process_user_id_input(message, state)
```
```bash
# Save and close file

# Verification:
grep "GainAlertsHandler" app/management_bot.py
# Should return the import and initialization

grep "gain_alerts_callback" app/management_bot.py
# Should return the callback handler
```

#### Task 2.14: Test Management Bot Startup
```bash
# Command to run:
python -m app.management_bot

# Expected output:
# Should start without errors
# No import errors
# No syntax errors

# If errors appear, STOP and fix before continuing

# Press Ctrl+C to stop after verifying startup
```

**PHASE 2 COMPLETE - Verify all 14 tasks marked DONE before proceeding**

---

### PHASE 3: Management Bot UI - Gain Alert Settings Section

#### Task 3.1: Add FSM States for Settings Editing
```bash
# Open file: app/ui/states.py

# Find ManagementStates class

# Add these lines INSIDE the class (after gain_alerts states):
```
```python
    # Gain Alert Settings states
    gain_settings_edit_gain_threshold = State()
    gain_settings_edit_drop_threshold = State()
    gain_settings_edit_drop_floor = State()
```
```bash
# Save and close file

# Verification:
grep "gain_settings_edit" app/ui/states.py | wc -l
# Should return 3
```

#### Task 3.2: Add Gain Alert Settings Handler to settings.py - Part 1
```bash
# Open file: app/ui/handlers/settings.py

# Find the end of the file

# Add this method to the SettingsHandler class:
```
```python
async def show_gain_alert_settings(self, query: types.CallbackQuery):
    """Show gain alert settings menu"""
    try:
        from app.config import get_gain_alert_settings

        # Load current settings
        settings = await get_gain_alert_settings()

        gain_threshold = settings['gain_threshold_pct'] * 100  # Convert to percentage
        drop_threshold = settings['drop_threshold_pct'] * 100
        drop_floor = settings['drop_floor_mc']

        text = "<b>⚙️ Gain Alert Settings</b>\n\n"
        text += "<b>Current Configuration:</b>\n\n"
        text += f"📈 <b>Gain Threshold:</b> {gain_threshold:.0f}%\n"
        text += f"   (Alert fires when token gains {gain_threshold:.0f}% from baseline)\n\n"
        text += f"📉 <b>Drop Threshold:</b> {drop_threshold:.0f}%\n"
        text += f"   (Stop tracking if token drops to {drop_threshold:.0f}% of first_seen_mc)\n\n"
        text += f"💰 <b>Drop Floor:</b> ${drop_floor:,.0f}\n"
        text += f"   (Absolute floor - stop tracking below this MC)\n"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📈 Edit Gain Threshold", callback_data="gain_settings:edit:gain")],
            [InlineKeyboardButton(text="📉 Edit Drop Threshold", callback_data="gain_settings:edit:drop")],
            [InlineKeyboardButton(text="💰 Edit Drop Floor", callback_data="gain_settings:edit:floor")],
            [InlineKeyboardButton(text="🔙 Back to Settings", callback_data="menu:settings")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing gain alert settings: {e}", exc_info=True)
        await query.answer("❌ Error loading settings")
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def show_gain_alert_settings" app/ui/handlers/settings.py
# Should return the method definition
```

#### Task 3.3: Add Settings Button to Main Settings Menu
```bash
# Open file: app/ui/handlers/settings.py

# Find the settings menu keyboard section

# Add this button (after Gain Alerts button):
```
```python
[InlineKeyboardButton(text="⚙️ Gain Alert Settings", callback_data="gain_settings:menu")],
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "⚙️ Gain Alert Settings" app/ui/handlers/settings.py
# Should return the line
```

#### Task 3.4: Add Edit Handlers - Part 2 (Start Edit)
```bash
# Open file: app/ui/handlers/settings.py

# Add this method to handle edit button clicks:
```
```python
async def start_edit_gain_setting(self, query: types.CallbackQuery, state: FSMContext):
    """Start editing a gain alert setting"""
    try:
        from app.config import get_gain_alert_settings

        setting_type = query.data.split(':')[2]  # 'gain', 'drop', or 'floor'

        settings = await get_gain_alert_settings()

        if setting_type == 'gain':
            current = settings['gain_threshold_pct'] * 100
            await state.set_state(ManagementStates.gain_settings_edit_gain_threshold)
            text = "<b>📈 Edit Gain Threshold</b>\n\n"
            text += f"Current: {current:.0f}%\n\n"
            text += "Enter new gain threshold percentage (1-1000):\n\n"
            text += "<b>Example:</b> 50 (for 50% gain alerts)\n\n"
            text += "💡 <i>Higher values = fewer but bigger gain alerts</i>"
        elif setting_type == 'drop':
            current = settings['drop_threshold_pct'] * 100
            await state.set_state(ManagementStates.gain_settings_edit_drop_threshold)
            text = "<b>📉 Edit Drop Threshold</b>\n\n"
            text += f"Current: {current:.0f}%\n\n"
            text += "Enter new drop threshold percentage (1-100):\n\n"
            text += "<b>Example:</b> 60 (stop tracking at 60% of peak)\n\n"
            text += "💡 <i>Lower values = more aggressive stop-loss</i>"
        elif setting_type == 'floor':
            current = settings['drop_floor_mc']
            await state.set_state(ManagementStates.gain_settings_edit_drop_floor)
            text = "<b>💰 Edit Drop Floor</b>\n\n"
            text += f"Current: ${current:,.0f}\n\n"
            text += "Enter new drop floor market cap (100-1000000):\n\n"
            text += "<b>Example:</b> 5000 (for $5,000 floor)\n\n"
            text += "💡 <i>Minimum MC before stopping tracking</i>"

        await state.update_data(setting_type=setting_type)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="gain_settings:menu")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error starting edit: {e}", exc_info=True)
        await query.answer("❌ Error starting edit")
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def start_edit_gain_setting" app/ui/handlers/settings.py
# Should return the method definition
```

#### Task 3.5: Add Edit Handlers - Part 3 (Process Input)
```bash
# Open file: app/ui/handlers/settings.py

# Add these methods to process user input:
```
```python
async def process_gain_threshold_input(self, message: types.Message, state: FSMContext):
    """Process gain threshold input"""
    try:
        # Parse input
        try:
            value = float(message.text.strip())
        except ValueError:
            await message.reply("❌ Invalid number. Please enter a number between 1 and 1000.")
            return

        # Validate range
        if not (1 <= value <= 1000):
            await message.reply("❌ Value must be between 1 and 1000.")
            return

        # Update database
        await self.db.execute("""
            INSERT INTO settings (key, value)
            VALUES ('gain_threshold_pct', $1)
            ON CONFLICT (key) DO UPDATE SET value = $1
        """, str(value / 100))  # Store as decimal

        text = f"✅ <b>Gain Threshold Updated</b>\n\n"
        text += f"New threshold: {value:.0f}%\n\n"
        text += f"Future alerts will fire when tokens gain {value:.0f}% from baseline."

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="gain_settings:menu")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        await message.reply(text, reply_markup=keyboard)
        await state.clear()

        logger.info(f"[GAIN_SETTINGS] Gain threshold updated to {value}% by user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error processing gain threshold input: {e}", exc_info=True)
        await message.reply("❌ Error updating setting")
        await state.clear()

async def process_drop_threshold_input(self, message: types.Message, state: FSMContext):
    """Process drop threshold input"""
    try:
        value = float(message.text.strip())

        if not (1 <= value <= 100):
            await message.reply("❌ Value must be between 1 and 100.")
            return

        await self.db.execute("""
            INSERT INTO settings (key, value)
            VALUES ('drop_threshold_pct', $1)
            ON CONFLICT (key) DO UPDATE SET value = $1
        """, str(value / 100))

        text = f"✅ <b>Drop Threshold Updated</b>\n\n"
        text += f"New threshold: {value:.0f}%\n\n"
        text += f"Tracking will stop if token drops to {value:.0f}% of peak MC."

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="gain_settings:menu")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        await message.reply(text, reply_markup=keyboard)
        await state.clear()

        logger.info(f"[GAIN_SETTINGS] Drop threshold updated to {value}% by user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error processing drop threshold input: {e}", exc_info=True)
        await message.reply("❌ Error updating setting")
        await state.clear()

async def process_drop_floor_input(self, message: types.Message, state: FSMContext):
    """Process drop floor input"""
    try:
        value = float(message.text.strip())

        if not (100 <= value <= 1_000_000):
            await message.reply("❌ Value must be between 100 and 1,000,000.")
            return

        await self.db.execute("""
            INSERT INTO settings (key, value)
            VALUES ('drop_floor_mc', $1)
            ON CONFLICT (key) DO UPDATE SET value = $1
        """, str(value))

        text = f"✅ <b>Drop Floor Updated</b>\n\n"
        text += f"New floor: ${value:,.0f}\n\n"
        text += f"Tracking will stop if token MC drops below ${value:,.0f}."

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Settings", callback_data="gain_settings:menu")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        await message.reply(text, reply_markup=keyboard)
        await state.clear()

        logger.info(f"[GAIN_SETTINGS] Drop floor updated to ${value:,.0f} by user {message.from_user.id}")

    except Exception as e:
        logger.error(f"Error processing drop floor input: {e}", exc_info=True)
        await message.reply("❌ Error updating setting")
        await state.clear()
```
```bash
# Save and close file

# Verification:
grep "async def process_gain_threshold_input" app/ui/handlers/settings.py
grep "async def process_drop_threshold_input" app/ui/handlers/settings.py
grep "async def process_drop_floor_input" app/ui/handlers/settings.py
# All three should return their method definitions
```

#### Task 3.6: Register Settings Callback Handlers
```bash
# Open file: app/management_bot.py

# Find where callbacks are registered

# Add this callback handler:
```
```python
# Gain alert settings callbacks
@dp.callback_query(lambda c: c.data and c.data.startswith('gain_settings:'))
async def gain_settings_callback(query: types.CallbackQuery, state: FSMContext):
    parts = query.data.split(':')
    action = parts[1] if len(parts) > 1 else 'menu'

    if action == 'menu':
        await settings_handler.show_gain_alert_settings(query)
    elif action == 'edit':
        await settings_handler.start_edit_gain_setting(query, state)

# Gain settings message handlers
@dp.message(ManagementStates.gain_settings_edit_gain_threshold)
async def gain_settings_gain_input(message: types.Message, state: FSMContext):
    await settings_handler.process_gain_threshold_input(message, state)

@dp.message(ManagementStates.gain_settings_edit_drop_threshold)
async def gain_settings_drop_input(message: types.Message, state: FSMContext):
    await settings_handler.process_drop_threshold_input(message, state)

@dp.message(ManagementStates.gain_settings_edit_drop_floor)
async def gain_settings_floor_input(message: types.Message, state: FSMContext):
    await settings_handler.process_drop_floor_input(message, state)
```
```bash
# Save and close file

# Verification:
grep "gain_settings_callback" app/management_bot.py
# Should return the callback handler
```

**PHASE 3 COMPLETE - Verify all 6 tasks marked DONE before proceeding**

---

### PHASE 4: Userbot Handler - Monitored Source Detection

#### Task 4.1: Add Monitored Source Check to Userbot Handler
```bash
# Open file: app/userbot/handlers.py

# Find the main message handler (@client.on(events.NewMessage))

# Add this code at the BEGINNING of the handler (before forwarding logic):
```
```python
# Check for monitored sources (gain alert system)
monitored = await db.fetchrow("""
    SELECT * FROM monitored_sources
    WHERE chat_id = $1
    AND (user_id = $2 OR user_id IS NULL)
""", event.chat_id, event.sender_id)

if monitored:
    # For groups: verify user_id match
    if monitored['chat_type'] == 'group' and monitored['user_id'] != event.sender_id:
        pass  # Different person in group, continue to forwarding logic
    else:
        # This is a monitored message - process for gain alerts
        from app.userbot.token_monitor import TokenMonitor

        monitor = TokenMonitor(userbot_id=userbot.id)
        await monitor.process_monitored_source_message(event, monitored)
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "monitored_sources" app/userbot/handlers.py
# Should return the SQL query
```

#### Task 4.2: Add process_monitored_source_message to TokenMonitor
```bash
# Open file: app/userbot/token_monitor.py

# Add this method to the TokenMonitor class:
```
```python
async def process_monitored_source_message(self, event, monitored_source: Dict[str, Any]):
    """Process message from a monitored source for gain alerts"""
    try:
        message = event.message
        text = self.utils.get_message_text(message)

        if not text:
            return

        # Extract token addresses
        tagged_addresses = self.utils.extract_token_addresses(text)

        if not tagged_addresses:
            return

        logger.debug(f"[MONITOR_DETECT] Found {len(tagged_addresses)} addresses in monitored source {monitored_source['chat_id']}")

        # Process each token for gain alert tracking
        for address, blockchain in tagged_addresses:
            await self._process_monitored_token(
                address=address,
                blockchain=blockchain,
                chat_id=event.chat_id,
                message_id=event.message.id,
                user_id=event.sender_id
            )

    except Exception as e:
        logger.error(f"Error processing monitored source message: {e}", exc_info=True)
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "async def process_monitored_source_message" app/userbot/token_monitor.py
# Should return the method definition
```

#### Task 4.3: Add _process_monitored_token Method
```bash
# Open file: app/userbot/token_monitor.py

# Add this method to the TokenMonitor class:
```
```python
async def _process_monitored_token(self, address: str, blockchain: str, chat_id: int, message_id: int, user_id: int):
    """Process a single token from monitored source"""
    try:
        from app.dex import get_dex_service
        from app.services.jupiter_api import get_jupiter_service
        from app.config import MIN_VALID_MARKET_CAP, MAX_VALID_MARKET_CAP
        from decimal import Decimal

        # Check if token already exists
        token = await db.fetchrow("SELECT id FROM tokens_tracked WHERE address = $1", address)

        if not token:
            # New token - add via dex service
            dex_service = get_dex_service()
            result = await dex_service.add_token(address)

            if not result['success']:
                logger.info(f"[MONITOR_DETECT] Skipping {address}: {result.get('error', 'unknown error')}")
                return

            token_id = result.get('token_id')
            if not token_id:
                logger.warning(f"[MONITOR_DETECT] No token_id returned for {address}")
                return
        else:
            token_id = token['id']

        # Check if this chat is already tracking this token
        existing = await db.fetchrow("""
            SELECT id FROM token_group_alerts
            WHERE token_id = $1 AND chat_id = $2
        """, token_id, chat_id)

        if existing:
            logger.debug(f"[GROUP_ALERT_DUP] Chat {chat_id} already tracking token {address}")
            return

        # Fetch current market cap
        jupiter_service = get_jupiter_service()
        okx_client = self.okx_client

        market_cap: Optional[Decimal] = None

        if blockchain == "SOL":
            token_data = await jupiter_service.get_token_data(address, use_cache=False)
            if token_data:
                okx_info = await okx_client.fetch_token_info(address, blockchain)
                if okx_info:
                    market_cap = okx_client.get_market_cap(okx_info)
                if market_cap is None:
                    market_cap = jupiter_service.get_market_cap(token_data)
        else:
            okx_info = await okx_client.fetch_token_info(address, blockchain)
            if okx_info:
                market_cap = okx_client.get_market_cap(okx_info)
            if market_cap is None:
                token_data = await jupiter_service.get_token_data(address, use_cache=False)
                market_cap = jupiter_service.get_market_cap(token_data) if token_data else None

        # Validate market cap
        if not market_cap or market_cap < Decimal(MIN_VALID_MARKET_CAP) or market_cap > Decimal(MAX_VALID_MARKET_CAP):
            logger.warning(f"[MONITOR_DETECT] Invalid MC for {address}: ${float(market_cap) if market_cap else 0:,.2f}")
            return

        # Create group-specific alert tracking
        await db.execute("""
            INSERT INTO token_group_alerts
            (token_id, chat_id, first_seen_mc, original_message_id, original_user_id)
            VALUES ($1, $2, $3, $4, $5)
        """, token_id, chat_id, market_cap, message_id, user_id)

        logger.info(f"[GROUP_ALERT_NEW] {address} tracking started for chat {chat_id} at MC ${float(market_cap):,.2f}")

    except Exception as e:
        logger.error(f"Error processing monitored token {address}: {e}", exc_info=True)
```
```bash
# Save and close file

# Verification:
grep "async def _process_monitored_token" app/userbot/token_monitor.py
# Should return the method definition
```

**PHASE 4 COMPLETE - Verify all 3 tasks marked DONE before proceeding**

---

### PHASE 5: Alert Dispatch - Per-Group Baselines

#### Task 5.1: Update _dispatch_gain_alert in dex.py
```bash
# Open file: app/dex.py

# Find the _dispatch_gain_alert method

# REPLACE the entire method with this:
```
```python
async def _dispatch_gain_alert(self, token_id: int, address: str, current_mc: Decimal, ticker: str):
    """Dispatch gain alerts to all groups tracking this token"""
    try:
        # Get all groups tracking this token
        tracking_groups = await db.fetch("""
            SELECT chat_id, original_message_id, first_seen_mc, last_alert_mc, original_user_id
            FROM token_group_alerts
            WHERE token_id = $1
        """, token_id)

        if not tracking_groups:
            logger.debug(f"[GROUP_ALERT_FIRE] No groups tracking {address}")
            return

        # Load global threshold
        from app.config import get_gain_alert_settings
        settings = await get_gain_alert_settings()
        gain_threshold = Decimal(str(settings['gain_threshold_pct']))

        for group in tracking_groups:
            # Calculate per-group baseline
            baseline_mc = group['last_alert_mc'] if group['last_alert_mc'] else group['first_seen_mc']
            gain_pct = (current_mc - baseline_mc) / baseline_mc

            if gain_pct >= gain_threshold:
                # Build alert message
                alert_msg = self._build_gain_alert_message(
                    ticker=ticker,
                    address=address,
                    current_mc=current_mc,
                    gain_pct=gain_pct * 100
                )

                # Persist to alert_queue
                alert_id = await db.fetchval("""
                    INSERT INTO alert_queue
                    (token_id, token_address, alert_message, target_chat_id, reply_to_message_id, status)
                    VALUES ($1, $2, $3, $4, $5, 'pending')
                    RETURNING id
                """, token_id, address, alert_msg, group['chat_id'], group['original_message_id'])

                # Send alert
                try:
                    # Get appropriate userbot for this chat
                    userbot = await self._get_userbot_for_chat(group['chat_id'])

                    if not userbot:
                        logger.warning(f"[GROUP_ALERT_FIRE] No userbot available for chat {group['chat_id']}")
                        await db.execute("UPDATE alert_queue SET status = 'failed', error = $1 WHERE id = $2",
                                       "No userbot available", alert_id)
                        continue

                    await userbot.send_message(
                        entity=group['chat_id'],
                        message=alert_msg,
                        reply_to=group['original_message_id']
                    )

                    # Update alert_queue status
                    await db.execute("UPDATE alert_queue SET status = 'sent' WHERE id = $1", alert_id)

                    # Update baseline for this group
                    await db.execute("""
                        UPDATE token_group_alerts
                        SET last_alert_mc = $1
                        WHERE token_id = $2 AND chat_id = $3
                    """, current_mc, token_id, group['chat_id'])

                    logger.info(f"[GROUP_ALERT_FIRE] {address} alert sent to chat {group['chat_id']}, baseline updated to ${float(current_mc):,.2f}")

                except Exception as e:
                    logger.error(f"[GROUP_ALERT_FIRE] Failed to send alert to chat {group['chat_id']}: {e}")
                    await db.execute("UPDATE alert_queue SET status = 'failed', error = $1 WHERE id = $2",
                                   str(e), alert_id)

    except Exception as e:
        logger.error(f"Error dispatching gain alert for {address}: {e}", exc_info=True)
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "token_group_alerts" app/dex.py
# Should return the SQL query
```

#### Task 5.2: Add _build_gain_alert_message Helper Method
```bash
# Open file: app/dex.py

# Check if _build_gain_alert_message method exists

# If it does NOT exist, add this method:
```
```python
def _build_gain_alert_message(self, ticker: str, address: str, current_mc: Decimal, gain_pct: Decimal) -> str:
    """Build gain alert message text"""
    from app.config import settings
    import datetime

    # Get blockchain from address format
    blockchain = "SOL" if len(address) < 44 else "BNB"

    msg = "🚀 <b>GAIN ALERT</b>\n\n"
    msg += f"<b>{ticker}</b> ({blockchain})\n"
    msg += f"CA: <code>{address}</code>\n\n"
    msg += f"💰 Current MC: <b>${float(current_mc):,.2f}</b>\n"
    msg += f"📈 Gain: <b>+{float(gain_pct):.1f}%</b>\n"
    msg += f"⏰ {datetime.datetime.now(settings.tz).strftime('%H:%M:%S')}\n"

    return msg
```
```bash
# Save file (DO NOT CLOSE YET)

# Verification:
grep "def _build_gain_alert_message" app/dex.py
# Should return the method definition
```

#### Task 5.3: Add _get_userbot_for_chat Helper Method
```bash
# Open file: app/dex.py

# Add this method to get userbot for a chat:
```
```python
async def _get_userbot_for_chat(self, chat_id: int):
    """Get an appropriate userbot client for sending messages to this chat"""
    try:
        from app.userbot.manager import get_userbot_manager

        manager = get_userbot_manager()

        # Try to get first available active userbot
        for userbot in manager.userbots.values():
            if userbot.is_active:
                return userbot.client

        logger.warning(f"No active userbots available for chat {chat_id}")
        return None

    except Exception as e:
        logger.error(f"Error getting userbot for chat {chat_id}: {e}")
        return None
```
```bash
# Save and close file

# Verification:
grep "async def _get_userbot_for_chat" app/dex.py
# Should return the method definition
```

**PHASE 5 COMPLETE - Verify all 3 tasks marked DONE before proceeding**

---

### PHASE 6: Testing & Validation

#### Task 6.1: Test Database Migration
```bash
# Verify tables exist:
psql $SUPABASE_POOLER_URL -c "SELECT COUNT(*) FROM monitored_sources;"
psql $SUPABASE_POOLER_URL -c "SELECT COUNT(*) FROM token_group_alerts;"

# Should return 0 for both (empty tables)
```

#### Task 6.2: Test Management Bot - Add Monitored Source
```bash
# Start management bot:
python -m app.management_bot

# In Telegram:
# 1. Send /start to management bot
# 2. Click Settings
# 3. Click "📈 Gain Alerts"
# 4. Click "➕ Add Monitored Source"
# 5. Select Group
# 6. Enter a test chat ID (negative number)
# 7. Enter a test user ID (positive number)
# 8. Click Confirm

# Expected: Success message, entry added to database

# Verify in database:
psql $SUPABASE_POOLER_URL -c "SELECT * FROM monitored_sources;"
# Should show your test entry
```

#### Task 6.3: Test Management Bot - View Monitored Sources
```bash
# In Telegram:
# 1. Click "📈 Gain Alerts"
# 2. Should see your monitored source listed with 0 tokens tracked

# Expected: List shows correctly with stats
```

#### Task 6.4: Test Management Bot - Remove Monitored Source
```bash
# In Telegram:
# 1. Click "🗑️ Remove Monitored Source"
# 2. Select your test source
# 3. Click "⚠️ Confirm Delete"

# Expected: Success message

# Verify in database:
psql $SUPABASE_POOLER_URL -c "SELECT COUNT(*) FROM monitored_sources;"
# Should return 0
```

#### Task 6.5: Test Gain Alert Settings
```bash
# In Telegram:
# 1. Click Settings → "⚙️ Gain Alert Settings"
# 2. Should see current values (30%, 70%, $8000)
# 3. Click "📈 Edit Gain Threshold"
# 4. Enter "50"
# 5. Should see success message

# Verify in database:
psql $SUPABASE_POOLER_URL -c "SELECT * FROM settings WHERE key = 'gain_threshold_pct';"
# Should show value = '0.5'
```

#### Task 6.6: Test End-to-End (Brand New Token)
```bash
# Setup:
# 1. Add monitored source (user in group)
# 2. Start userbot: python -m app.userbot.main
# 3. Start dex service: python -m app.dex

# Action:
# 1. Have monitored user post a token CA in the group

# Expected:
# - Userbot detects message
# - Creates token_group_alerts entry
# - Token added to tokens_tracked
# - When token gains 30% (or your threshold), alert fires
# - Alert replies to original message

# Verify logs:
# Should see [MONITOR_DETECT], [GROUP_ALERT_NEW], [GROUP_ALERT_FIRE]
```

#### Task 6.7: Test Duplicate Token Handling
```bash
# Setup: Existing token being tracked in Group1

# Action:
# 1. Have same user post same token again in Group1

# Expected:
# - Userbot detects message
# - Sees token_group_alerts entry exists
# - Logs [GROUP_ALERT_DUP]
# - Does NOT create duplicate entry

# Verify in database:
psql $SUPABASE_POOLER_URL -c "SELECT COUNT(*) FROM token_group_alerts WHERE token_id = X AND chat_id = Y;"
# Should return 1 (not 2)
```

#### Task 6.8: Test Independent Baselines
```bash
# Setup:
# - Token ABC tracked in Group1 from $5K
# - Token ABC currently at $20K
# - Add monitored source for Group2

# Action:
# - Have user post ABC in Group2

# Expected:
# - Group2 tracking starts at $20K
# - Group1 baseline remains at $5K (or last alert)
# - Both groups get alerts independently

# Verify in database:
psql $SUPABASE_POOLER_URL -c "SELECT chat_id, first_seen_mc FROM token_group_alerts WHERE token_id = X;"
# Should show different first_seen_mc values
```

**PHASE 6 COMPLETE - All features tested and validated**

---

## Final Verification Checklist

**Database:**
- [ ] monitored_sources table exists with correct schema
- [ ] token_group_alerts table exists with correct schema
- [ ] All indexes created
- [ ] UNIQUE constraints work
- [ ] Foreign key cascades work

**Management Bot:**
- [ ] "📈 Gain Alerts" menu appears in Settings
- [ ] Add monitored source works (all 3 types)
- [ ] View monitored sources shows stats correctly
- [ ] Remove monitored source deletes data
- [ ] "⚙️ Gain Alert Settings" menu appears
- [ ] Edit gain threshold works
- [ ] Edit drop threshold works
- [ ] Edit drop floor works
- [ ] Admin-only access enforced

**Userbot:**
- [ ] Monitored source detection works
- [ ] Token extraction works (SOL/BNB)
- [ ] token_group_alerts entries created
- [ ] Duplicate detection works
- [ ] MC validation works

**Alert Dispatch:**
- [ ] Alerts query token_group_alerts
- [ ] Per-group baselines calculated correctly
- [ ] Alerts sent to correct chats
- [ ] Alerts reply to original message
- [ ] Baselines update after alerts
- [ ] alert_queue persistence works

**End-to-End:**
- [ ] Brand new token flow works
- [ ] Existing token, new group works
- [ ] Same token, same group, different people works
- [ ] Channel monitoring works (if applicable)
- [ ] Remove source deletes all tracking

---

## Backward Compatibility

### What Stays Unchanged
- Forwarding system (source→target) continues working
- Tier-based polling system unchanged
- `tokens_tracked` schema unchanged
- Stop-loss logic unchanged
- Alert message format unchanged

### What Changes
- Gain alerts NO LONGER trigger from forwarded messages
- Gain alerts ONLY trigger from monitored people/channels/DMs
- Alert routing uses `token_group_alerts` instead of `source_group_id`

### Migration Path
1. Deploy schema changes (migration 064)
2. Configure monitored sources via management bot
3. Gain alerts will start working from monitored sources
4. Old forwarding continues but doesn't trigger alerts
5. Optional: Keep forwarding for non-alert purposes, or disable entirely

---

## Operational Notes

### Logging Prefixes
```python
[MONITOR_DETECT] - Monitored source detected token
[GROUP_ALERT_NEW] - New group started tracking token
[GROUP_ALERT_DUP] - Group already tracking, ignored
[GROUP_ALERT_FIRE] - Alert sent to specific group
```

### Admin Commands (Future Enhancement)
- `/monitor_stats` - Global stats across all monitored sources
- `/token_groups <address>` - Show all groups tracking a token
- `/group_tokens <chat_id>` - Show all tokens tracked by a group

### Performance Considerations
- `token_group_alerts` table grows with (unique tokens × groups tracking)
- Index on `(token_id, chat_id)` ensures fast duplicate checks
- Alert dispatch loops through all tracking groups per token
- Consider pagination if single token tracked by 100+ groups

---

## Acceptance Criteria

### Schema
- [ ] Migration 064 creates `monitored_sources` table
- [ ] Migration 064 creates `token_group_alerts` table
- [ ] All indexes created successfully
- [ ] Foreign key constraints working

### Management Bot
- [ ] Add monitored source flow works (group/channel/dm)
- [ ] User ID input validation for groups
- [ ] View command shows correct stats
- [ ] Remove command performs hard delete
- [ ] Admin-only access enforced
- [ ] Buttons navigate correctly

### Userbot
- [ ] Monitored person in group triggers detection
- [ ] Channel monitoring detects all messages
- [ ] DM monitoring detects all messages
- [ ] Duplicate token-group combinations ignored
- [ ] Token extraction (SOL/BNB) works
- [ ] MC validation rejects invalid values

### Alert System
- [ ] Alerts sent to correct groups
- [ ] Each group uses independent baseline
- [ ] Replies to original_message_id
- [ ] Baseline updates after alert fires
- [ ] Multiple groups receive independent alerts
- [ ] Same group ignores duplicate tokens

### End-to-End Tests
- [ ] Test Example 1: Brand new token
- [ ] Test Example 2: Existing token, new group
- [ ] Test Example 3: Same token, same group, different people
- [ ] Test Example 4: Channel monitoring
- [ ] Test Example 5: Multiple people, same group, same token

---

## Future Enhancements

### Priority 1
- Alert retry worker for failed `alert_queue` entries
- Metrics/monitoring (Prometheus counters)
- Unit tests for alert threshold logic

### Priority 2
- Per-group gain threshold configuration (instead of global 30%)
- Custom alert message templates per group
- Alert history/log table for audit trail

### Priority 3
- Web dashboard for monitoring
- Bulk import/export of monitored sources
- Rate limiting per monitored source
