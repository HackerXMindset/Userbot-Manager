# Chart Alert Feature Implementation Plan

## Overview
Add chart image attachment to gain alerts by posting CA in random groups, waiting for chart bot reply, and attaching the image when MC exceeds threshold.

---

## Phase 1: Database Schema & Migrations

### 1.1 Global Chart Settings
**File:** `migrations/068_add_chart_request_groups.sql`

```sql
-- Store list of groups where we can post CA requests
CREATE TABLE IF NOT EXISTS chart_request_groups (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL UNIQUE,
    label TEXT,
    added_at TIMESTAMP DEFAULT NOW()
);
```

### 1.2 Per-Source Chart Settings
**File:** `migrations/069_add_monitored_source_chart_settings.sql`

```sql
-- Add chart-related columns to monitored_sources
ALTER TABLE monitored_sources
ADD COLUMN chart_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN chart_bot_id BIGINT,
ADD COLUMN chart_mc_threshold NUMERIC(20, 2) DEFAULT 100000.00;

-- Index for chart bot queries
CREATE INDEX idx_monitored_sources_chart_bot ON monitored_sources(chart_bot_id) WHERE chart_bot_id IS NOT NULL;
```

**Acceptance:**
- Run migrations on test DB
- Verify columns exist with correct defaults
- Confirm chart_enabled defaults to FALSE

---

## Phase 2: Chart Fetching Core Logic

### 2.1 Chart Request Handler
**File:** `app/chart_fetcher.py` (new file)

**Responsibilities:**
- Post CA to random group with random userbot via Telethon
- Listen for reply from specific chart bot ID
- Wait up to 60 seconds for reply
- Download photo from reply message as bytes (in-memory)
- Return photo bytes or None on timeout

**Photo Handling Strategy:**
- **In-memory approach:** Telethon downloads photo → returns bytes → aiogram sends bytes
- **NO temp files:** Avoids disk I/O and cleanup complexity
- **Concurrent safe:** Each request tracked by unique message_id with separate asyncio.Future
- Gain alerts are posted as replies, so cannot use message forwarding

**Key Functions:**
```python
class ChartFetcher:
    def __init__(self, db_pool, userbot_manager):
        self.db = db_pool
        self.userbot_manager = userbot_manager
        self._pending_requests = {}  # {message_id: asyncio.Future[bytes]}

    async def fetch_chart_for_token(
        self,
        contract_address: str,
        chart_bot_id: int,
        timeout: int = 60
    ) -> Optional[bytes]:
        """
        Post CA to random group, wait for chart bot reply.
        Returns: photo bytes or None on timeout/error

        Flow:
        1. Pick random chart request group
        2. Pick random available userbot
        3. Post raw CA text to group via Telethon
        4. Store (message_id → Future) in _pending_requests
        5. Wait for chart bot to reply (max 60s)
        6. Download photo bytes from reply
        7. Return bytes or None
        """
        pass

    async def _get_random_chart_group(self) -> Optional[int]:
        """Pick random group from chart_request_groups table"""
        pass

    async def _post_ca_with_random_userbot(
        self,
        chat_id: int,
        contract_address: str
    ) -> Optional[Tuple[int, int]]:
        """
        Post raw CA using random available userbot via Telethon.
        Returns: (chat_id, message_id) or None
        """
        pass

    async def handle_chart_bot_reply(
        self,
        message,
        chart_bot_id: int
    ):
        """
        Called by userbot message handler when chart bot replies.

        1. Check if message.reply_to_msg_id exists in _pending_requests
        2. If yes, download first photo as bytes via message.download_media(file=bytes)
        3. Resolve the Future with photo bytes
        4. Clean up _pending_requests entry
        """
        pass
```

**Concurrent Request Handling:**
Multiple gain alerts can trigger simultaneously without collision:

