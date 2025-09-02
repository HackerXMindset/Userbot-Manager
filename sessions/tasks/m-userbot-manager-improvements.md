---
task: m-userbot-manager-improvements
branch: feature/userbot-manager-improvements
status: pending
created: 2025-09-02
modules: [app/userbot, app/ui, app/alerts, app/management_bot, app/scheduler]
---

# Userbot Manager Bot Improvements

## Problem/Goal
Continue development of the userbot_manager telegram bot system that monitors telegram groups, users, and channels for Solana contract addresses and forwards them. The system needs ongoing bug fixes and new feature additions to improve functionality and reliability.

## Success Criteria
- [ ] Identify and document current bugs in the system
- [ ] Implement fixes for critical bugs affecting core functionality
- [ ] Add requested new features to improve user experience
- [ ] Ensure all components (management bot, userbot workers, scheduler, alerts) work reliably
- [ ] Test end-to-end workflows (group monitoring, address detection, forwarding)
- [ ] Update documentation for any changes made

## Context Manifest

### System Architecture Overview
This is a **multi-component Telegram bot system** that monitors groups for Solana contract addresses and forwards them to target channels with advanced scheduling, quotas, and price-based alerts.

### Core Components
1. **Management Bot** (`app/management_bot.py`) - Button-based admin interface via `/menu`
2. **Userbot Workers** (`app/userbot/`) - Individual Telegram clients that monitor groups  
3. **Scheduler** (`app/scheduler.py`) - Manages call timing with quotas and cooldowns
4. **Alert System** (`app/alerts.py`) - Price monitoring with gain/drop thresholds
5. **Database Models** (`app/models/`) - PostgreSQL persistence layer
6. **UI Handlers** (`app/ui/handlers/`) - Button interaction processing

### How The System Works

**Token Detection Flow:**
- Userbots monitor assigned groups for messages containing Solana addresses (regex pattern)
- Detected tokens are added to tracking database and DexScreener price monitoring  
- Raw contract addresses are forwarded to target channels (no formatting)
- All activity is logged with quotas, cooldowns, and audit trails

**Management Interface:**
- Complete button-based UI accessible via `/menu` command
- No config files - everything configured through Telegram interface
- Supports group management, userbot login, schedule setup, alert configuration
- Uses aiogram with FSM for complex multi-step flows

**Scheduling & Quotas:**
- Per-group daily caps and time-window quotas
- Weekly scheduling with Asia/Kolkata timezone
- No spillover between groups - strict per-group limits
- Rate limiting (30 calls/minute per userbot)

**Alert System:**
- DexScreener API integration for real-time price monitoring
- Configurable gain thresholds (5x, 10x, 15x, 20x, 50x)
- Drop alerts at 70% decline from peak (configurable)
- Alerts fire once per threshold with database tracking

### Technical Architecture
- **Database**: PostgreSQL with asyncpg connection pooling
- **Frameworks**: aiogram (management bot), Telethon (userbots)  
- **Architecture**: Async/await throughout, component lifecycle management
- **Deployment**: Single runner process managing all components

### Key Files
- @app/management_bot.py:1-500     # Main admin interface with /menu command
- @app/userbot/manager.py:1-300    # Userbot lifecycle management
- @app/userbot/message_handler.py  # Token detection and forwarding logic
- @app/scheduler.py:1-400          # Job scheduling with quotas/cooldowns
- @app/alerts.py:1-250             # Price monitoring and alert system
- @app/ui/keyboards.py             # Button layouts for management interface
- @app/ui/handlers/                # FSM handlers for multi-step flows
- @app/models/group.py             # Group and schedule models
- @app/models/token.py             # Token tracking models
- @app/dex.py                      # DexScreener API integration
- @app/config.py                   # Configuration management

## User Notes
<!-- Any specific notes or requirements from the developer -->
- System is a Telegram bot that monitors groups for Solana addresses
- Uses button-based UI for configuration via /menu command  
- Supports multiple userbot workers with scheduling and quotas
- Has alert system for token price monitoring (5x, 10x gains, 70% drops)
- Focus on bug fixes and feature improvements
- All configuration done through management bot interface
- Keep it simple - not even 100 people will use this bot, avoid over-engineering

## Work Log
<!-- Updated as work progresses -->
- [2025-09-02] Created task for userbot manager improvements
- [2025-09-02] **FIXED**: Multiple target forwarding bug - targets were being created with group_id=NULL, breaking the forwarding logic. Updated targets handler to properly associate targets with groups during creation.
- [2025-09-02] **FIXED**: Database schema error - removed broken detection_count logic from token_monitor.py and event_processor.py. Token tracking now works without missing database columns. Duplicate prevention functionality preserved.
- [2025-09-02] **FIXED**: Alert system completely overhauled for correct behavior:
  - Added source_group_id tracking to tokens_tracked table (migration 007)
  - Changed gain alerts to send `/pnl {address}` commands to DESTINATION groups (where tokens were forwarded to)
  - Updated alert system to read configured gain thresholds from UI settings (supports per-group and global)  
  - Updated drop alerts to use configured drop percentage from UI settings
  - Each gain threshold (5x, 10x, 15x, etc.) now fires once per token and sends /pnl command to all destination groups
  - Uses calls table to find all groups that received the token for proper /pnl distribution
  - Drop alerts stop monitoring when configured percentage is reached