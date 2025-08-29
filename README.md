# Telegram Bot Management System

A sophisticated management bot + userbot workers system for monitoring Telegram groups and forwarding Solana addresses with advanced scheduling, quotas, and alerts.

## ✨ Features

- **🎛 Complete Button-Based UI**: Everything configurable via `/menu` - no config files needed
- **📅 Advanced Scheduling**: Weekly windows with per-group quotas and cooldowns
- **🤖 Multi-Userbot Support**: Each group gets a unique userbot
- **🚨 Smart Alerts**: Gain thresholds (5x, 10x, etc.) and 70% drop protection
- **📢 Event Notifications**: Forward replies/DMs/mentions to notification channel
- **⏱ Timezone Support**: Asia/Kolkata timezone for all scheduling
- **🔒 Admin Only**: Single admin controls everything via Telegram

## 🚀 Quick Start

### 1. Clone & Install

```bash
git clone <repo>
cd callbot_copy
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your values
```

Required environment variables:
```env
ADMIN_TELEGRAM_ID=123456789
MGMT_BOT_TOKEN=your_management_bot_token
API_ID=12345678
API_HASH=your_api_hash
SUPABASE_POOLER_URL=your_database_url
```

### 3. Setup Database

- Get Supabase account and create project
- Copy pooler connection string to .env
- Migrations run automatically on first start

### 4. Start System

```bash
python app/runner.py
```

Or with custom logging:
```bash
LOG_LEVEL=DEBUG LOG_FILE=logs/system.log python app/runner.py
```

### 5. Use Management Bot

- Send `/menu` to your management bot
- Add groups, schedules, userbots
- Everything is button-based!

## 📱 Management Console

Access everything through `/menu`:

### Main Menu
- **📊 Status** - System overview
- **👥 Groups** - Add/configure groups
- **📅 Schedules** - Set weekly windows
- **📦 Quotas** - Daily caps & cooldowns
- **🤖 Userbots** - Add & assign workers
- **🎯 Targets** - Set destination chats
- **🚨 Alerts** - Configure gain/drop thresholds
- **📢 Notifications** - Event forwarding
- **📈 Tracking** - Token management
- **⚙️ Settings** - Global configuration

### Key Workflows

#### Adding a Group
1. Click Groups → Add Group
2. Enter @username or chat ID
3. Set daily quota and cooldown
4. Add schedule windows
5. Assign a userbot
6. Add target channels

#### Setting Schedules
1. Select group → Schedules
2. Choose days (Mon-Sun)
3. Set start/end times (IST)
4. Set max calls per window
5. Multiple windows supported

#### Userbot Login
1. Click Userbots → Add
2. Enter phone number
3. Enter code (auto-masked)
4. Handle 2FA if needed
5. Auto-assigns to groups

## 🎯 Business Rules

- **No Spillover**: Quotas are strict per group
- **Cooldowns**: Minimum gap between calls (customizable)
- **Gain Alerts**: Fire once per threshold (5x, 10x, etc.)
- **Drop Protection**: Stop at 70% loss globally
- **Unique Assignment**: One userbot per group
- **IST Timezone**: All scheduling in Asia/Kolkata

## 🏗 Architecture

The system consists of several modular components:

```
app/
├── config.py              # Configuration management
├── db.py                  # Database connection & migrations
├── models/                # Data models
│   ├── bot.py            # Bot management
│   ├── group.py          # Groups & schedules
│   ├── token.py          # Token tracking
│   └── event.py          # Events & alerts
├── ui/                    # User interface
│   ├── keyboards.py      # Inline keyboards
│   ├── states.py         # FSM states
│   └── handlers/         # UI handlers
├── management_bot.py      # Main management bot
├── scheduler.py          # Job scheduling
├── alerts.py             # Alert system
├── events.py             # Event routing
├── dex.py                # DexScreener integration
├── userbot_worker.py     # Userbot workers
├── logging_conf.py       # Logging setup
└── runner.py             # Main application runner
```

