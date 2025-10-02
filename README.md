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
├── migrations/             # Contains 44 database migration files
├── scripts/                # Helper scripts
│   ├── add_complete_jupiter_template.py
│   └── add_example_templates.py
├── templates/              # Message templates
│   └── holder_template.txt
├── tests/                  # Project tests
├── tools/                  # Diagnostic tools
│   └── diagnostic_alerts.py
├── .env.example            # Example environment file
├── .gitignore              # Git ignore file
├── helius_placeholders.md  # Placeholder documentation
├── jupiter_placeholders.md # Placeholder documentation
├── pumpfun_placeholders.md # Placeholder documentation
└── requirements.txt        # Python dependencies
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