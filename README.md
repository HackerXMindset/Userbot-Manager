# 🚀 Advanced Telegram Userbot Manager

An enterprise-grade Telegram userbot management system designed for automated Solana token call monitoring, forwarding, and profit tracking. Built with modern Python architecture and sophisticated business logic for professional trading operations.

## ✨ Key Features

*   **Multi-Userbot Support**: Manage multiple userbots to monitor different groups and channels.
*   **Advanced Scheduling**: Configure time-based rules, quotas, and cooldowns for forwarding messages.
*   **Profit & Loss (PNL) Tracking**: Automatically track the performance of token calls and forward PNL updates.
*   **Curated Alpha**: A system for identifying and forwarding high-quality "alpha" from specified sources.
*   **Custom Post Templates**: Customize the format of forwarded messages with dynamic placeholders.
*   **Command Forwarding**: Forward commands from source channels to target groups.
*   **Auto Button Click**: Automatically click buttons in messages from specified bots.
*   **Rust-based Token Bot**: A high-performance Rust component for handling token-related operations.

## 🏗️ System Architecture

The system consists of a Python-based management bot and a Rust-based token bot.

### **Python Component**

The Python component provides the main management interface and orchestration layer.

### **Rust Component**

The Rust component is a high-performance Telegram bot that handles token-related operations, including fetching metadata from Helius. It is located in the `telegram_token_bot` directory.

## 📁 Project Structure

### **Python Application (`app/`)**

```
app/
├── 🎛️ management_bot.py      # Main dashboard interface
├── ⚙️ config.py              # Environment & settings management
├── 🗄️ db.py                  # Database connection & migrations
├── 🏃 runner.py              # Application orchestrator
├── 📊 dex.py                 # DexScreener API integration
├── 📅 scheduler.py           # Job scheduling & quota management
├── 🚨 alerts.py              # Alert system & thresholds
├── 🔄 events.py              # Event processing & routing
├── 📝 logging_conf.py        # Advanced logging configuration
├──
├── 📱 ui/
│   ├── keyboards.py          # Interactive UI components
│   ├── states.py             # FSM state management
│   └── handlers/             # UI interaction handlers
│       ├── menu.py
│       ├── groups.py
│       ├── userbots.py
│       ├── sources.py
│       ├── alerts.py
│       ├── pnl.py
│       ├── notifications.py
│       ├── auto_click.py
│       ├── command_forwarding.py
│       ├── curate_alpha.py
│       ├── schedules.py
│       ├── targets.py
│       └── templates.py
│
├── 🤖 userbot/
│   ├── session_manager.py    # Session handling & authentication
│   ├── message_handler.py    # Message processing & filtering
│   ├── token_monitor.py      # Token detection & validation
│   ├── pnl_tracker.py        # Profit/loss tracking
│   ├── notification_handler.py # Event forwarding
│   ├── call_executor.py      # Message forwarding logic
│   ├── source_manager.py     # Source monitoring
│   ├── worker.py             # Userbot worker implementation
│   └── utils.py              # Utility functions
│
├── 🛠️ services/
│   ├── call_dispatcher.py    # Dispatches token calls
│   ├── call_history_service.py # Manages token call history
│   └── placeholder_service.py  # Manages message templates
│
└── 📊 models/
    ├── base.py
    ├── bot.py
    ├── group.py
    ├── token.py
    ├── event.py
    ├── auto_button_click.py
    ├── call_queue.py
    ├── command_forwarding.py
    ├── curated_alpha.py
    ├── notification.py
    ├── pnl_forwarding.py
    ├── source_chat.py
    ├── target_alert_state.py
    ├── target.py
    └── template.py
```

### **Rust Bot (`telegram_token_bot/`)**

```
telegram_token_bot/
├── src/
│   ├── main.rs         # Main entry point for the Rust bot
│   ├── bot.rs          # Core bot logic
│   ├── api.rs          # Helius API client
│   ├── http_server.rs  # HTTP server for receiving callbacks
│   └── types.rs        # Data structures
└── Cargo.toml          # Rust dependencies
```

### **Other Files and Directories**

