# 🚀 Advanced Telegram Userbot Manager

An enterprise-grade Telegram userbot management system designed for automated Solana token call monitoring, forwarding, and profit tracking. Built with modern Python architecture and sophisticated business logic for professional trading operations.

## ✨ Core Features

### 🎛️ **Management Dashboard**
- **Complete UI Control**: Full bot management via `/menu` command with intuitive button interface
- **Real-time Monitoring**: Live system status, userbot health, and performance metrics
- **Multi-Admin Support**: Secure admin-only access with role-based permissions
- **Advanced Pagination**: Efficient navigation through large datasets

### 🤖 **Intelligent Userbot Management**
- **Auto-Login System**: Phone/SMS/2FA authentication with secure session handling
- **Health Monitoring**: Continuous connection status tracking and auto-recovery
- **Load Balancing**: Smart assignment of userbots to groups for optimal performance
- **Session Security**: Encrypted session storage with automatic cleanup

### 📡 **Source Monitoring Engine**
- **Multi-Channel Support**: Monitor channels, groups, and direct messages simultaneously
- **Smart Token Detection**: Advanced Solana address parsing with validation
- **Message Filtering**: Sophisticated content analysis and spam detection
- **Real-time Processing**: Instant message capture and routing

### 💹 **Profit & Loss Tracking**
- **DexScreener Integration**: Real-time token price monitoring and market data
- **Gain Alerts**: Configurable multiplier thresholds (5x, 10x, 20x+)
- **Stop-Loss Protection**: Automatic tracking halt on major drops (70% default)
- **Performance Analytics**: Comprehensive PNL reports and statistics

### 📬 **Advanced Notification System**
- **Event Forwarding**: Auto-forward replies, mentions, and DMs
- **Smart Routing**: Context-aware message categorization
- **Customizable Alerts**: Per-group notification preferences
- **Rich Formatting**: Enhanced message presentation with metadata

### 📡 **Auto-Tap Features**
- **Auto-Click Integration**: Automated interaction with scanner bots
- **Smart Button Detection**: Intelligent UI element recognition
- **Response Automation**: Configured automatic responses to common scenarios
- **Performance Optimization**: Efficient resource usage and rate limiting

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MANAGEMENT DASHBOARD                         │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │   Overview  │   Agents    │ Profit Logs │   Inbox     │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE ENGINE                                │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │ Session Mgmt │   Scheduler  │  DexScreener │ Event Router │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    WORKER LAYER                                 │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │   Userbot 1  │   Userbot 2  │   Userbot N  │ Auto-Click   │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                  DATABASE LAYER                                 │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │    Groups    │    Tokens    │   Events     │  Analytics   │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 📁 Project Structure

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
│       └── auto_click.py
├──
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
├──
└── 📊 models/
    ├── bot.py                # Userbot data models
    ├── group.py              # Group & schedule models
    ├── token.py              # Token tracking models
    └── event.py              # Event & alert models
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
DB_POOL_MIN=2                             # Minimum connection pool size
DB_POOL_MAX=10                            # Maximum connection pool size

# System Configuration
TIMEZONE=Asia/Kolkata                     # System timezone
DEX_POLL_SECS=5                          # DexScreener polling interval
DEX_TIMEOUT=10                           # API request timeout
DEX_MAX_RETRIES=3                        # Maximum retry attempts

# Optional Features
SCANNER_BOT_ID=7178305557                # Auto-click scanner bot ID
SCANNER_BUTTON_TEXT=🛰 Just Scanning     # Scanner button text
```

### 3. **Database Setup**

#### **Option A: Supabase (Recommended)**
1. Create account at [supabase.com](https://supabase.com)
2. Create new project
3. Copy **Connection Pooler** URL (not direct connection)
4. Add to `.env` as `SUPABASE_POOLER_URL`

#### **Option B: Local PostgreSQL**
```bash
# Install PostgreSQL
sudo apt install postgresql postgresql-contrib  # Ubuntu/Debian
# or
brew install postgresql                         # macOS

# Create database
sudo -u postgres createdb userbot_manager
sudo -u postgres psql -c "CREATE USER yourusername WITH PASSWORD 'yourpassword';"
sudo -u postgres psql -c "GRANT ALL ON DATABASE userbot_manager TO yourusername;"

# Update .env
SUPABASE_POOLER_URL=postgresql://yourusername:yourpassword@localhost:5432/userbot_manager
```

### 4. **Start the System**

```bash
# Standard startup
python app/runner.py

# Debug mode with detailed logging
LOG_LEVEL=DEBUG python app/runner.py

