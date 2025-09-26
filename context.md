# Advanced Telegram Userbot Manager - Complete System Context
#
# 🎯 Mission Statement
This is an enterprise-grade Telegram userbot management system designed for automated Solana token call monitoring, forwarding, and profit tracking. The system combines a high-performance Rust microservice for data aggregation with a sophisticated Python automation framework for userbot orchestration and template-based message generation.

**Core Objectives:**
- Serve all token intelligence through the Rust microservice (`telegram_token_bot`) ensuring fresh, uncached data on every execution
- Expose 300+ data points as placeholders in `PlaceholderService`, enabling operators to craft pump.fun and generic templates without code changes
- Maintain legacy Python fetchers as emergency fallbacks while Rust service owns primary data collection from DexScreener, pump.fun, Jupiter, and Helius APIs
- Enable split-responsibility forwarding where different userbots monitor sources vs send calls
- Provide comprehensive template management system with categorized help and ready-to-use examples

#
# 🏗️ System Architecture Overview

## **Hybrid Rust/Python Architecture**
```
┌─────────────────────────────────────────────────────────────────┐
│                    MANAGEMENT DASHBOARD                         │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐      │
│  │   Overview  │   Agents    │ Profit Logs │   Templates │      │
│  └─────────────┴─────────────┴─────────────┴─────────────┘      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                      CORE ENGINE                                │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │ Session Mgmt │ Call Dispatch│  Rust Bridge │ Event Router │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    RUST MICROSERVICE                            │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │ DexScreener  │   pump.fun   │   Jupiter    │    Helius    │   │
│  │     API      │     API      │     API      │     API      │   │
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
│                  DATABASE LAYER (PostgreSQL)                   │
│  ┌──────────────┬──────────────┬──────────────┬──────────────┐   │
│  │  Userbots    │    Groups    │   Templates  │ Call Queue   │   │
│  │  Tokens      │    Events    │   Analytics  │ Call History │   │
│  └──────────────┴──────────────┴──────────────┴──────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## **Rust Microservice (`telegram_token_bot/`)**
**Purpose**: High-performance, concurrent data aggregation service
**Architecture**: Dual-mode service running both Telegram bot and HTTP server

### Key Files:
- **`src/main.rs`**: Service orchestrator with graceful shutdown, env validation
- **`src/api.rs`**: Multi-API integration client with connection pooling (30 conn/host, 60s idle)
- **`src/http_server.rs`**: Axum-based REST API server for `/dex/{mint}` endpoint
- **`src/types.rs`**: Comprehensive data structures for all API responses
- **`Cargo.toml`**: Production-optimized build config (LTO, single codegen unit)

### HTTP API Specification:
- **Endpoint**: `GET /dex/{mint_address}`
- **Binding**: `RUST_HTTP_ADDR` environment variable (default: `0.0.0.0:8080`)
- **Timeout**: 5s per external API call, 12s total client timeout
- **Concurrency**: All API calls executed in parallel via `tokio::join!`

### Payload Structure (`DexPayload`):
```rust
{
  "pairs": Vec<TokenPair>,              // DexScreener trading pairs data
  "orders": Vec<DexScreenerOrder>,      // Paid promotional orders with timestamps
  "pump_fun": Option<PumpFunData>,      // Bonding curve and creator metadata
  "jupiter": Option<JupiterTokenData>,  // Token analytics, audit flags, social links
  "dev_sol_balance": Option<f64>,       // Developer wallet SOL balance
  "holders": Option<HoldersData>,       // Top 20 token holders from Helius
  "supply_ui_amount": Option<f64>       // Total circulating supply
}
```

### External API Dependencies:
- **DexScreener**: Token pairs, market data, promotional orders
- **pump.fun**: Bonding curve data, creator info, engagement metrics
- **Jupiter**: Token analytics, audit information, social links
- **Helius**: Token holder analysis, supply information
- **SOL Balance**: Real-time developer wallet balance

## **Python Automation Framework (`app/`)**

### Core Services (`app/services/`):

#### **`rust_bridge.py`** - HTTP Client
- aiohttp client with 12s timeout calling Rust `/dex/{mint}`
- Error handling with graceful degradation to Python fallback

#### **`placeholder_service.py`** - Data Transformation Engine (980 lines)
- **Purpose**: Transform raw Rust payload + DB context into 300+ formatted placeholders
- **Key Features**:
  - Dual syntax support: `{placeholder}` and `${placeholder}`
  - Smart formatting functions: `format_market_cap()`, `format_time_diff()`, `format_bool()`
  - Comprehensive fallback handling: all missing data → `N/A`
  - Social media platform detection for intelligent link formatting
  - Progress bar generation for bonding curves (`jup_bonding_progress_bar`)
  - ATH comparison calculations with time deltas (`pf_ath_comparison`)

#### **`call_dispatcher.py`** - Job Queue Processor (430 lines)
- **Purpose**: Process call queue jobs and delegate to appropriate userbots
- **Architecture**: Async service with 2s polling interval, 10-job batch size
- **Features**:
  - Template resolution with placeholder substitution
  - Management bot vs userbot routing logic
  - Executor caching (5-minute TTL)
  - Stuck job recovery (5-minute timeout)
  - Rich call history logging with market cap tracking
  - Multi-source call history: logs every contributing source with real Telegram titles and caller attribution

### Database Models (`app/models/`):

#### **Core Models**:
- **`BotModel`**: Userbot management (sessions, health, assignments)
- **`GroupModel`**: Target group configuration (quotas, schedules)
- **`TokenModel`**: Token tracking (market caps, multipliers, history)
- **`CallQueueModel`**: Job queue management (pending → processing → completed/failed)
- **`TemplateModel`**: Custom message templates
- **`TemplateAssignmentModel`**: Group-to-template mappings
- **`SourceChatModel`**: Source monitoring configuration with routing rules
- **`TokenCallHistoryModel`**: Rich call logging with market data

#### **Split-Responsibility Architecture**:
Recent implementation enables different userbots for monitoring vs forwarding:
- **Monitoring Assignment**: Which userbot monitors each source chat
- **Forwarding Assignment**: Which userbot sends calls to target groups
- **Job Queue**: Decouples monitoring from forwarding via persistent queue
- **Database Schema**: `routing_rules` table with `monitoring_userbot_id` + `forwarding_userbot_id`

### User Interface (`app/ui/`):

#### **`handlers/templates.py`** - Template Management System (941 lines)
- **Complete CRUD Operations**: Create, read, update, delete templates
- **Group Assignment UI**: Interactive selection with pagination
- **Comprehensive Help System**:
  - Categorized placeholder documentation (Basic Info, Money, Trading, Time, Links)
  - Ready-to-use template examples (Simple, Detailed, Quick, Premium)
  - Step-by-step usage instructions with template copying functionality
- **Sender Configuration**: Toggle between management bot vs userbot delivery

#### **Other UI Handlers**:
- **`menu.py`**: Main dashboard navigation
- **`userbots.py`**: Agent management (add, start/stop workers, health monitoring)
- **`groups.py`**: Target group configuration
- **`sources.py`**: Source monitoring setup with userbot assignment
- **`pnl.py`**: Profit/loss tracking configuration
- **`alerts.py`**: Threshold-based alert management

#
# 📊 Complete Placeholder System (300+ Placeholders)

## **Placeholder Categories and Coverage:**

### **DexScreener Data (`dex_*`)**:
- **Metadata**: `dex_id`, `dex_pair_chain_id`, `dex_pair_dex_id`, `dex_pair_url`, `dex_pair_address`
- **Pricing**: `price_usd`, `price_native`, `market_cap`, `fdv`, `dex_pair_market_cap_raw`, `dex_pair_fdv_raw`
- **Liquidity**: `liquidity_usd`, `liquidity_base`, `liquidity_quote`, `bonding_status`
- **Volume/Deltas**: `volume_m5`, `volume_h1`, `volume_h6`, `volume_h24`
- **Price Changes**: `price_change_m5`, `price_change_h1`, `price_change_h6`, `price_change_h24`
- **Transactions**: `txns_m5_buys/sells`, `txns_h1_buys/sells`, `txns_h6_buys/sells`, `txns_h24_buys/sells`
- **Info Blocks**: `dex_info_image_url`, `dex_info_header`, `dex_info_websites`, `dex_info_socials`
- **Paid Orders**: `dex_order_1_type` through `dex_order_20_type` with timestamps
- **CTO Detection**: `cto_status`, `cto_time`, `dex_time`, `dex_paid`
- **Timing**: `pair_created_at`

### **pump.fun Data (`pf_*`)** - 80+ Placeholders:
- **Identity**: `pf_mint`, `pf_name`, `pf_symbol`, `pf_description`, `pf_image_uri`, `pf_metadata_uri`
- **Social**: `pf_twitter`, `pf_telegram`, `pf_website`, `pf_social` (combined HTML links)
- **Creator**: `pf_creator`, `pf_creator_short`, `pf_creator_solscan`, `pf_creator_stats`
- **Bonding**: `pf_bonding_curve`, `pf_associated_bonding_curve`
- **Economics**: `pf_total_supply`, `pf_market_cap_sol`, `pf_market_cap_usd`, `pf_ath_market_cap`
- **Reserves**: `pf_real_sol_reserves`, `pf_virtual_sol_reserves`, `pf_virtual_token_reserves`, `pf_real_token_reserves`
- **Timestamps** (raw/ISO/ago format): `pf_created_timestamp*`, `pf_last_trade_timestamp*`, `pf_ath_market_cap_timestamp*`
- **Engagement**: `pf_reply_count`, `pf_num_participants`
- **Status Flags**: `pf_complete`, `pf_hidden`, `pf_nsfw`, `pf_is_banned`, etc.
- **Special**: `pf_ath_comparison` (ratio from ATH with time delta)

### **Jupiter Analytics (`jup_*`)** - 70+ Placeholders:
- **Identity**: `jup_id`, `jup_name`, `jup_symbol`, `jup_icon`, `jup_decimals`
- **Market**: `jup_usd_price`, `jup_mcap`, `jup_fdv`, `jup_liquidity`, `jup_holder_count`
- **Audit**: `jup_audit_mint_authority_disabled`, `jup_audit_freeze_authority_disabled`, `jup_audit_top_holders_pct`
- **Developer**: `jup_dev_address`, `jup_dev_sol_balance`
- **Social**: `jup_twitter`, `jup_telegram`, `jup_website`, `jup_socials` (smart HTML formatting)
- **Analytics**: `jup_organic_score`, `jup_ct_likes`, `jup_smart_ct_likes`
- **Bonding**: `jup_bonding_curve`, `jup_bonding_progress_bar` (visual progress bar or "Bonded ✅")
- **Interval Stats**: `jup_stats_5m_*`, `jup_stats_1h_*`, `jup_stats_6h_*`, `jup_stats_24h_*`
  - Each timeframe includes: price_change, holder_change, volume_change, buy_volume, sell_volume, num_buys, num_sells, num_traders

### **Helius Holder Data (`helius_*`)** - 40+ Placeholders:
- **Snapshot**: `helius_data_slot`, `helius_holder_count`, `helius_holder_total_ui_amount`
- **Aggregates**: `helius_top1_ui_amount/share`, `helius_top5_*`, `helius_top10_*`, `helius_top20_*`
- **Per-Holder** (1-20): `helius_holder_N_address`, `helius_holder_N_short`, `helius_holder_N_ui_amount`
- **Formatted** (1-20): `helius_holder_N_user`, `helius_holder_N_balance_short`, `helius_holder_N_percent_short`, `helius_breakdown_N`
- **Creator Holdings**: `helius_creator_is_holder`, `helius_creator_holding_*` (amounts, percentages)
- **Enhanced Dev Detection**: `dev_holdings_indicator` (🟢 if sold, 🔴 (X.X%) if holding)

### **General Helpers**:
- **Basic**: `address`, `token_symbol`, `token_name`, `multiplier`
- **Links**: `dexscreener_link`, `defined_link`
- **History**: `mention_count`, `call_history` (formatted historical calls)
- **Status**: `bonding_status` ("Bonded" vs "Not Bonded")

#
# 🔄 Integration Flow & Template Execution

## **Message Processing Pipeline:**
```
User/Bot Message → Token Detection → Source Rule Matching → Job Queue → Call Dispatcher → Template Resolution → Placeholder Service → Rust Bridge → External APIs → Data Aggregation → Template Rendering → Message Delivery
```

## **Detailed Flow:**
1. **Source Monitoring**: Userbot receives message in monitored channel
2. **Token Extraction**: Regex detects Solana token addresses
3. **Rule Matching**: Check routing rules for source chat
4. **Job Creation**: Add job to `call_queue` with:
   - `token_address`, `source_chat_id`, `target_chat_id`
   - `monitoring_userbot_id`, `forwarding_userbot_id`
   - `additional_info` (caller details, source metadata)
5. **Job Processing**: Call Dispatcher polls queue (2s intervals)
6. **Template Resolution**: Check for custom template assigned to target group
7. **Placeholder Generation**:
   - Call Rust service `/dex/{mint}` endpoint
   - Merge with database context (token history, multipliers)
   - Apply formatting functions and fallback handling
8. **Template Rendering**: Replace placeholders in template text
9. **Message Delivery**: Send via management bot or assigned userbot
10. **History Logging**: Record call with market cap, source info, timestamps

#
# 🗃️ Database Schema & Models

## **Core Tables:**
- **`userbots`**: Session management, health status, assignments
- **`groups`**: Target groups with quotas, schedules, notification preferences
- **`routing_rules`**: Source monitoring configuration with split-responsibility userbot assignments
- **`call_queue`**: Job queue (pending → processing → completed/failed)
- **`post_templates`**: Custom message templates with sender configuration
- **`template_assignments`**: Group-to-template mappings
- **`tokens`**: Token tracking (market caps, multipliers, peak values)
- **`calls`**: Legacy call tracking
- **`token_call_history`**: Rich call logging with market data and source metadata

## **Split-Responsibility Implementation:**
- **`routing_rules.monitoring_userbot_id`**: Which userbot monitors this source
- **`routing_rules.forwarding_userbot_id`**: Which userbot sends calls to targets
- **Job Queue Architecture**: Decouples monitoring from forwarding
- **Backward Compatibility**: NULL assignments allow any userbot (legacy behavior)

#
# 📝 Template System Architecture

## **Template Management Features:**
- **CRUD Operations**: Full create, read, update, delete via management bot UI
- **Group Assignment**: Multi-select interface with pagination
- **Sender Toggle**: Choose management bot vs userbot for delivery
- **Preview System**: Live template preview with example data

## **Help System Structure:**
- **Categorized Documentation**:
  - 🔤 Basic Info (addresses, names, symbols)
  - 💰 Money Stuff (prices, market caps, multipliers)
  - 📈 Trading Activity (volumes, transactions, price changes)
  - ⏰ Time & History (timestamps, call history)
    - Includes `{call_history}` with live call data combining current dispatch sources + recent logs
  - 🔗 Links & Special (status flags, links)
- **Ready-to-Use Examples**:
  - 🚀 Simple Call (basic token info)
  - 📊 Detailed Stats (comprehensive analysis)
  - ⚡ Quick Alert (minimal notification)
  - 🎯 Premium Call (professional formatting)
- **Copy-Paste Functionality**: One-click template copying
- **Usage Instructions**: Step-by-step template creation guide

#
# 🔧 Operational Procedures

## **Service Management:**
- **Rust Service**: `cargo run` in `telegram_token_bot/` directory
  - Build: `cargo build --release` for production
  - Environment: Requires `HELIUS_API_KEY`, optional `PUMP_FUN_JWT`
  - Binding: `RUST_HTTP_ADDR` (default: `0.0.0.0:8080`)
- **Python App**: `python app/runner.py`
  - Environment: `.env` file with database, API keys, admin IDs
  - Database: PostgreSQL/Supabase with connection pooling

## **Configuration:**
```env
# Required Environment Variables
ADMIN_TELEGRAM_IDS=123456789,987654321
MGMT_BOT_TOKEN=7123456789:AAH...
API_ID=12345678
API_HASH=abcd1234567890...
SUPABASE_POOLER_URL=postgresql://...
HELIUS_API_KEY=your_helius_key
PUMP_FUN_JWT=your_pump_jwt (optional)
RUST_HTTP_ADDR=0.0.0.0:8080