```
Alert A (Token 0x123) → post CA → message_id=1001 → _pending_requests[1001] = Future_A
Alert B (Token 0xabc) → post CA → message_id=1002 → _pending_requests[1002] = Future_B

Chart bot replies to 1001 → downloads photo_bytes_A → Future_A.set_result(photo_bytes_A)
Chart bot replies to 1002 → downloads photo_bytes_B → Future_B.set_result(photo_bytes_B)

Alert A sends with photo_bytes_A
Alert B sends with photo_bytes_B
```

Each request is isolated by message_id, so there's no cross-contamination.

**Edge Cases:**
- No chart request groups configured → return None
- No userbots available → return None
- Timeout (60s) → return None
- Chart bot replies without photo → return None
- Multiple photos in reply → use first one

**Logging:**
- `[CHART_FETCH]` prefix for all chart-related logs
- Log CA, group_id, userbot_id, chart_bot_id, success/timeout

**Acceptance:**
- Unit test: successful chart fetch
- Unit test: timeout scenario
- Unit test: no groups/userbots available

---

## Phase 3: Model Layer Updates

### 3.1 MonitoredSourceModel Extensions
**File:** `app/models/monitored_source.py`

**New Methods:**
```python
async def get_chart_settings(self, source_id: int) -> Optional[Dict]:
    """
    Returns {
        'chart_enabled': bool,
        'chart_bot_id': int or None,
        'chart_mc_threshold': Decimal
    }
    """
    pass

async def set_chart_enabled(self, source_id: int, enabled: bool):
    """Toggle chart alerts for source"""
    pass

async def set_chart_bot_id(self, source_id: int, bot_id: Optional[int]):
    """Assign chart bot to source"""
    pass

async def set_chart_mc_threshold(self, source_id: int, threshold: Optional[Decimal]):
    """Set MC threshold for charts (None = use default 100k)"""
    pass
```

### 3.2 Chart Request Groups Model
**File:** `app/models/chart_request_group.py` (new file)

```python
class ChartRequestGroupModel:
    def __init__(self, db_pool):
        self.db = db_pool

    async def list_all(self) -> List[Dict]:
        """Return all chart request groups"""
        pass

    async def add_group(self, chat_id: int, label: Optional[str] = None):
        """Add new chart request group"""
        pass

    async def remove_group(self, chat_id: int) -> bool:
        """Remove chart request group"""
        pass

    async def get_random_group(self) -> Optional[int]:
        """Pick random group chat_id"""
        pass
```

**Acceptance:**
- CRUD operations work correctly
- get_random_group returns None when no groups exist
- Duplicate chat_id raises UniqueViolationError

---

## Phase 4: Global Chart Settings UI

### 4.1 Main Gain Alerts Menu Update
**File:** `app/ui/handlers/gain_alerts.py`

**Changes:**
- Add "⚙️ Chart Request Groups" button to main menu
- Shows count of configured groups

### 4.2 Chart Request Groups Screen
**New Handler Methods:**

```python
async def show_chart_groups_menu(self, query: CallbackQuery):
    """
    Display list of chart request groups with add/remove options.

    Format:
    <b>📊 Chart Request Groups</b>

    Groups where bot can post CA to fetch charts:
    • Group -1001234567890 (Label)
    • Group -1009876543210

    [➕ Add Group] [🔙 Back]
    """
    pass

async def start_add_chart_group(self, query: CallbackQuery, state: FSMContext):
    """Prompt for chat_id input"""
    pass

async def handle_chart_group_input(self, message: Message, state: FSMContext):
    """Validate and add chat_id"""
    pass

async def remove_chart_group(self, query: CallbackQuery, chat_id: int):
    """Remove group with confirmation"""
    pass
```

**FSM States (add to ManagementStates):**
- `chart_groups_add_chat_id`

**Router Updates:**
**File:** `app/ui/routers/gain_alerts.py`
- `gain_alerts:chart_groups:menu`
- `gain_alerts:chart_groups:add`
- `gain_alerts:chart_groups:remove:<chat_id>`

**Acceptance:**
- Can add/remove chart request groups via UI
- Input validation works (must be negative integer for groups)
- Menu shows current list with counts