# Background mode with log file
nohup python app/runner.py > system.log 2>&1 &
```

### 5. **Initial Setup via Bot**

1. **Start Management Bot**: Send `/menu` to your management bot
2. **Add Userbots**: Navigate to "👤 Agents" → "Add Agent"
3. **Configure Groups**: Go to "👥 Groups" → "Add Group"
4. **Set Schedules**: Configure active windows and quotas
5. **Enable Tracking**: Set up profit/loss monitoring

## 💼 Business Logic & Features

### 📊 **Scheduling System**

#### **Time-Based Controls**
- **Active Days**: Monday-Sunday selection
- **Time Windows**: Start/end times in configured timezone
- **Quota Management**: Maximum calls per window
- **Cooldown Periods**: Minimum gaps between forwards

#### **Smart Quota System**
```python
# Example: Group configuration
{
    "daily_quota": 50,           # Max 50 calls per day
    "cooldown_minutes": 15,      # 15min gap between calls
    "schedule_windows": [
        {
            "days": ["Monday", "Tuesday", "Wednesday"],
            "start_time": "09:00",
            "end_time": "17:00",
            "max_calls": 20
        }
    ]
}
```

### 🎯 **Token Tracking & Alerts**

#### **Gain Thresholds**
- **Multi-level Alerts**: 5x, 10x, 20x, 50x+ configurable
- **One-time Triggers**: Each threshold fires once per token
- **Custom Multipliers**: Set any gain percentage

#### **Loss Protection**
- **Auto-stop Tracking**: Halt at configured drop percentage
- **Global Protection**: System-wide loss thresholds
- **Recovery Monitoring**: Auto-resume when conditions improve

### 🔄 **Event Processing**

#### **Message Types**
- **Replies**: Responses to your messages
- **Mentions**: When you're tagged in groups
- **Direct Messages**: Private conversations
- **Channel Posts**: Public announcements

#### **Smart Routing**
```python
# Event routing example
{
    "source_type": "reply",
    "from_chat": "@trading_signals",
    "to_channel": "@profit_updates",
    "conditions": ["contains_pnl", "is_gain"],
    "format": "enhanced"  # Add metadata
}
```

## 🎛️ Management Interface

### **Main Dashboard**
Access via `/menu` command:

#### **🧾 Overview**
- System health status
- Active userbot count
- Processing statistics
- Recent alerts

#### **👤 Agents (Userbots)**
- Add new agents via phone authentication
- **Worker Controls**: Start, stop, and restart individual workers directly from the UI.
- Monitor connection status
- Assign to groups
- View performance metrics

#### **👥 Groups**
- Add target groups for forwarding
- Configure quotas and schedules
- Set notification preferences
- Manage userbot assignments

#### **💹 Profit Logs**
- Real-time PNL tracking
- Token performance analytics
- Gain/loss history
- Alert configuration

#### **📬 Inbox**
- Event forwarding settings
- Notification preferences
- Message routing rules
- Activity logs

#### **📡 Auto-Tap**
- Auto-click configuration
- Scanner bot integration
- Response automation
- Performance settings

## 🔧 Advanced Configuration

### **Per-Group Settings**

#### **Quota Configuration**
```yaml
Group: "@crypto_signals"
├── Daily Quota: 100 calls
├── Cooldown: 10 minutes
├── Active Schedule:
│   ├── Monday-Friday: 09:00-18:00 (60 calls max)
│   └── Weekend: 10:00-16:00 (40 calls max)
└── Assigned Userbot: Agent #3
```

#### **Alert Settings**
```yaml
Token Tracking:
├── Gain Thresholds: [5x, 10x, 25x, 50x]
├── Loss Threshold: 70%
├── Tracking Duration: 7 days
└── Alert Channels: ["@profit_alerts", "@team_updates"]
```

### **Global System Settings**

#### **Performance Tuning**
- **Database Pool**: 2-10 connections (configurable)
- **API Rate Limits**: Telegram-compliant defaults
- **Polling Intervals**: 5-second DexScreener updates
- **Memory Management**: Automatic cleanup routines

#### **Security Features**
- **Session Encryption**: Secure userbot session storage
- **Admin Validation**: ID-based access control
- **Rate Limiting**: Anti-spam protection
- **Audit Logging**: Complete activity tracking

## 📊 Monitoring & Analytics

### **System Metrics**
- **Uptime Tracking**: Service availability monitoring
- **Performance Stats**: Message processing rates
- **Error Rates**: Failure analysis and alerting
- **Resource Usage**: Memory, CPU, and network monitoring

### **Business Intelligence**
- **Token Performance**: Success rate analysis
- **Group Activity**: Forwarding statistics per group
- **Userbot Efficiency**: Performance comparison
- **Revenue Tracking**: Profit/loss aggregation

### **Logging System**
```python
# Log levels and destinations
LOG_LEVEL=DEBUG                    # DEBUG, INFO, WARNING, ERROR
LOG_FILE=logs/system.log          # File destination
LOG_ROTATION=daily                # daily, weekly, monthly
LOG_MAX_SIZE=100MB                # Maximum log file size
```

## 🚨 Troubleshooting

### **Common Issues & Solutions**

#### **Database Connection Issues**
```bash
# Test connection
python -c "import asyncio; from app.db import db; asyncio.run(db.connect())"

