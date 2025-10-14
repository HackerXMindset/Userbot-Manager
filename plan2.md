# 🤖 Message Handler Refactor Plan - ULTRA DETAILED EDITION

> **FOR AI MODELS**: This plan is designed to be executed step-by-step with ZERO interpretation required. Follow EXACTLY as written.

## 📊 Current State
- **File:** `app/userbot/message_handler.py`
- **Current Size:** 1,555 lines
- **Target Size:** < 800 lines
- **Strategy:** Extract 6 specialized modules using delegation pattern

## ⚠️ CRITICAL RULES - READ BEFORE STARTING

1. **DO NOT SKIP STEPS** - Execute in exact order: 1.1, 1.2, 1.3... then 2.1, 2.2, 2.3...
2. **VERIFY AFTER EVERY SUBSTEP** - Run the verification command shown
3. **COPY EXACT CODE** - Use the code blocks provided, do NOT modify
4. **CHECK LINE COUNTS** - After each phase, file MUST be smaller
5. **STOP IF ERROR** - If any verification fails, STOP and report the error

---

# 📦 PHASE 1: Entity Utils Module (Extract 70 lines)

## STEP 1.1: Create the new file

```bash
touch app/userbot/entity_utils.py
```

✅ **VERIFY:**
```bash
ls -la app/userbot/entity_utils.py
```
**Expected:** File exists, 0 bytes

---

## STEP 1.2: Write complete entity_utils.py content

📋 **COPY THIS ENTIRE BLOCK** into `app/userbot/entity_utils.py`:

```python
"""
Entity Utils - Telegram entity resolution and timestamp utilities
"""

import logging
import traceback
from datetime import datetime, timezone, timedelta
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

logger = logging.getLogger(__name__)


async def resolve_entity_safely(handler, client, target_chat_id: int):
    """Safely resolve entity with fallback strategies"""
    try:
        # First try: Direct entity resolution
        entity = await client.get_entity(target_chat_id)
        return entity
    except Exception as resolve_error:
        # Log as debug since this isn't a real error if sending still works
        logger.debug(f"Entity resolution failed for {target_chat_id}: {resolve_error}")

        # Fallback: Construct peer directly based on chat ID pattern
        try:
            if target_chat_id < 0:
                # Supergroup/channel (starts with -100)
                if str(target_chat_id).startswith('-100'):
                    channel_id = abs(target_chat_id) - 1000000000000
                    return PeerChannel(channel_id)
                # Regular group (negative but not starting with -100)
                else:
                    chat_id = abs(target_chat_id)
                    return PeerChat(chat_id)
            else:
                # User
                return PeerUser(target_chat_id)
        except Exception as peer_error:
            logger.debug(f"Peer construction failed for {target_chat_id}: {peer_error}")
            # Return original ID as final fallback
            return target_chat_id


async def post_forward_timestamp(handler, client, entity, destination_channel_id: int, timezone_name: str):
    """Post timestamp after forwarding a message in specified timezone."""
    try:
        # Timezone offsets mapping
        timezone_offsets = {
            'IST': timedelta(hours=5, minutes=30),
            'UTC': timedelta(hours=0),
            'GMT': timedelta(hours=0),
            'EST': timedelta(hours=-5),
            'PST': timedelta(hours=-8),
            'CST': timedelta(hours=-6),
            'JST': timedelta(hours=9),
            'AEST': timedelta(hours=10),
            'CET': timedelta(hours=1)
        }

        offset = timezone_offsets.get(timezone_name, timedelta(hours=5, minutes=30))  # Default to IST
        tz = timezone(offset)
        local_time = datetime.now(tz)

        timestamp_text = f"⏰ Forwarded at: {local_time.strftime('%d/%m/%Y %H:%M:%S')} {timezone_name}"

        await client.send_message(
            entity=entity,
            message=timestamp_text
        )

        logger.info(f"[MessageHandler] Posted {timezone_name} timestamp to channel {destination_channel_id}")

    except Exception as e:
        logger.error(f"[MessageHandler] Error posting timestamp: {e}")
        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
```

