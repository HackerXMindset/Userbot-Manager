---
task: m-implement-solana-forwarding-userbot
branch: feature/userbot-manager-improvements
status: in-progress
created: 2025-09-04
modules: [app/userbot, app/solana, app/models]
---

# Implement Solana Token Forwarding Userbot

## Problem/Goal
Extend the existing Telegram userbot system to perform actual Solana blockchain token transfers instead of just forwarding token addresses as text messages. Currently the system only detects Solana addresses in messages and forwards them as text - we need to add real blockchain integration for automatic token forwarding.

## Success Criteria
- [ ] Create Solana wallet management system with encrypted private key storage
- [ ] Implement automatic token detection and balance monitoring
- [ ] Add real blockchain token transfer functionality when tokens are received
- [ ] Integrate with existing userbot flow (TokenMonitor -> CallExecutor)
- [ ] Add configuration UI for wallet addresses and forwarding settings
- [ ] Ensure secure key management with proper encryption
- [ ] Add transaction history tracking and error handling

## Context Files
<!-- Current system architecture -->
- @app/userbot/token_monitor.py:22-42  # Current token address detection
- @app/userbot/call_executor.py:55-97  # Current message forwarding system
- @app/models/token.py                 # Token tracking database model
- @app/config.py:35-36                # Solana address regex pattern
- @app/userbot/utils.py:22-28         # Solana address extraction
- @migrations/001_initial.sql:60-71   # tokens_tracked table schema
- @requirements.txt                   # Current dependencies (base58, cryptography available)

## User Notes
**Current System Behavior:**
- Detects Solana addresses using regex `r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b'`
- Forwards addresses as TEXT messages to target chats
- Tracks token performance via DexScreener API
- Uses PostgreSQL for call/token tracking

**Required Architecture:**
- New `app/solana/` module for blockchain operations
- Wallet management with secure private key storage
- RPC integration for Solana network interaction
- Balance monitoring and automatic forwarding logic
- Integration with existing database schema

## Work Log
<!-- Updated as work progresses -->
- [2025-09-04] Started task, analyzed existing codebase architecture
- [2025-09-07] Reviewed current token detection and forwarding system