---

## Phase 5: Per-Source Chart Settings UI

### 5.1 Source Detail View Updates
**File:** `app/ui/handlers/gain_alerts.py`

**Changes to `_format_source_detail`:**
Add new section after "Sender":

```
<b>Chart Alerts</b>
• Status: ✅ Enabled / ⛔️ Disabled
• MC Threshold: $100,000 (or custom value)
• Chart Bot: @ChartBotName (ID: 123456)
```

**New Keyboard Buttons in `_build_source_detail_keyboard`:**
```python
[
    InlineKeyboardButton(
        text="📊 Chart Settings",
        callback_data=f"gain_alerts:view:chart_settings:{chat_id}"
    )
]
```

### 5.2 Chart Settings Sub-Menu
**New Handler:**

```python
async def show_chart_settings_menu(self, query: CallbackQuery, chat_id: int):
    """
    <b>📊 Chart Alert Settings</b>

    Current Status: ✅ Enabled
    MC Threshold: $100,000
    Chart Bot ID: 123456789

    [Toggle On/Off]
    [Set MC Threshold]
    [Set Chart Bot ID]
    [🔙 Back to Detail]
    """
    pass

async def toggle_chart_enabled(self, query: CallbackQuery, chat_id: int):
    """Flip chart_enabled flag"""
    pass

async def start_edit_chart_threshold(self, query: CallbackQuery, state: FSMContext, chat_id: int):
    """Prompt for MC threshold input"""
    pass

async def handle_chart_threshold_input(self, message: Message, state: FSMContext):
    """
    Accept formats:
    - 100000 or 100k → $100,000
    - 1.5m → $1,500,000
    - default → reset to $100k
    """
    pass

async def start_edit_chart_bot(self, query: CallbackQuery, state: FSMContext, chat_id: int):
    """Prompt for chart bot ID (integer)"""
    pass

async def handle_chart_bot_input(self, message: Message, state: FSMContext):
    """Validate and save chart bot ID"""
    pass
```

**FSM States (add to ManagementStates):**
- `gain_alerts_edit_chart_threshold`
- `gain_alerts_edit_chart_bot`

**Router Callbacks:**
- `gain_alerts:view:chart_settings:<chat_id>`
- `gain_alerts:view:chart_toggle:<chat_id>`
- `gain_alerts:view:chart_threshold:<chat_id>`
- `gain_alerts:view:chart_bot:<chat_id>`

**Acceptance:**
- Chart settings menu accessible from source detail
- Can toggle chart alerts on/off
- Can set custom MC threshold (with k/m suffix support)
- Can set chart bot ID
- Settings persist and display correctly

---

## Phase 6: Integration with Gain Alert System

### 6.1 Gain Alert Posting Logic Update
**File:** `app/userbot/token_monitor.py` (or wherever gain alerts are posted)

**Integration Point:**
Modify the gain alert posting function to:

1. Check if current MC > chart_mc_threshold AND chart_enabled = TRUE
2. If yes, call `ChartFetcher.fetch_chart_for_token(ca, chart_bot_id)`
3. If photo returned, attach to gain alert message
4. If None (timeout/error), send gain alert without photo
5. Log outcome with `[CHART_ALERT]` prefix

