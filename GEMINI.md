# GEMINI.md

## Project Overview

This project is a sophisticated Telegram bot management system for monitoring Telegram groups and forwarding Solana addresses. It features a button-based UI for configuration, advanced scheduling with quotas and cooldowns, multi-userbot support for handling different groups, and a smart alert system for price changes.

The system is built in Python and uses the `aiogram` and `telethon` libraries for interacting with Telegram. It uses a PostgreSQL database (via Supabase) for data persistence.

The architecture is modular, with components for:
- **Management Bot:** The main admin interface.
- **Userbot Workers:** Instances that monitor specific Telegram groups.
- **Scheduler:** Manages time-based rules and quotas.
- **Alert System:** Tracks token prices and sends alerts.
- **Event Router:** Processes incoming messages and events.
- **DexScreener Service:** Fetches token price data.

## Building and Running

1.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

2.  **Configure Environment:**
    Create a `.env` file by copying `.env.example` and filling in the required values:
    ```bash
    cp .env.example .env
    ```
    **Required .env variables:**
    - `ADMIN_TELEGRAM_IDS`: Comma-separated list of your Telegram user IDs.
    - `MGMT_BOT_TOKEN`: Your management bot's Telegram token.
    - `API_ID`: Your Telegram API ID.
    - `API_HASH`: Your Telegram API hash.
    - `SUPABASE_POOLER_URL`: The connection string for your Supabase PostgreSQL database.

3.  **Run the Application:**
    ```bash
    python app/runner.py
    ```
    The application will automatically handle database migrations on the first run.

## Development Conventions

- **Configuration:** All configuration is managed through the bot's UI, which modifies settings stored in the database. Initial credentials are set via the `.env` file.
- **Entry Point:** The main entry point for the application is `app/runner.py`.
- **Modular Design:** The application is broken down into several independent components located in the `app/` directory.
- **Database Migrations:** SQL migration files are located in the `migrations/` directory.
- **Dependencies:** Python dependencies are managed in the `requirements.txt` file.