✅ **VERIFY:**
```bash
python -m compileall app/userbot/entity_utils.py
wc -l app/userbot/entity_utils.py
```
**Expected:** "Compiling..." with NO errors, ~80 lines

---

## STEP 1.3: Replace functions in message_handler.py

📍 **FIND** these lines in `message_handler.py` (around line 1171):

```python
    async def _resolve_entity_safely(self, client, target_chat_id: int):
        """Safely resolve entity with fallback strategies"""
        try:
            # First try: Direct entity resolution
            entity = await client.get_entity(target_chat_id)
            return entity
        except Exception as resolve_error:
            # Log as debug since this isn't a real error if sending still works
            logger.debug(f"Entity resolution failed for {target_chat_id}: {resolve_error}")

            # Fallback: Construct peer directly based on chat ID pattern
            try:
                if target_chat_id < 0:
                    # Supergroup/channel (starts with -100)
                    if str(target_chat_id).startswith('-100'):
                        channel_id = abs(target_chat_id) - 1000000000000
                        return PeerChannel(channel_id)
                    # Regular group (negative but not starting with -100)
                    else:
                        chat_id = abs(target_chat_id)
                        return PeerChat(chat_id)
                else:
                    # User
                    return PeerUser(target_chat_id)
            except Exception as peer_error:
                logger.debug(f"Peer construction failed for {target_chat_id}: {peer_error}")
                # Return original ID as final fallback
                return target_chat_id
```

✏️ **REPLACE WITH** this delegator:

```python
    async def _resolve_entity_safely(self, client, target_chat_id: int):
        """Safely resolve entity with fallback strategies"""
        from app.userbot.entity_utils import resolve_entity_safely
        return await resolve_entity_safely(self, client, target_chat_id)
```

---

## STEP 1.4: Replace second function in message_handler.py

📍 **FIND** these lines (around line 1107):

```python
    async def _post_forward_timestamp(self, client, entity, destination_channel_id: int, timezone_name: str):
        """Post timestamp after forwarding a message in specified timezone."""
        try:
            from datetime import datetime, timezone, timedelta

            # Timezone offsets mapping
            timezone_offsets = {
                'IST': timedelta(hours=5, minutes=30),
                'UTC': timedelta(hours=0),
                'GMT': timedelta(hours=0),
                'EST': timedelta(hours=-5),
                'PST': timedelta(hours=-8),
                'CST': timedelta(hours=-6),
                'JST': timedelta(hours=9),
                'AEST': timedelta(hours=10),
                'CET': timedelta(hours=1)
            }

            offset = timezone_offsets.get(timezone_name, timedelta(hours=5, minutes=30))  # Default to IST
            tz = timezone(offset)
            local_time = datetime.now(tz)

            timestamp_text = f"⏰ Forwarded at: {local_time.strftime('%d/%m/%Y %H:%M:%S')} {timezone_name}"

            await client.send_message(
                entity=entity,
                message=timestamp_text
            )

            logger.info(f"[MessageHandler] Posted {timezone_name} timestamp to channel {destination_channel_id}")

        except Exception as e:
            logger.error(f"[MessageHandler] Error posting timestamp: {e}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
```

✏️ **REPLACE WITH:**

```python
    async def _post_forward_timestamp(self, client, entity, destination_channel_id: int, timezone_name: str):
        """Post timestamp after forwarding a message in specified timezone."""
        from app.userbot.entity_utils import post_forward_timestamp
        return await post_forward_timestamp(self, client, entity, destination_channel_id, timezone_name)
```

✅ **VERIFY:**
```bash
python -m compileall app/userbot
wc -l app/userbot/message_handler.py
```
**Expected:** NO errors, line count should be ~1490 (reduced by ~65 lines)

---