**Pseudocode:**
```python
async def send_gain_alert(token_data, monitored_source):
    # Existing template formatting logic...
    alert_text = format_alert_template(...)

    photo_file_id = None
    current_mc = token_data.get('current_market_cap')

    # Check if chart alerts enabled
    chart_settings = await monitored_source_model.get_chart_settings(source_id)
    if (chart_settings['chart_enabled'] and
        chart_settings['chart_bot_id'] and
        current_mc >= chart_settings['chart_mc_threshold']):

        logger.info(
            f"[CHART_ALERT] Fetching chart for {token_data['address']} "
            f"(MC: ${current_mc}, threshold: ${chart_settings['chart_mc_threshold']})"
        )

        chart_fetcher = ChartFetcher(db_pool, userbot_manager)
        photo_file_id = await chart_fetcher.fetch_chart_for_token(
            contract_address=token_data['address'],
            chart_bot_id=chart_settings['chart_bot_id'],
            timeout=60
        )

        if photo_file_id:
            logger.info(f"[CHART_ALERT] Chart fetched successfully: {photo_file_id}")
        else:
            logger.warning(f"[CHART_ALERT] Chart fetch timeout/failed for {token_data['address']}")

    # Send alert (with or without photo)
    if photo_file_id:
        await bot.send_photo(
            chat_id=target_chat_id,
            photo=photo_file_id,
            caption=alert_text,
            parse_mode="HTML"
        )
    else:
        await bot.send_message(
            chat_id=target_chat_id,
            text=alert_text,
            parse_mode="HTML"
        )
```

### 6.2 Userbot Message Handler Update
**File:** `app/userbot/handlers.py` (or relevant userbot message handler)

**Add Chart Bot Reply Detection:**
```python
@userbot_client.on(events.NewMessage())
async def handle_incoming_message(event):
    # Existing message handling...

    # Check if this is a reply from a chart bot
    if event.message.reply_to_msg_id and event.sender_id:
        # Notify ChartFetcher if this is a pending chart request
        await chart_fetcher.handle_chart_bot_reply(
            message=event.message,
            chart_bot_id=event.sender_id
        )
```

**Acceptance:**
- Gain alerts with MC > threshold include chart photo
- Gain alerts with MC < threshold do NOT fetch charts
- Timeout cases send alert without photo (no blocking)
- Chart disabled sources never fetch charts
- Logs show chart fetch attempts and outcomes

---

## Testing Checklist

### Phase 1
- [ ] Migrations run successfully
- [ ] Default values correct
- [ ] Indexes created

### Phase 2
- [ ] Chart fetch returns photo on success
- [ ] Chart fetch returns None on timeout
- [ ] Random group selection works
- [ ] Random userbot selection works
- [ ] Edge cases handled (no groups, no bots)

### Phase 3
- [ ] Model CRUD operations work
- [ ] get_chart_settings returns correct data
- [ ] Chart request groups CRUD functional

### Phase 4
- [ ] Chart groups menu displays
- [ ] Can add/remove groups via UI
- [ ] Input validation works

### Phase 5
- [ ] Chart settings visible in source detail
- [ ] Toggle chart enabled/disabled works
- [ ] MC threshold editor accepts k/m formats
- [ ] Chart bot ID editor validates input
- [ ] Settings persist correctly

### Phase 6
- [ ] Alerts with photo sent when MC > threshold
- [ ] Alerts without photo sent when MC < threshold
- [ ] Timeout doesn't block alert sending
- [ ] Chart disabled sources skip fetch
- [ ] Logs track all chart operations

---

## File Manifest

### New Files
1. `migrations/068_add_chart_request_groups.sql`
2. `migrations/069_add_monitored_source_chart_settings.sql`
3. `app/chart_fetcher.py`
4. `app/models/chart_request_group.py`

### Modified Files
1. `app/models/monitored_source.py` (add chart settings methods)
2. `app/ui/handlers/gain_alerts.py` (add chart UI handlers)
3. `app/ui/routers/gain_alerts.py` (add chart routes)
4. `app/ui/states.py` (add FSM states)
5. `app/ui/keyboards.py` (add chart keyboard methods)
6. `app/userbot/token_monitor.py` (integrate chart fetch)
7. `app/userbot/handlers.py` (detect chart bot replies)

---

## Rollout Order

1. **Phase 1** → Run migrations (reversible, no code dependencies)
2. **Phase 2 + 3** → Core logic + models (can test independently)
3. **Phase 4** → Global settings UI (configure chart groups)
4. **Phase 5** → Per-source UI (configure per-source settings)
5. **Phase 6** → Integration (actually use charts in alerts)

**Reason for order:** Each phase builds on previous, allows incremental testing, UI before integration prevents deployment issues.