# System Configuration
TIMEZONE=Asia/Kolkata
DEX_POLL_SECS=5
DEX_TIMEOUT=10
DEX_MAX_RETRIES=3
```

## **Health Monitoring:**
- **Rust Service**: HTTP endpoint health via curl `http://localhost:8080/dex/test_address`
- **Python Services**: Management bot `/menu` → Overview for system status
- **Database**: Connection pool monitoring, query performance
- **Userbots**: Health status in management interface

#
# 🐛 Debugging & Troubleshooting

## **Debug Snippets:**
### Dump All Placeholders:
```python
from app.services.placeholder_service import PlaceholderService
import asyncio
async def main():
    ps = PlaceholderService('MINT_ADDRESS', {})
    data = await ps.get_all_placeholders()
    for key in sorted(data):
        print(key, ':', data[key])
asyncio.run(main())
```

### Test Rust Service:
```bash
curl http://localhost:8080/dex/EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v
```

### Check Call Queue Status:
```sql
SELECT status, COUNT(*) FROM call_queue GROUP BY status;
```

## **Common Issues:**
- **"call queue schema outdated"**: Cosmetic warning for curated alpha flows
- **Missing placeholders**: Check Rust service connectivity and API keys
- **Template not applied**: Verify group assignment in template management
- **Userbot offline**: Check session health in agent management