### Core Components

1. **Management Bot**: Main admin interface with button-based UI
2. **Scheduler**: Handles call scheduling with quotas and cooldowns
3. **Alert System**: Monitors token prices and triggers alerts
4. **Event Router**: Processes Telegram events (replies, mentions, DMs)
5. **DexScreener Service**: Fetches real-time token price data
6. **Userbot Workers**: Monitor groups and send calls
7. **Database Models**: Handle all data persistence

## 🔧 Advanced Configuration

All configuration is done via the management bot UI:

### Per-Group Settings
- Daily quotas and cooldowns
- Schedule windows (days/times)
- Target channels
- Userbot assignment

### Global Settings
- Gain thresholds (5x, 10x, 15x, etc.)
- Drop percentage (default 70%)
- DexScreener polling rate
- Timezone settings

### Alert Configuration
- Multiple gain multipliers
- Custom drop thresholds
- Per-group or global alerts
- Notification channels

## 📊 Monitoring

The system provides comprehensive monitoring:

### System Status
- Component health checks
- Resource usage tracking
- Error rate monitoring
- Performance metrics

### Activity Tracking
- Calls per day/window
- Token performance
- Alert triggers
- Event routing stats
- Userbot health

### Logging
- Structured logging with multiple levels
- Performance logging
- Security event logging
- Health monitoring
- File rotation support

## 🔒 Security

- Single admin control via Telegram ID
- Phone/code masking during userbot login
- Session string encryption (recommended)
- Rate limiting and cooldowns
- Permission-based access control
- Security event logging

## 🛠 Development

### Running in Development Mode

```bash
# Set debug logging
export LOG_LEVEL=DEBUG
export LOG_FILE=logs/debug.log

# Run with auto-reload (if using tools like nodemon equivalent)
python app/runner.py
```

### Database Management

```sql
-- Connect to your Supabase database
-- Migrations are in migrations/001_initial.sql
-- New migrations can be added with incremental numbers
```

### Adding New Features

1. Create models in `app/models/`
2. Add UI handlers in `app/ui/handlers/`
3. Update keyboards in `app/ui/keyboards.py`
4. Add database migrations as needed
5. Update the main runner if new services are added

## 🐛 Troubleshooting

### Common Issues

**Database Connection Error**
```bash
# Check your SUPABASE_POOLER_URL
# Ensure the database is accessible
# Verify credentials and permissions
```

**Userbot Login Failed**
```bash
# Verify API_ID and API_HASH
# Check phone number format (+country_code)
# Ensure 2FA password is correct if enabled
```

**No Tokens Detected**
```bash
# Check Solana address regex pattern
# Verify DexScreener API access
# Check network connectivity
```

**Scheduling Not Working**
```bash
# Verify timezone settings
# Check group has assigned userbot
# Ensure targets are configured
# Validate schedule windows
```

### Logging

Enable debug logging to troubleshoot:

```bash
LOG_LEVEL=DEBUG python app/runner.py
```

Check specific component logs:
- Management Bot: UI interactions and admin commands
- Scheduler: Job scheduling and quota management
- Alert System: Price monitoring and alert triggers
- Event Router: Message processing and forwarding
- Userbot Workers: Group monitoring and message sending

## 📈 Performance

### Optimization Tips

1. **Database**: Use connection pooling (configured automatically)
2. **API Calls**: Implement rate limiting and caching
3. **Memory**: Monitor userbot worker memory usage
4. **Network**: Use async HTTP clients for external APIs
5. **Logging**: Use appropriate log levels in production

### Scaling

- Multiple userbot workers can run concurrently
- Database connection pool scales automatically
- Alert system processes tokens in batches
- Event routing handles high message volumes
- Horizontal scaling via multiple runner instances

## 📝 License

MIT

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 🆘 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs with DEBUG level
3. Open an issue with detailed information
4. Include configuration (without sensitive data)

---

**Made with ❤️ for the Solana community**