```
├── migrations/
│   ├── 001_initial.sql
│   ├── 002_add_session_string.sql
│   ├── 003_add_source_chats.sql
│   ├── 004_add_notification_settings.sql
│   ├── 005_add_dm_source_type.sql
│   ├── 006_global_sources_system.sql
│   ├── 007_add_source_group_tracking.sql
│   ├── 008_add_display_name.sql
│   ├── 009_add_group_display_name.sql
│   ├── 010_add_source_display_name.sql
│   ├── 011_extend_sources_configuration.sql
│   ├── 012_add_peak_mc_tracking.sql
│   ├── 013_add_pnl_forwarding_rules.sql
│   ├── 014_add_pnl_user_whitelist.sql
│   ├── 015_add_forwarding_userbot.sql
│   ├── 016_add_pnl_tracking_table.sql
│   ├── 017_add_pnl_stateful_tracking.sql
│   ├── 018_pnl_tracker_enhancements.sql
│   ├── 019_simplify_pnl_permissions.sql
│   ├── 020_add_pnl_reply_users.sql
│   ├── 021_fix_pnl_tracking_constraint.sql
│   ├── 022_add_notification_system.sql
│   ├── 023_add_auto_button_click.sql
│   ├── 024_fix_userbot_assignment_constraint.sql
│   ├── 025_add_autoclick_tracking.sql
│   ├── 026_add_ticker_to_tokens.sql
│   ├── 027_add_split_responsibility_forwarding.sql
│   ├── 028_fix_call_queue_columns.sql
│   ├── 029_add_forwarded_tokens_log.sql
│   ├── 030_add_curated_alpha.sql
│   ├── 031_add_curated_alpha_to_queue.sql
│   ├── 032_add_custom_post_templates.sql
│   ├── 033_add_user_id_to_call_queue.sql
│   ├── 034_add_sender_toggle_to_templates.sql
│   ├── 035_add_min_mentions_to_curated_alpha.sql
│   ├── 036_add_source_level_bots.sql
│   ├── 037_add_updated_at_to_curated_alpha_token_state.sql
│   ├── 038_add_token_call_history.sql
│   ├── 039_fix_source_chat_id_nullable.sql
│   ├── 040_add_target_alert_settings.sql
│   ├── 041_add_command_forwarding_rules.sql
│   ├── 042_add_command_tracked_messages.sql
│   ├── 043_add_phone_to_bots.sql
│   └── 044_add_timestamp_posting_to_cmd_fwd.sql
├── scripts/
│   ├── add_complete_jupiter_template.py
│   └── add_example_templates.py
├── templates/
│   └── holder_template.txt
├── tests/
│   ├── test_auto_click.py
│   └── test_batch.py
├── tools/
│   └── diagnostic_alerts.py
├── .env.example
├── .gitignore
├── helius_placeholders.md
├── jupiter_placeholders.md
├── pumpfun_placeholders.md
└── requirements.txt
```

## 🚀 Quick Start Guide

### 1. **Clone & Setup**

```bash
# Clone repository
git clone https://github.com/your-username/userbot-manager.git
cd userbot-manager

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. **Environment Configuration**

```bash
# Copy example configuration
cp .env.example .env
```

**Required Environment Variables:**

```env
# Administrative Control
ADMIN_TELEGRAM_IDS=123456789,987654321    # Comma-separated admin IDs
MGMT_BOT_TOKEN=7123456789:AAHxxxxxxxxx    # Management bot token

# Telegram API Credentials
API_ID=12345678                           # Get from my.telegram.org
API_HASH=abcd1234567890abcd1234567890      # Get from my.telegram.org

# Database Configuration
SUPABASE_POOLER_URL=postgresql://postgres.xxxx:password@aws-0-region.pooler.supabase.com:5432/postgres

# Helius API Key (for Rust bot)
HELIUS_API_KEY=your_helius_api_key

# System Configuration
TIMEZONE=Asia/Kolkata                     # System timezone
```

### 3. **Database Setup**

The application uses a PostgreSQL database. The migrations are applied automatically when the application starts.

### 4. **Start the System**

```bash
# Start the Python application
python app/runner.py

# Start the Rust bot
cd telegram_token_bot
cargo run --release
```

### 5. **Initial Setup via Bot**

1.  **Start Management Bot**: Send `/menu` to your management bot.
2.  **Add Userbots**: Navigate to "👤 Agents" → "Add Agent".
3.  **Configure Groups**: Go to "👥 Groups" → "Add Group".
4.  **Set Schedules**: Configure active windows and quotas.
5.  **Enable Tracking**: Set up profit/loss monitoring.

## 🤝 Contributing

Contributions are welcome! Please follow the standard fork-and-pull-request workflow.

## 📝 License

This project is licensed under the MIT License.