#
# 📈 Performance Characteristics

## **Rust Service:**
- **Concurrent API Calls**: All external APIs called in parallel via `tokio::join!`
- **Connection Pooling**: 30 connections per host, 60s idle timeout
- **Timeout Strategy**: 5s per API call, 12s total timeout
- **Memory Usage**: Optimized for minimal allocation, efficient JSON parsing

## **Python Framework:**
- **Database Pool**: 2-10 connections (configurable)
- **Call Dispatcher**: 2s polling, 10-job batches, 5-minute executor cache
- **Template Resolution**: Cached template lookups, efficient placeholder replacement
- **Error Handling**: Comprehensive fallback mechanisms, graceful degradation

#
# 📅 Phase History & Current State

## **Completed Phases:**
- **Phase 1**: Rust bridge + DexScreener integration + `/dex/{mint}` endpoint
- **Phase 2**: pump.fun payload/placeholder coverage (80+ placeholders) - **100% COMPLETE**
- **Phase 3**: Jupiter analytics integration (70+ placeholders) - **100% COMPLETE**
- **Phase 4**: Removed Telegram parse mode to eliminate Markdown formatting errors
- **Phase 5**: Enhanced Helius integration with direct dev holdings detection (40+ placeholders) - **100% COMPLETE + ENHANCED**
  - **Original**: Basic top-20 holder analysis via `getTokenLargestAccounts`
  - **Enhancement**: Direct dev holdings detection via `getTokenAccountsByOwner` API
  - **Impact**: Now detects dev holdings regardless of ranking (previously missed devs not in top 20)
