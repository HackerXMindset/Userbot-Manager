---
task: h-pnl-reply-forwarding
branch: app
status: in-progress
created: 2025-09-10
modules: [app/userbot/message_handler, app/alerts, app/models]
---

# PNL Reply Forwarding Feature

## Problem/Goal
Implement a feature that monitors /pnl commands from specific userbots in specific groups and forwards replies to those commands to a different channel using a designated forwarding userbot.

**Multi-Userbot Architecture:**
- **Detection Userbots**: Multiple userbots can send `/pnl` commands in monitored groups
- **Forwarding Userbot**: One designated userbot sends the forwarded replies to destination channels
- **Per-Group Rules**: Each group has separate rules with its own detection bots and forwarding bot

When detection userbots execute `/pnl` in a monitored group:
- Monitor for replies to that /pnl message
- Forward replies from specified users to a configured destination channel via forwarding userbot
- Configuration managed through dedicated PNL Forwarding interface in management bot

## Success Criteria
- [x] Create PnlForwardingRule database model and schema with forwarding_userbot_id
- [x] Multi-select detection userbot configuration in wizard
- [x] Single forwarding userbot selection in wizard  
- [x] Detect /pnl commands from specific detection userbots in specific groups
- [x] Track /pnl message IDs for reply monitoring
- [x] Monitor replies to tracked /pnl messages
- [x] Filter replies by user whitelist
- [x] Forward replies via designated forwarding userbot to destination channel
- [x] Configuration interface with 5-step wizard in management bot
- [ ] Testing with real /pnl scenarios

## Context Files
- @app/userbot/message_handler.py:58-74  # Event handlers setup
- @app/userbot/message_handler.py:206-215 # Outgoing message tracking
- @app/userbot/utils.py:75-117            # MessageTracker class
- @app/userbot/call_executor.py:20-25     # Message tracking components
- @app/alerts.py                          # Alert system for configuration
- @app/models/group.py                    # Group management models
- @app/models/__init__.py                 # Models imports

## Implementation Plan

### 1. Database Schema
```sql
CREATE TABLE pnl_forwarding_rules (
    id SERIAL PRIMARY KEY,
    source_group_id BIGINT NOT NULL,
    destination_channel_id BIGINT NOT NULL, 
    allowed_user_ids BIGINT[] NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 2. Core Components
- **PNL Command Detection**: Extend MessageHandler event handlers
- **Reply Monitoring**: Extend existing MessageTracker for /pnl replies
- **PnlForwardingRule Model**: New model in app/models/
- **Configuration Interface**: Extend AlertSystem

### 3. Flow
1. Detect `/pnl` in monitored groups → track message
2. Monitor for replies to tracked PNL messages  
3. Check if replier is in allowed users list
4. Forward reply to destination channel

## User Notes
- Source group (where /pnl commands are monitored) should be configurable
- Destination channel (where replies are forwarded) should be configurable  
- User whitelist (whose replies to forward) should be configurable
- Configuration should be accessible through alerts system
- Need to track message IDs to detect replies to /pnl commands
- Should integrate with existing message handling and tracking system

## Work Log
- [2025-09-10] Created task, analyzed existing codebase structure
- [2025-09-10] Identified key components: MessageHandler, MessageTracker, AlertSystem
- [2025-09-10] MAJOR REDESIGN: Implemented multi-userbot architecture
  - Created database schema with forwarding_userbot_id field (migrations 013, 014, 015)
  - Built 5-step wizard: Group → Detection Userbots (multi-select) → Forwarding Userbot → Destination → Reply Users
  - Updated message handler to use separate forwarding userbot for sending replies
  - Added complete UI interface in management bot under "💸 PNL Forwarding"
  - All core functionality implemented and ready for testing