# Check environment
echo $SUPABASE_POOLER_URL

# Verify Supabase project status
# Visit your Supabase dashboard
```

#### **Userbot Authentication Failures**
```bash
# Clear sessions
rm -rf sessions/*.session

# Verify API credentials
python -c "from app.config import settings; print(f'API_ID: {settings.api_id}')"

# Re-authenticate via management bot
# Send /menu → Agents → Add Agent
```

#### **Token Detection Issues**
```bash
# Test Solana address regex
python -c "
import re
from app.config import settings
pattern = settings.solana_pattern
test_addr = 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v'
print(f'Match: {bool(re.search(pattern, test_addr))}')
"
```

#### **DexScreener API Issues**
```bash
# Test API connectivity
curl -s "https://api.dexscreener.com/tokens/v1/solana/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Check network configuration
ping api.dexscreener.com
```

### **Performance Optimization**

#### **Database Performance**
- **Connection Pooling**: Adjust `DB_POOL_MIN/MAX` based on load
- **Query Optimization**: Use pagination for large datasets
- **Index Management**: Ensure proper indexing on frequently queried columns
- **Regular Cleanup**: Remove old tokens and events

#### **Memory Management**
- **Session Cleanup**: Regular userbot session maintenance
- **Cache Management**: Token price cache optimization
- **Log Rotation**: Prevent log files from growing too large
- **Resource Monitoring**: Track memory usage per component

## 🔒 Security Best Practices

### **Access Control**
- **Admin IDs**: Secure storage of authorized Telegram IDs
- **Bot Tokens**: Environment-based token management
- **API Keys**: Separate development/production credentials
- **Session Security**: Encrypted userbot session files

### **Data Protection**
- **Database Security**: Connection encryption and access controls
- **Log Sanitization**: Remove sensitive data from logs
- **Error Handling**: Prevent information leakage in error messages
- **Backup Strategy**: Regular database backups

### **Operational Security**
- **Network Security**: Firewall configuration for external APIs
- **Update Management**: Regular dependency updates
- **Monitoring**: Security event logging and alerting
- **Incident Response**: Procedures for security breaches

## 📈 Scaling & Production Deployment

### **Production Setup**

#### **Environment Preparation**
```bash
# Production environment file
cp .env.example .env.production

# Update with production values
ADMIN_TELEGRAM_IDS=real_admin_ids
MGMT_BOT_TOKEN=production_bot_token
SUPABASE_POOLER_URL=production_database_url
LOG_LEVEL=INFO
```

#### **Service Management**
```bash
# Systemd service (Linux)
sudo cp scripts/userbot-manager.service /etc/systemd/system/
sudo systemctl enable userbot-manager
sudo systemctl start userbot-manager

# Docker deployment
docker build -t userbot-manager .
docker run -d --env-file .env.production userbot-manager
```

### **Horizontal Scaling**
- **Multiple Instances**: Run multiple runner processes
- **Load Balancing**: Distribute userbots across instances
- **Database Sharding**: Separate databases for different regions
- **Message Queues**: Implement async message processing

### **Monitoring & Alerting**
- **Health Checks**: Endpoint monitoring
- **Performance Metrics**: Response time tracking
- **Error Alerting**: Real-time failure notifications
- **Capacity Planning**: Resource usage forecasting

## 🤝 Contributing

### **Development Setup**
```bash
# Development environment
python -m venv venv-dev
source venv-dev/bin/activate
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Additional dev dependencies

# Pre-commit hooks
pre-commit install

# Run tests
pytest tests/
```

### **Code Standards**
- **Python Style**: PEP 8 compliance
- **Type Hints**: Full type annotation
- **Documentation**: Comprehensive docstrings
- **Testing**: Unit tests for all components

### **Contribution Process**
1. **Fork Repository**: Create personal fork
2. **Feature Branch**: Create branch for changes
3. **Development**: Implement features with tests
4. **Documentation**: Update relevant documentation
5. **Pull Request**: Submit for review

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support & Community

### **Getting Help**
- **Documentation**: Check this README and inline documentation
- **Issues**: Report bugs via GitHub Issues
- **Discussions**: Community discussions for questions
- **Examples**: Sample configurations and use cases

### **Professional Support**
For enterprise deployments and custom integrations:
- **Consulting Services**: Architecture and optimization
- **Custom Development**: Feature development and integration
- **Training**: Team training and best practices
- **24/7 Support**: Production support and monitoring

---

**⚡ Built for Professional Trading Operations | 🚀 Enterprise-Grade Architecture | 🔒 Security-First Design**

*Making Solana token monitoring simple, reliable, and profitable.*