- **Phase 6**: CTO detection, ATH comparisons, social link formatting, error handling improvements

## **Current Branch:** `pumpfun-phase2`
## **Active Tasks:**
- **`h-split-responsibility-forwarding`** (in-progress): Job queue architecture for decoupled monitoring/forwarding
- **`h-investigate-curate-alpha-bugs`** (pending)
- **`l-fix-bird-ath-only`** (pending)
- **`m-implement-template-help`** (pending)

## **Recent Commits:**
```
5df20c1 jupiter done 100%
186b744 dex and pumpfun placeholders done 100%
a1b1ff0 all placeholders created jup, helius, punpfun, dex
```

#
# 🚀 Pending Enhancements & Future Development

## **High Priority:**
- Complete split-responsibility forwarding implementation
- UI control to switch pump.fun vs generic templates
- Retries & telemetry in `rust_bridge` for better error surfacing
- Automated placeholder tests using fixture payloads

## **Future Considerations:**
- Additional Solana analytics APIs integration
- Horizontal scaling with multiple Rust service instances
- Advanced template conditional logic
- Real-time performance monitoring dashboard
- Comprehensive deployment automation

#
# 📚 Reference Documentation

## **Placeholder Inventories** (Living Documentation):
- **`pumpfun_placeholders.md`**: Complete pump.fun placeholder reference (80+ placeholders)
- **`jupiter_placeholders.md`**: Jupiter analytics placeholder documentation (70+ placeholders)
- **`helius_placeholders.md`**: Helius holder analysis placeholders (40+ placeholders)

## **Task Management System** (`sessions/`):
- **Task-driven development**: All work organized as trackable tasks
- **Context manifests**: Each task maintains detailed context and progress
- **Protocols**: Standardized workflows for task creation, completion, context management
- **Agent system**: Specialized AI agents for code review, logging, documentation

#
# 🎯 Mission Completion Status
This system represents a mature, production-ready token intelligence platform with:
- ✅ **Comprehensive Data Coverage**: 300+ placeholders across 4 major APIs
- ✅ **High-Performance Architecture**: Rust microservice with Python orchestration
- ✅ **Advanced Template System**: User-friendly interface with categorized help
- ✅ **Split-Responsibility Architecture**: Flexible userbot assignment model
- ✅ **Enterprise Features**: Comprehensive logging, error handling, health monitoring
- ✅ **Operational Excellence**: Detailed documentation, debugging tools, performance optimization

**This context document enables any engineer or AI assistant to understand, extend, debug, and operate the entire system without exploring the codebase.**