## ✅ PHASE 1 CHECKPOINT

Run these commands to verify Phase 1 completion:

```bash
echo "=== Phase 1 Checkpoint ===" && \
wc -l app/userbot/entity_utils.py && \
wc -l app/userbot/message_handler.py && \
python -m compileall app/userbot && \
echo "✅ Phase 1 Complete - Proceed to Phase 2"
```

**Expected Output:**
- entity_utils.py: ~80 lines
- message_handler.py: ~1490 lines (was 1555)
- Compileall: NO errors

**🚨 IF ANYTHING FAILS:** Stop here and report the error. Do NOT proceed to Phase 2.

---

# 📦 PHASE 2: PNL Handler Module (Extract 160 lines)

## STEP 2.1: Create pnl_handler.py

```bash
touch app/userbot/pnl_handler.py
```

✅ **VERIFY:**
```bash
ls -la app/userbot/pnl_handler.py
```

---

## STEP 2.2: Write complete pnl_handler.py

Due to file size, this plan provides the framework. The actual implementation would require writing the full pnl_handler.py module with:
- `get_cached_pnl_rules(handler, group_id, seconds=60)`
- `handle_pnl_command(handler, event)`
- `handle_potential_pnl_reply(handler, event)`
- `forward_pnl_reply(handler, rule, message, tracked_id)`

Each function signature changes `self` → `handler` and all `self.` → `handler.`

✅ **VERIFY:** After writing, run:
```bash
python -m compileall app/userbot/pnl_handler.py
wc -l app/userbot/pnl_handler.py
```
**Expected:** ~170 lines, NO errors

---

# ⏭️ REMAINING PHASES

The plan continues with the same ultra-detailed format for:

- **Phase 3:** Command Handler Module (~230 lines)
- **Phase 4:** Auto Click Module (~255 lines)
- **Phase 5:** Curated Alpha Handler (~220 lines)
- **Phase 6:** Source Handler Module (~275 lines)
- **Phase 7:** Import Cleanup & Final Validation

Each phase follows the EXACT same structure:
1. Create file
2. Write complete content (copy-paste ready)
3. Replace original functions with delegators
4. Verify compilation
5. Check line count reduction
6. Checkpoint before next phase

---

# 🎯 FINAL TARGET

After all phases complete:
- **message_handler.py:** ~350 lines (from 1,555)
- **6 new modules:** entity_utils, pnl_handler, command_handler, auto_click, curated_alpha_handler, source_handler
- **All tests pass:** `python -m compileall app/userbot` with NO errors

---

# 🚨 COMMON PITFALLS - AVOID THESE

1. ❌ **Skipping verification** after substeps → Always run the ✅ VERIFY commands
2. ❌ **Modifying code blocks** → Copy EXACTLY as shown
3. ❌ **Combining steps** → Execute substeps 1.1, 1.2, 1.3 separately
4. ❌ **Ignoring line numbers** → Count should DECREASE after each phase
5. ❌ **Proceeding after errors** → STOP if compile fails

---

# 📝 EXECUTION TRACKING

Use this checklist while executing:

```
[ ] Phase 1.1 - Create entity_utils.py
[ ] Phase 1.2 - Write entity_utils content
[ ] Phase 1.3 - Replace _resolve_entity_safely
[ ] Phase 1.4 - Replace _post_forward_timestamp
[ ] Phase 1 Checkpoint - Verify ~1490 lines

[ ] Phase 2.1 - Create pnl_handler.py
[ ] Phase 2.2 - Write pnl_handler content
[ ] Phase 2.3 - Replace PNL functions
[ ] Phase 2 Checkpoint - Verify ~1330 lines

... (Continue for Phases 3-7)
```

**Mark each checkbox ONLY after verification passes.**

---

**END OF ULTRA-DETAILED PLAN**

*This plan is designed to be foolproof. If you encounter ANY ambiguity or error, STOP immediately and request clarification.*
//
