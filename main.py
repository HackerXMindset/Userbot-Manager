import asyncio
import threading
import time
import re
import logging
import os
from datetime import datetime, timedelta
import pytz
from flask import Flask
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.errors.rpcerrorlist import ChannelInvalidError, ChatWriteForbiddenError
from telethon.tl.types import User, Channel
from dotenv import load_dotenv, set_key
import psycopg2
from psycopg2 import pool
import aiohttp
from aiolimiter import AsyncLimiter
from asyncio import Lock

# --- Logging Setup ---
def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger

logger = setup_logger(__name__)

# --- Utility Functions ---
def format_time_diff(start: datetime, end: datetime) -> str:
    if not start.tzinfo or not end.tzinfo:
        logger.warning("Naive datetime detected in format_time_diff")
        start = start.replace(tzinfo=pytz.utc) if not start.tzinfo else start
        end = end.replace(tzinfo=pytz.utc) if not end.tzinfo else end
    diff = end - start
    total_seconds = int(diff.total_seconds())
    if total_seconds < 60:
        return f"{total_seconds}s"
    elif total_seconds < 3600:
        minutes = total_seconds // 60
        return f"{minutes}m"
    elif total_seconds < 86400:
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}h:{minutes:02d}m"
    else:
        days = diff.days
        hours = (total_seconds % 86400) // 3600
        return f"{days}d {hours}h"

def format_market_cap(value: float) -> str:
    if value is None:
        return "N/A"
    try:
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"${value / 1_000:.2f}K"
        return f"${value:,.2f}"
    except Exception as e:
        logger.error(f"Error formatting market cap {value}: {e}")
        return "Invalid"

def format_mention_count(count: int) -> str:
    if count <= 1:
        return ""
    ordinals = {2: "Second", 3: "Third", 4: "Fourth", 5: "Fifth", 6: "Sixth", 7: "Seventh", 8: "Eighth", 9: "Ninth"}
    return f"({ordinals.get(count, f'{count}th')} Mention)"

def parse_shorthand_value(value: str) -> float:
    try:
        value = value.strip().upper()
        multipliers = {'K': 1_000, 'M': 1_000_000, 'B': 1_000_000_000}
        match = re.match(r'^(\d*\.?\d+)([KMB])$', value)
        if match:
            number, unit = match.groups()
            return float(number) * multipliers[unit]
        return float(value)
    except Exception as e:
        logger.error(f"Error parsing shorthand value {value}: {e}")
        raise ValueError(f"Invalid value: {value}")

def get_telegram_link(chat_id: int, message_id: int, username: str = None) -> str:
    if username:
        return f"t.me/{username}/{message_id}"
    chat_id_str = str(chat_id).replace('-100', '') if str(chat_id).startswith('-100') else str(chat_id)
    return f"t.me/c/{chat_id_str}/{message_id}"

# --- Configuration Loading ---
def load_config():
    load_dotenv()
    config = {
        "DATABASE_URL": os.getenv("DATABASE_URL"),
        "BOT_TOKEN": os.getenv("BOT_TOKEN"),
        "ALERT_CHANNEL_ID": os.getenv("ALERT_CHANNEL_ID"),
        "MANAGEMENT_API_ID": os.getenv("MANAGEMENT_API_ID"),
        "MANAGEMENT_API_HASH": os.getenv("MANAGEMENT_API_HASH"),
        "ADMIN_IDS": os.getenv("ADMIN_IDS", "").split(",") if os.getenv("ADMIN_IDS") else [],
        "PORT": int(os.getenv("PORT", 8047)),
        "DEX_API_URL": os.getenv("DEX_API_URL", "https://api.dexscreener.com/latest/dex/tokens")
    }
    required_vars = ["DATABASE_URL", "MANAGEMENT_API_ID", "MANAGEMENT_API_HASH"]
    missing_vars = [key for key in required_vars if not config[key]]
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
    if config["DATABASE_URL"] and "keepalives" not in config["DATABASE_URL"]:
        config["DATABASE_URL"] += "?keepalives=1&keepalives_idle=30&keepalives_interval=10&keepalives_count=5"
    if not config["BOT_TOKEN"]:
        logger.warning("BOT_TOKEN not set. Userbots require valid sessions, and management bot may fail.")
    if not config["ALERT_CHANNEL_ID"]:
        logger.warning("ALERT_CHANNEL_ID not set. Please set it using /set_alert after starting the bot.")
    if not config["ADMIN_IDS"]:
        logger.warning("ADMIN_IDS not set. No admin access will be granted.")
    logger.info("Configuration loaded successfully")
    return config

# --- Database Management ---
class Database:
    def __init__(self, database_url):
        self.conn_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, database_url)
        self.create_tables()

    def create_tables(self):
        try:
            conn, cursor = self.get_connection()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bots (
                    name VARCHAR(255) PRIMARY KEY,
                    api_id INTEGER NOT NULL,
                    api_hash VARCHAR(255) NOT NULL,
                    session TEXT NOT NULL,
                    sensitivity FLOAT DEFAULT 50.0,
                    is_userbot BOOLEAN DEFAULT FALSE,
                    min_market_cap FLOAT DEFAULT 0.0,
                    bonded_only BOOLEAN DEFAULT FALSE
                );
                CREATE TABLE IF NOT EXISTS calls (
                    id SERIAL PRIMARY KEY,
                    bot_name VARCHAR(255) NOT NULL,
                    address VARCHAR(44) NOT NULL,
                    chat_id BIGINT NOT NULL,
                    user_id VARCHAR(255),
                    message_text TEXT,
                    message_id BIGINT,
                    chat_name VARCHAR(255),
                    mention_count INTEGER DEFAULT 1,
                    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS monitored_users (
                    bot_name VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    PRIMARY KEY (bot_name, user_id),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS target_groups (
                    bot_name VARCHAR(255) NOT NULL,
                    group_id BIGINT NOT NULL,
                    PRIMARY KEY (bot_name, group_id),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS target_channels (
                    bot_name VARCHAR(255) NOT NULL,
                    channel_id BIGINT NOT NULL,
                    PRIMARY KEY (bot_name, channel_id),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS channel_names (
                    bot_name VARCHAR(255) NOT NULL,
                    channel_id BIGINT NOT NULL,
                    custom_name VARCHAR(255) NOT NULL,
                    PRIMARY KEY (bot_name, channel_id),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS keywords (
                    bot_name VARCHAR(255) NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    keyword VARCHAR(255) NOT NULL,
                    PRIMARY KEY (bot_name, user_id, keyword),
                    FOREIGN KEY (bot_name, user_id) REFERENCES monitored_users(bot_name, user_id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS channel_keywords (
                    bot_name VARCHAR(255) NOT NULL,
                    channel_id BIGINT NOT NULL,
                    keyword VARCHAR(255) NOT NULL,
                    PRIMARY KEY (bot_name, channel_id, keyword),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS custom_alert_templates (
                    bot_name VARCHAR(255) PRIMARY KEY,
                    template TEXT NOT NULL,
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS repeat_alert_templates (
                    bot_name VARCHAR(255) PRIMARY KEY,
                    template TEXT NOT NULL,
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS reply_templates (
                    bot_name VARCHAR(255) PRIMARY KEY,
                    template TEXT NOT NULL DEFAULT '{emoji} {multiplier}x | 💹 From {initial_mc} ↗️ {current_mc} within ⏰{time}',
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS milestone_replies (
                    bot_name VARCHAR(255) NOT NULL,
                    multiplier FLOAT NOT NULL,
                    template TEXT NOT NULL,
                    PRIMARY KEY (bot_name, multiplier),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS tracked_calls (
                    id SERIAL PRIMARY KEY,
                    bot_name VARCHAR(255) NOT NULL,
                    address VARCHAR(44) NOT NULL,
                    initial_market_cap FLOAT,
                    original_initial_market_cap FLOAT,
                    initial_bonding_status BOOLEAN,
                    max_percentage_increase FLOAT DEFAULT 0.0,
                    alert_message_id BIGINT,
                    first_alert_message_id BIGINT,
                    posted_at TIMESTAMP WITH TIME ZONE,
                    last_checked TIMESTAMP WITH TIME ZONE,
                    original_chat_id BIGINT,
                    original_message_id BIGINT,
                    bonding_alert_sent BOOLEAN DEFAULT FALSE,
                    ath_price FLOAT DEFAULT 0.0,
                    ath_market_cap FLOAT DEFAULT 0.0,
                    ath_timestamp TIMESTAMP WITH TIME ZONE,
                    monitoring BOOLEAN DEFAULT TRUE,
                    original_caller_user_id VARCHAR(255),
                    last_alert_market_cap FLOAT,
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE,
                    UNIQUE (bot_name, address)
                );
                CREATE TABLE IF NOT EXISTS uptime_urls (
                    bot_name VARCHAR(255) PRIMARY KEY,
                    url TEXT NOT NULL,
                    last_status BOOLEAN,
                    last_checked TIMESTAMP WITH TIME ZONE,
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS ignored_addresses (
                    address VARCHAR(44) PRIMARY KEY,
                    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS bot_buttons (
                    bot_name VARCHAR(255) NOT NULL,
                    button_label VARCHAR(255) NOT NULL,
                    button_url VARCHAR(255) NOT NULL,
                    PRIMARY KEY (bot_name, button_label),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS message_text_permissions (
                    bot_name VARCHAR(255) NOT NULL,
                    entity_id BIGINT NOT NULL,
                    allow BOOLEAN NOT NULL DEFAULT FALSE,
                    PRIMARY KEY (bot_name, entity_id),
                    FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                );
                CREATE OR REPLACE FUNCTION delete_old_calls() RETURNS void AS $$
                BEGIN
                    DELETE FROM calls WHERE detected_at < NOW() - INTERVAL '2 months';
                    DELETE FROM tracked_calls WHERE posted_at < NOW() - INTERVAL '30 days' AND monitoring = FALSE;
                    DELETE FROM ignored_addresses WHERE added_at < NOW() - INTERVAL '30 days';
                END;
                $$ LANGUAGE plpgsql;
            """)
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'message_text_permissions') THEN
                        CREATE TABLE message_text_permissions (
                            bot_name VARCHAR(255) NOT NULL,
                            entity_id BIGINT NOT NULL,
                            allow BOOLEAN NOT NULL DEFAULT FALSE,
                            PRIMARY KEY (bot_name, entity_id),
                            FOREIGN KEY (bot_name) REFERENCES bots(name) ON DELETE CASCADE
                        );
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'message_text_permissions' AND column_name = 'allow') THEN
                        ALTER TABLE message_text_permissions ADD COLUMN allow BOOLEAN NOT NULL DEFAULT FALSE;
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'message_text_permissions' AND column_name = 'entity_id' AND data_type != 'bigint') THEN
                        ALTER TABLE message_text_permissions ALTER COLUMN entity_id TYPE BIGINT USING entity_id::BIGINT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'bots' AND column_name = 'is_userbot') THEN
                        ALTER TABLE bots ADD COLUMN is_userbot BOOLEAN DEFAULT FALSE;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'calls' AND column_name = 'message_id') THEN
                        ALTER TABLE calls ADD COLUMN message_id BIGINT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'calls' AND column_name = 'mention_count') THEN
                        ALTER TABLE calls ADD COLUMN mention_count INTEGER DEFAULT 1;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'calls' AND column_name = 'chat_name') THEN
                        ALTER TABLE calls ADD COLUMN chat_name VARCHAR(255);
                    END IF;
                    IF EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name = 'tracked_calls' AND column_name = 'max_multiplier') THEN
                        ALTER TABLE tracked_calls RENAME COLUMN max_multiplier TO max_percentage_increase;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'max_percentage_increase') THEN
                        ALTER TABLE tracked_calls ADD COLUMN max_percentage_increase FLOAT DEFAULT 0.0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'original_initial_market_cap') THEN
                        ALTER TABLE tracked_calls ADD COLUMN original_initial_market_cap FLOAT;
                        UPDATE tracked_calls SET original_initial_market_cap = initial_market_cap;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'first_alert_message_id') THEN
                        ALTER TABLE tracked_calls ADD COLUMN first_alert_message_id BIGINT;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'bots' AND column_name = 'min_market_cap') THEN
                        ALTER TABLE bots ADD COLUMN min_market_cap FLOAT DEFAULT 0.0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'bots' AND column_name = 'bonded_only') THEN
                        ALTER TABLE bots ADD COLUMN bonded_only BOOLEAN DEFAULT FALSE;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'ath_price') THEN
                        ALTER TABLE tracked_calls ADD COLUMN ath_price FLOAT DEFAULT 0.0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'ath_market_cap') THEN
                        ALTER TABLE tracked_calls ADD COLUMN ath_market_cap FLOAT DEFAULT 0.0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'ath_timestamp') THEN
                        ALTER TABLE tracked_calls ADD COLUMN ath_timestamp TIMESTAMP WITH TIME ZONE;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'monitoring') THEN
                        ALTER TABLE tracked_calls ADD COLUMN monitoring BOOLEAN DEFAULT TRUE;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'original_caller_user_id') THEN
                        ALTER TABLE tracked_calls ADD COLUMN original_caller_user_id VARCHAR(255);
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                  WHERE table_name = 'tracked_calls' AND column_name = 'last_alert_market_cap') THEN
                        ALTER TABLE tracked_calls ADD COLUMN last_alert_market_cap FLOAT;
                    END IF;
                    -- Remove duplicates from tracked_calls
                    DELETE FROM tracked_calls t1
                    USING (
                        SELECT bot_name, address, MIN(posted_at) AS min_posted_at
                        FROM tracked_calls
                        GROUP BY bot_name, address
                    ) t2
                    WHERE t1.bot_name = t2.bot_name AND t1.address = t2.address AND t1.posted_at > t2.min_posted_at;
                    -- Adding unique constraint on (bot_name, address)
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_indexes 
                        WHERE tablename = 'tracked_calls' AND indexname = 'unique_tracked_call'
                    ) THEN
                        CREATE UNIQUE INDEX unique_tracked_call ON tracked_calls (bot_name, address);
                    END IF;
                END;
                $$;
            """)
            conn.commit()
            logger.info("Database tables created or updated successfully")
        except Exception as e:
            logger.error(f"Failed to create database tables: {e}")
            raise
        finally:
            if 'conn' in locals():
                self.release_connection(conn, cursor)

    def get_connection(self):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self.conn_pool.getconn()
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                conn.commit()
                return conn, cursor
            except psycopg2.OperationalError as e:
                logger.error(f"Database connection failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    try:
                        self.conn_pool.putconn(conn, close=True)
                    except:
                        pass
                else:
                    raise Exception(f"Failed to connect to database after {max_retries} attempts: {e}")
        raise Exception("Failed to establish database connection")

    def release_connection(self, conn, cursor):
        try:
            conn.commit()
            cursor.close()
            self.conn_pool.putconn(conn)
        except Exception as e:
            logger.error(f"Failed to release database connection: {e}")

    def close_pool(self):
        try:
            self.conn_pool.closeall()
            logger.info("Database connection pool closed")
        except Exception as e:
            logger.error(f"Failed to close database connection pool: {e}")

    def add_bot(self, name, api_id, api_hash, session, sensitivity=50.0, is_userbot=False):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO bots (name, api_id, api_hash, session, sensitivity, is_userbot) VALUES (%s, %s, %s, %s, %s, %s)",
                (name, api_id, api_hash, session, sensitivity, is_userbot)
            )
            return True
        except psycopg2.IntegrityError:
            return False
        finally:
            self.release_connection(conn, cursor)

    def remove_bot(self, name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("DELETE FROM bots WHERE name = %s", (name,))
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_bots(self):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT name, api_id, api_hash, session, sensitivity, is_userbot FROM bots")
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def set_sensitivity(self, bot_name, sensitivity):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "UPDATE bots SET sensitivity = %s WHERE name = %s",
                (sensitivity, bot_name)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def set_min_market_cap(self, bot_name, min_mc):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("UPDATE bots SET min_market_cap = %s WHERE name = %s", (min_mc, bot_name))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_min_market_cap(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT min_market_cap FROM bots WHERE name = %s", (bot_name,))
            result = cursor.fetchone()
            return result[0] if result else 0.0
        finally:
            self.release_connection(conn, cursor)

    def set_bonded_only(self, bot_name, bonded_only):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("UPDATE bots SET bonded_only = %s WHERE name = %s", (bonded_only, bot_name))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_bonded_only(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT bonded_only FROM bots WHERE name = %s", (bot_name,))
            result = cursor.fetchone()
            return result[0] if result else False
        finally:
            self.release_connection(conn, cursor)

    def add_user(self, bot_name, user_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO monitored_users (bot_name, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (bot_name, user_id)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def remove_user(self, bot_name, user_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "DELETE FROM monitored_users WHERE bot_name = %s AND user_id = %s",
                (bot_name, user_id)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_users(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT user_id FROM monitored_users WHERE bot_name = %s", (bot_name,))
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.release_connection(conn, cursor)

    def add_group(self, bot_name, group_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO target_groups (bot_name, group_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (bot_name, group_id)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def remove_group(self, bot_name, group_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "DELETE FROM target_groups WHERE bot_name = %s AND group_id = %s",
                (bot_name, group_id)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_groups(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT group_id FROM target_groups WHERE bot_name = %s", (bot_name,))
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.release_connection(conn, cursor)

    def add_channel(self, bot_name, channel_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO target_channels (bot_name, channel_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (bot_name, channel_id)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def remove_channel(self, bot_name, channel_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "DELETE FROM target_channels WHERE bot_name = %s AND channel_id = %s",
                (bot_name, channel_id)
            )
            cursor.execute(
                "DELETE FROM channel_names WHERE bot_name = %s AND channel_id = %s",
                (bot_name, channel_id)
            )
            cursor.execute(
                "DELETE FROM channel_keywords WHERE bot_name = %s AND channel_id = %s",
                (bot_name, channel_id)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_channels(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT channel_id FROM target_channels WHERE bot_name = %s", (bot_name,))
            return [row[0] for row in cursor.fetchall()]
        finally:
            self.release_connection(conn, cursor)

    def set_channel_name(self, bot_name, channel_id, custom_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("""
                INSERT INTO channel_names (bot_name, channel_id, custom_name) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (bot_name, channel_id) 
                DO UPDATE SET custom_name = %s
            """, (bot_name, channel_id, custom_name, custom_name))
        finally:
            self.release_connection(conn, cursor)

    def get_channel_name(self, bot_name, channel_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT custom_name FROM channel_names WHERE bot_name = %s AND channel_id = %s",
                (bot_name, channel_id)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.release_connection(conn, cursor)

    def add_keyword(self, bot_name, user_id, keyword):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO keywords (bot_name, user_id, keyword) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (bot_name, user_id, keyword)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def remove_keyword(self, bot_name, user_id, keyword):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "DELETE FROM keywords WHERE bot_name = %s AND user_id = %s AND keyword = %s",
                (bot_name, user_id, keyword)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_keywords(self, bot_name, user_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT keyword FROM keywords WHERE bot_name = %s AND user_id = %s",
                (bot_name, user_id)
            )
            return [row[0].lower() for row in cursor.fetchall()]
        finally:
            self.release_connection(conn, cursor)

    def add_channel_keyword(self, bot_name, channel_id, keyword):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO channel_keywords (bot_name, channel_id, keyword) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (bot_name, channel_id, keyword)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def remove_channel_keyword(self, bot_name, channel_id, keyword):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "DELETE FROM channel_keywords WHERE bot_name = %s AND channel_id = %s AND keyword = %s",
                (bot_name, channel_id, keyword)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_channel_keywords(self, bot_name, channel_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT keyword FROM channel_keywords WHERE bot_name = %s AND channel_id = %s",
                (bot_name, channel_id)
            )
            return [row[0].lower() for row in cursor.fetchall()]
        finally:
            self.release_connection(conn, cursor)

    def set_custom_alert_template(self, bot_name, template):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO custom_alert_templates (bot_name, template) VALUES (%s, %s) ON CONFLICT (bot_name) DO UPDATE SET template = %s",
                (bot_name, template, template)
            )
        finally:
            self.release_connection(conn, cursor)

    def get_custom_alert_template(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT template FROM custom_alert_templates WHERE bot_name = %s", (bot_name,))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.release_connection(conn, cursor)

    def set_repeat_alert_template(self, bot_name, template):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO repeat_alert_templates (bot_name, template) VALUES (%s, %s) ON CONFLICT (bot_name) DO UPDATE SET template = %s",
                (bot_name, template, template)
            )
        finally:
            self.release_connection(conn, cursor)

    def get_repeat_alert_template(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT template FROM repeat_alert_templates WHERE bot_name = %s", (bot_name,))
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.release_connection(conn, cursor)

    def set_reply_template(self, bot_name, template):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO reply_templates (bot_name, template) VALUES (%s, %s) ON CONFLICT (bot_name) DO UPDATE SET template = %s",
                (bot_name, template, template)
            )
        finally:
            self.release_connection(conn, cursor)

    def get_reply_template(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT template FROM reply_templates WHERE bot_name = %s", (bot_name,))
            result = cursor.fetchone()
            return result[0] if result else "<b>{emoji} {multiplier}x</b> | <code>💹From</code> <b>{initial_mc}</b> ↗️ <b>{current_mc}</b> <code>within</code> ⏰<b>{time}</b>"
        finally:
            self.release_connection(conn, cursor)

    def set_milestone_reply(self, bot_name, multiplier, template):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO milestone_replies (bot_name, multiplier, template) VALUES (%s, %s, %s) ON CONFLICT (bot_name, multiplier) DO UPDATE SET template = %s",
                (bot_name, multiplier, template, template)
            )
        finally:
            self.release_connection(conn, cursor)

    def get_milestone_replies(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT multiplier, template FROM milestone_replies WHERE bot_name = %s ORDER BY multiplier",
                (bot_name,)
            )
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def set_uptime_url(self, bot_name, url):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO uptime_urls (bot_name, url) VALUES (%s, %s) ON CONFLICT (bot_name) DO UPDATE SET url = %s",
                (bot_name, url, url)
            )
        finally:
            self.release_connection(conn, cursor)

    def get_uptime_urls(self):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT bot_name, url FROM uptime_urls")
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def update_uptime_status(self, bot_name, status, timestamp):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "UPDATE uptime_urls SET last_status = %s, last_checked = %s WHERE bot_name = %s",
                (status, timestamp, bot_name)
            )
        finally:
            self.release_connection(conn, cursor)

    def log_call(self, bot_name, address, chat_id, user_id, message_text, message_id, detected_at, chat_name, mention_count=1):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO calls (bot_name, address, chat_id, user_id, message_text, message_id, detected_at, chat_name, mention_count) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (bot_name, address, chat_id, user_id, message_text, message_id, detected_at, chat_name, mention_count)
            )
        finally:
            self.release_connection(conn, cursor)

    def get_existing_mention_count(self, bot_name, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT COUNT(*) FROM calls WHERE bot_name = %s AND address = %s", (bot_name, address))
            return cursor.fetchone()[0]
        finally:
            self.release_connection(conn, cursor)

    def get_original_caller_user_id(self, bot_name, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT user_id FROM calls WHERE bot_name = %s AND address = %s ORDER BY detected_at ASC LIMIT 1",
                (bot_name, address)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.release_connection(conn, cursor)

    def get_last_alert_mc(self, bot_name, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT last_alert_market_cap FROM tracked_calls WHERE bot_name = %s AND address = %s",
                (bot_name, address)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.release_connection(conn, cursor)

    def update_last_alert_mc(self, bot_name, address, new_mc):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "UPDATE tracked_calls SET last_alert_market_cap = %s WHERE bot_name = %s AND address = %s",
                (new_mc, bot_name, address)
            )
            conn.commit()
        finally:
            self.release_connection(conn, cursor)

    def get_first_alert_message_id(self, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT MIN(first_alert_message_id) FROM tracked_calls WHERE address = %s AND first_alert_message_id IS NOT NULL",
                (address,)
            )
            result = cursor.fetchone()[0]
            return result if result else None
        finally:
            self.release_connection(conn, cursor)

    def is_duplicate_call(self, bot_name, chat_id, message_id, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT 1 FROM calls WHERE bot_name = %s AND chat_id = %s AND message_id = %s AND address = %s",
                (bot_name, chat_id, message_id, address)
            )
            return bool(cursor.fetchone())
        finally:
            self.release_connection(conn, cursor)

    def track_call(self, bot_name, address, initial_market_cap, initial_bonding_status, alert_message_id, first_alert_message_id, posted_at, chat_id, message_id, original_caller_user_id, ath_price=0.0, ath_market_cap=0.0, ath_timestamp=None):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("""
                INSERT INTO tracked_calls (
                    bot_name, address, initial_market_cap, original_initial_market_cap, 
                    initial_bonding_status, max_percentage_increase, alert_message_id, 
                    first_alert_message_id, posted_at, last_checked, original_chat_id, 
                    original_message_id, bonding_alert_sent, original_caller_user_id, 
                    last_alert_market_cap, ath_price, ath_market_cap, ath_timestamp, monitoring
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bot_name, address) DO UPDATE SET
                    alert_message_id = EXCLUDED.alert_message_id,
                    last_checked = EXCLUDED.last_checked,
                    bonding_alert_sent = EXCLUDED.bonding_alert_sent,
                    ath_price = EXCLUDED.ath_price,
                    ath_market_cap = EXCLUDED.ath_market_cap,
                    ath_timestamp = EXCLUDED.ath_timestamp,
                    monitoring = EXCLUDED.monitoring
            """, (
                bot_name, address, initial_market_cap, initial_market_cap, initial_bonding_status, 
                0.0, alert_message_id, first_alert_message_id, posted_at, posted_at, chat_id, message_id, 
                False, original_caller_user_id, initial_market_cap, ath_price, ath_market_cap, ath_timestamp, True
            ))
        finally:
            self.release_connection(conn, cursor)

    def get_tracked_calls(self, bot_name=None):
        conn, cursor = self.get_connection()
        try:
            if bot_name:
                cursor.execute("""
                    SELECT id, bot_name, address, initial_market_cap, original_initial_market_cap, 
                           initial_bonding_status, max_percentage_increase, alert_message_id, 
                           first_alert_message_id, posted_at, original_chat_id, original_message_id, 
                           bonding_alert_sent, ath_price, ath_market_cap, ath_timestamp, 
                           original_caller_user_id, last_alert_market_cap
                    FROM tracked_calls 
                    WHERE bot_name = %s AND monitoring = TRUE
                """, (bot_name,))
            else:
                cursor.execute("""
                    SELECT id, bot_name, address, initial_market_cap, original_initial_market_cap, 
                           initial_bonding_status, max_percentage_increase, alert_message_id, 
                           first_alert_message_id, posted_at, original_chat_id, original_message_id, 
                           bonding_alert_sent, ath_price, ath_market_cap, ath_timestamp, 
                           original_caller_user_id, last_alert_market_cap
                    FROM tracked_calls 
                    WHERE monitoring = TRUE
                """)
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def update_tracked_call(self, call_id, max_percentage_increase, last_checked, ath_price, ath_market_cap, ath_timestamp, bonding_alert_sent=None, monitoring=None):
        conn, cursor = self.get_connection()
        try:
            set_clause = "max_percentage_increase = %s, last_checked = %s, ath_price = %s, ath_market_cap = %s, ath_timestamp = %s"
            params = [max_percentage_increase, last_checked, ath_price, ath_market_cap, ath_timestamp]
            if bonding_alert_sent is not None:
                set_clause += ", bonding_alert_sent = %s"
                params.append(bonding_alert_sent)
            if monitoring is not None:
                set_clause += ", monitoring = %s"
                params.append(monitoring)
            params.append(call_id)
            cursor.execute(f"UPDATE tracked_calls SET {set_clause} WHERE id = %s", tuple(params))
        finally:
            self.release_connection(conn, cursor)

    def cleanup_tracked_calls(self, cutoff_date):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("DELETE FROM tracked_calls WHERE posted_at < %s AND monitoring = FALSE", (cutoff_date,))
            return cursor.rowcount
        finally:
            self.release_connection(conn, cursor)

    def calculate_caller_stats(self, bot_name, user_id):
        conn, cursor = self.get_connection()
        try:
            utc = pytz.utc
            one_month_ago = datetime.now(utc) - timedelta(days=30)
            cursor.execute(
                "SELECT COUNT(*) FROM calls WHERE bot_name = %s AND user_id = %s AND detected_at >= %s",
                (bot_name, user_id, one_month_ago)
            )
            total_calls = cursor.fetchone()[0]
            if total_calls == 0:
                return {"hit_rate_5x": 0.0, "hit_rate_2x": 0.0, "migration_rate": 0.0, "total_calls": 0}
            cursor.execute("""
                SELECT COUNT(DISTINCT c.id) 
                FROM calls c 
                JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                        AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                WHERE c.bot_name = %s AND c.user_id = %s AND c.detected_at >= %s AND tc.max_percentage_increase >= 500
            """, (bot_name, user_id, one_month_ago))
            calls_5x = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(DISTINCT c.id) 
                FROM calls c 
                JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                        AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                WHERE c.bot_name = %s AND c.user_id = %s AND c.detected_at >= %s AND tc.max_percentage_increase >= 100
            """, (bot_name, user_id, one_month_ago))
            calls_2x = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(DISTINCT c.id) 
                FROM calls c 
                JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                        AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                WHERE c.bot_name = %s AND c.user_id = %s AND c.detected_at >= %s AND tc.initial_bonding_status = FALSE
            """, (bot_name, user_id, one_month_ago))
            total_unbonded = cursor.fetchone()[0]
            cursor.execute("""
                SELECT COUNT(DISTINCT c.id) 
                FROM calls c 
                JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                        AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                WHERE c.bot_name = %s AND c.user_id = %s AND c.detected_at >= %s AND tc.initial_bonding_status = FALSE 
                AND EXISTS (
                    SELECT 1 
                    FROM tracked_calls tc2 
                    WHERE tc2.bot_name = tc.bot_name AND tc2.address = tc.address 
                    AND tc2.posted_at > tc.posted_at AND tc2.initial_bonding_status = TRUE
                )
            """, (bot_name, user_id, one_month_ago))
            bonded_from_unbonded = cursor.fetchone()[0]
            hit_rate_5x = (calls_5x / total_calls) * 100 if total_calls > 0 else 0.0
            hit_rate_2x = (calls_2x / total_calls) * 100 if total_calls > 0 else 0.0
            migration_rate = (bonded_from_unbonded / total_unbonded) * 100 if total_unbonded > 0 else 0.0
            return {
                "hit_rate_5x": round(hit_rate_5x, 2),
                "hit_rate_2x": round(hit_rate_2x, 2),
                "migration_rate": round(migration_rate, 2),
                "total_calls": total_calls
            }
        finally:
            self.release_connection(conn, cursor)

    def get_caller_best_calls(self, bot_name, user_id, limit=10):
        conn, cursor = self.get_connection()
        try:
            utc = pytz.utc
            one_month_ago = datetime.now(utc) - timedelta(days=30)
            cursor.execute("""
                SELECT c.address, tc.max_percentage_increase, tc.alert_message_id, 
                       tc.posted_at, c.chat_id, c.message_id, c.message_text
                FROM calls c
                JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                        AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                WHERE c.bot_name = %s AND c.user_id = %s AND c.detected_at >= %s
                ORDER BY tc.max_percentage_increase DESC
                LIMIT %s
            """, (bot_name, user_id, one_month_ago, limit))
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def calculate_group_stats(self, bot_name, group_id):
        conn, cursor = self.get_connection()
        try:
            utc = pytz.utc
            one_month_ago = datetime.now(utc) - timedelta(days=30)
            cursor.execute("""
                SELECT DISTINCT mu.user_id 
                FROM monitored_users mu
                JOIN calls c ON mu.user_id = c.user_id AND mu.bot_name = c.bot_name
                WHERE mu.bot_name = %s AND c.chat_id = %s AND c.detected_at >= %s
            """, (bot_name, group_id, one_month_ago))
            monitored_users = [row[0] for row in cursor.fetchall()]
            if not monitored_users:
                return {"hit_rate_5x": 0.0, "hit_rate_2x": 0.0, "migration_rate": 0.0, "total_calls": 0, "users": []}
            total_calls = 0
            calls_5x = 0
            calls_2x = 0
            total_unbonded = 0
            bonded_from_unbonded = 0
            for user_id in monitored_users:
                cursor.execute(
                    "SELECT COUNT(*) FROM calls WHERE bot_name = %s AND user_id = %s AND chat_id = %s AND detected_at >= %s",
                    (bot_name, user_id, group_id, one_month_ago)
                )
                total_calls += cursor.fetchone()[0]
                cursor.execute("""
                    SELECT COUNT(DISTINCT c.id) 
                    FROM calls c 
                    JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                            AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                    WHERE c.bot_name = %s AND c.user_id = %s AND c.chat_id = %s AND c.detected_at >= %s AND tc.max_percentage_increase >= 500
                """, (bot_name, user_id, group_id, one_month_ago))
                calls_5x += cursor.fetchone()[0]
                cursor.execute("""
                    SELECT COUNT(DISTINCT c.id) 
                    FROM calls c 
                    JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                            AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                    WHERE c.bot_name = %s AND c.user_id = %s AND c.chat_id = %s AND c.detected_at >= %s AND tc.max_percentage_increase >= 100
                """, (bot_name, user_id, group_id, one_month_ago))
                calls_2x += cursor.fetchone()[0]
                cursor.execute("""
                    SELECT COUNT(DISTINCT c.id) 
                    FROM calls c 
                    JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                            AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                    WHERE c.bot_name = %s AND c.user_id = %s AND c.chat_id = %s AND c.detected_at >= %s AND tc.initial_bonding_status = FALSE
                """, (bot_name, user_id, group_id, one_month_ago))
                total_unbonded += cursor.fetchone()[0]
                cursor.execute("""
                    SELECT COUNT(DISTINCT c.id) 
                    FROM calls c 
                    JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                            AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                    WHERE c.bot_name = %s AND c.user_id = %s AND c.chat_id = %s AND c.detected_at >= %s 
                    AND tc.initial_bonding_status = FALSE 
                    AND EXISTS (
                        SELECT 1 
                        FROM tracked_calls tc2 
                        WHERE tc2.bot_name = tc.bot_name AND tc2.address = tc.address 
                        AND tc2.posted_at > tc.posted_at AND tc2.initial_bonding_status = TRUE
                    )
                """, (bot_name, user_id, group_id, one_month_ago))
                bonded_from_unbonded += cursor.fetchone()[0]
            hit_rate_5x = (calls_5x / total_calls) * 100 if total_calls > 0 else 0.0
            hit_rate_2x = (calls_2x / total_calls) * 100 if total_calls > 0 else 0.0
            migration_rate = (bonded_from_unbonded / total_unbonded) * 100 if total_unbonded > 0 else 0.0
            return {
                "hit_rate_5x": round(hit_rate_5x, 2),
                "hit_rate_2x": round(hit_rate_2x, 2),
                "migration_rate": round(migration_rate, 2),
                "total_calls": total_calls,
                "users": monitored_users
            }
        finally:
            self.release_connection(conn, cursor)

    def get_group_best_calls(self, bot_name, group_id, limit=10):
        conn, cursor = self.get_connection()
        try:
            utc = pytz.utc
            one_month_ago = datetime.now(utc) - timedelta(days=30)
            cursor.execute("""
                SELECT c.address, tc.max_percentage_increase, tc.alert_message_id, 
                       tc.posted_at, c.chat_id, c.message_id, c.user_id, c.message_text
                FROM calls c
                JOIN tracked_calls tc ON c.bot_name = tc.bot_name AND c.address = tc.address 
                                        AND c.chat_id = tc.original_chat_id AND c.message_id = tc.original_message_id
                WHERE c.bot_name = %s AND c.chat_id = %s AND c.detected_at >= %s
                ORDER BY tc.max_percentage_increase DESC
                LIMIT %s
            """, (bot_name, group_id, one_month_ago, limit))
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def add_ignored_address(self, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO ignored_addresses (address) VALUES (%s) ON CONFLICT DO NOTHING",
                (address,)
            )
            conn.commit()
            logger.debug(f"Added address {address} to ignored_addresses")
        finally:
            self.release_connection(conn, cursor)

    def is_ignored_address(self, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT 1 FROM ignored_addresses WHERE address = %s", (address,))
            return bool(cursor.fetchone())
        finally:
            self.release_connection(conn, cursor)

    def add_button(self, bot_name, button_label, button_url):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "INSERT INTO bot_buttons (bot_name, button_label, button_url) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (bot_name, button_label, button_url)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def remove_button(self, bot_name, button_label):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "DELETE FROM bot_buttons WHERE bot_name = %s AND button_label = %s",
                (bot_name, button_label)
            )
            return cursor.rowcount > 0
        finally:
            self.release_connection(conn, cursor)

    def get_buttons(self, bot_name):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("SELECT button_label, button_url FROM bot_buttons WHERE bot_name = %s", (bot_name,))
            return cursor.fetchall()
        finally:
            self.release_connection(conn, cursor)

    def get_initial_market_cap(self, bot_name, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT initial_market_cap FROM tracked_calls WHERE bot_name = %s AND address = %s ORDER BY posted_at ASC LIMIT 1",
                (bot_name, address)
            )
            result = cursor.fetchone()
            return result[0] if result else None
        finally:
            self.release_connection(conn, cursor)

    def set_message_text_permission(self, bot_name, entity_id, allow):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("""
                INSERT INTO message_text_permissions (bot_name, entity_id, allow) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (bot_name, entity_id) 
                DO UPDATE SET allow = %s
            """, (bot_name, entity_id, allow, allow))
            conn.commit()
        finally:
            self.release_connection(conn, cursor)

    def get_message_text_permission(self, bot_name, entity_id):
        conn, cursor = self.get_connection()
        try:
            cursor.execute(
                "SELECT allow FROM message_text_permissions WHERE bot_name = %s AND entity_id = %s",
                (bot_name, entity_id)
            )
            result = cursor.fetchone()
            return result[0] if result is not None else False
        finally:
            self.release_connection(conn, cursor)

    def get_first_call(self, address):
        conn, cursor = self.get_connection()
        try:
            cursor.execute("""
                SELECT bot_name, chat_id, message_id, user_id, detected_at 
                FROM calls 
                WHERE address = %s 
                ORDER BY detected_at ASC 
                LIMIT 1
            """, (address,))
            return cursor.fetchone()
        finally:
            self.release_connection(conn, cursor)

# --- DexScreener API Integration ---
class DexScreenerAPI:
    def __init__(self, api_url):
        self.api_url = api_url
        self.rate_limiter = AsyncLimiter(4, 1)

    async def fetch_dex_data(self, chain_id: str, token_address: str) -> dict:
        url = f"{self.api_url}/{token_address}"
        retries = 3
        for attempt in range(retries):
            try:
                async with self.rate_limiter:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(url, headers={"User-Agent": "TelegramBot/1.0"}) as resp:
                            if resp.status == 429:
                                logger.warning(f"Rate limit hit on DexScreener API for {token_address}, attempt {attempt + 1}")
                                await asyncio.sleep(2 ** attempt)
                                continue
                            if resp.status != 200:
                                logger.warning(f"No pairs found for address {token_address} in DexScreener response")
                                return {"is_bonded": False, "is_paid": False, "token_data": None}
                            data = await resp.json()
                            pairs = data.get("pairs", [])
                            if not pairs:
                                logger.warning(f"No pairs found for address {token_address} in DexScreener response: {data}")
                                return {"is_bonded": False, "is_paid": False, "token_data": None}
                            token_data = pairs[0]
                            required_keys = [
                                "chainId", "dexId", "url", "pairAddress", "baseToken", "quoteToken",
                                "priceNative", "priceUsd", "txns", "volume", "priceChange", "fdv"
                            ]
                            missing_keys = [key for key in required_keys if key not in token_data]
                            if missing_keys:
                                logger.error(f"DexScreener API missing keys for {token_address}: {missing_keys}")
                                return {"is_bonded": False, "is_paid": False, "token_data": None}
                            pair_created_at = token_data.get("pairCreatedAt")
                            pair_created_at = (
                                datetime.fromtimestamp(pair_created_at / 1000, tz=pytz.utc)
                                if pair_created_at else None
                            )
                            liquidity = token_data.get("liquidity", {})
                            liquidity_usd = liquidity.get("usd", 0)
                            price_change = token_data.get("priceChange", {})
                            volume = token_data.get("volume", {})
                            txns = token_data.get("txns", {})
                            current_price = float(token_data.get("priceUsd", 0))
                            info = token_data.get("info", {})
                            is_paid = any(key in info for key in ["imageUrl", "header", "openGraph", "websites", "socials"])
                            return {
                                "is_bonded": liquidity_usd > 0,
                                "is_paid": is_paid,
                                "token_data": {
                                    "chain_id": token_data["chainId"],
                                    "dex_id": token_data["dexId"],
                                    "url": token_data["url"],
                                    "pair_address": token_data["pairAddress"],
                                    "base_token": {
                                        "name": token_data["baseToken"].get("name", "Unknown"),
                                        "symbol": token_data["baseToken"].get("symbol", "N/A")
                                    },
                                    "quote_token": {
                                        "name": token_data["quoteToken"].get("name", "Unknown"),
                                        "symbol": token_data["quoteToken"].get("symbol", "N/A")
                                    },
                                    "price_native": token_data["priceNative"],
                                    "price_usd": token_data["priceUsd"],
                                    "txns": {
                                        "h24": txns.get("h24", {"buys": 0, "sells": 0}),
                                        "h6": txns.get("h6", {"buys": 0, "sells": 0}),
                                        "h1": txns.get("h1", {"buys": 0, "sells": 0}),
                                        "m5": txns.get("m5", {"buys": 0, "sells": 0}),
                                    },
                                    "volume": {
                                        "h24": volume.get("h24", 0),
                                        "h6": volume.get("h6", 0),
                                        "h1": volume.get("h1", 0),
                                        "m5": volume.get("m5", 0),
                                    },
                                    "price_change": {
                                        "h24": price_change.get("h24", 0),
                                        "h6": price_change.get("h6", 0),
                                        "h1": price_change.get("h1", 0),
                                        "m5": price_change.get("m5", 0),
                                    },
                                    "fdv": token_data["fdv"],
                                    "market_cap": token_data.get("marketCap"),
                                    "pair_created_at": pair_created_at,
                                    "liquidity_usd": liquidity_usd,
                                    "current_price": current_price
                                }
                            }
            except Exception as e:
                logger.error(f"Failed to fetch DexScreener data for {token_address}: {e}")
                if attempt < retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return {"is_bonded": False, "is_paid": False, "token_data": None}
        return {"is_bonded": False, "is_paid": False, "token_data": None}

# --- Bot Management ---
class BotManager:
    def __init__(self, config, db, dex_api):
        self.config = config
        self.db = db
        self.dex_api = dex_api
        self.clients = {}
        self.alert_channel = int(config["ALERT_CHANNEL_ID"]) if config["ALERT_CHANNEL_ID"] else None
        self.admin_entities = {}
        self.bot_sensitivities = {}
        self.userbot_status = {}
        self.handlers = {}
        self.processing_locks = {}
        self.send_lock = Lock()
        self.pending_buttons = {}

    async def resolve_admin_entities(self, client):
        for admin_id in self.config["ADMIN_IDS"]:
            try:
                admin_entity = await client.get_entity(int(admin_id))
                self.admin_entities[admin_id] = admin_entity
                logger.info(f"Resolved admin entity for {admin_id}")
            except ValueError as e:
                logger.warning(f"Cannot resolve admin {admin_id}: {e}. Ensure they have messaged the bot.")
            except Exception as e:
                logger.error(f"Failed to resolve admin entity for {admin_id}: {e}")

    async def notify_admins(self, client, message):
        for admin_id, admin_entity in self.admin_entities.items():
            try:
                await client.send_message(admin_entity, message)
                logger.info(f"Notified admin {admin_id} with message: {message[:50]}...")
            except ValueError as e:
                logger.warning(f"Skipping notification to admin {admin_id}: {e}")
            except Exception as e:
                logger.error(f"Failed to notify admin {admin_id}: {e}")

    def check_admin(self, user_id: str) -> bool:
        is_admin = str(user_id) in self.config["ADMIN_IDS"]
        if not is_admin:
            logger.warning(f"User {user_id} attempted to execute a command but is not an admin.")
        return is_admin

    async def add_bot(self, api_id: int, api_hash: str, session: str, name: str):
        try:
            client = TelegramClient(StringSession(session), api_id, api_hash)
            await client.connect()
            is_userbot = False
            if not await client.is_user_authorized():
                if self.config["BOT_TOKEN"]:
                    await client.start(bot_token=self.config["BOT_TOKEN"])
                    session_str = client.session.save()
                    logger.info(f"Bot {name} started with BOT_TOKEN, treated as bot")
                else:
                    return f"❌ No BOT_TOKEN provided for {name}, and session is invalid."
            else:
                is_userbot = True
                session_str = session
                logger.info(f"Bot {name} started with valid user session, treated as userbot")
            if not self.db.add_bot(name, api_id, api_hash, session_str, is_userbot=is_userbot):
                return f"❌ Bot {name} already exists!"
            self.clients[name] = client
            self.bot_sensitivities[name] = 50.0
            self.userbot_status[name] = is_userbot
            await self.setup_handlers(client, name)
            asyncio.create_task(client.run_until_disconnected())
            logger.info(f"Bot {name} added successfully (Userbot: {is_userbot})")
            return f"✅ Bot {name} added! (Userbot: {is_userbot})"
        except Exception as e:
            logger.error(f"Error adding bot {name}: {e}")
            return f"❌ Error adding bot {name}: {str(e)}"

    async def remove_bot(self, name: str):
        if self.db.remove_bot(name):
            if name in self.clients:
                await self.clients[name].disconnect()
                del self.clients[name]
            if name in self.bot_sensitivities:
                del self.bot_sensitivities[name]
            if name in self.userbot_status:
                del self.userbot_status[name]
            if name in self.handlers:
                del self.handlers[name]
            if name in self.pending_buttons:
                del self.pending_buttons[name]
            logger.info(f"Bot {name} removed successfully")
            return f"✅ Bot {name} removed!"
        logger.warning(f"Attempted to remove non-existent bot {name}")
        return f"❌ Bot {name} not found."

    async def send_message(self, client, message, parse_mode=None, reply_to=None, buttons=None):
        bot_name = next((name for name, c in self.clients.items() if c == client), "unknown")
        is_userbot = self.userbot_status.get(bot_name, False)
        if not self.alert_channel:
            logger.error(f"Bot {bot_name} cannot send message: ALERT_CHANNEL_ID not set.")
            await self.notify_admins(client, f"⚠️ Bot {bot_name} failed to send message: ALERT_CHANNEL_ID not set.")
            return None
        max_attempts = 4
        async with self.send_lock:
            for attempt in range(max_attempts):
                try:
                    if not str(self.alert_channel).startswith('-100') or len(str(self.alert_channel)) != 14:
                        raise ValueError(f"Invalid ALERT_CHANNEL_ID format: {self.alert_channel}")
                    await client.get_entity(self.alert_channel)
                    if buttons:
                        logger.info(f"Bot {bot_name} sending message with buttons: {[(b.text, b.url) for row in buttons for b in row]}")
                    else:
                        logger.info(f"Bot {bot_name} sending message without buttons")
                    sent_message = await client.send_message(
                        self.alert_channel, 
                        message, 
                        parse_mode=parse_mode, 
                        reply_to=reply_to,
                        link_preview=False,
                        buttons=buttons
                    )
                    logger.info(f"Bot {bot_name} sent message to {self.alert_channel} with ID {sent_message.id}")
                    await asyncio.sleep(1)
                    return sent_message
                except (ValueError, ChannelInvalidError) as e:
                    logger.error(f"Bot {bot_name} failed to send message to {self.alert_channel} (attempt {attempt + 1}/{max_attempts}): {e}")
                    if attempt == max_attempts - 1:
                        await self.notify_admins(client, f"⚠️ Bot {bot_name} failed to send message after {max_attempts} attempts: {str(e)}.")
                        return None
                except ChatWriteForbiddenError as e:
                    logger.error(f"Bot {bot_name} lacks permission to post in {self.alert_channel} (attempt {attempt + 1}/{max_attempts}): {e}")
                    if attempt == max_attempts - 1:
                        await self.notify_admins(client, f"⚠️ Bot {bot_name} lacks 'Post Messages' permission after {max_attempts} attempts: {str(e)}")
                        return None
                except Exception as e:
                    logger.error(f"Bot {bot_name} unexpected error sending message to {self.alert_channel} (attempt {attempt + 1}/{max_attempts}): {e}")
                    if attempt == max_attempts - 1:
                        await self.notify_admins(client, f"⚠️ Bot {bot_name} unexpected error after {max_attempts} attempts: {str(e)}")
                    return None
                if attempt < max_attempts - 1:
                    await asyncio.sleep(5)
            return None

    async def setup_handlers(self, client, bot_name: str):
        pass

    async def test_market_cap_reply(self, client, bot_name: str, address: str, initial_mc: float, current_mc: float, posted_at: datetime, message_id: int):
        utc = pytz.utc
        if posted_at.tzinfo is None:
            posted_at = utc.localize(posted_at)
        now = datetime.now(utc)
        multiplier = current_mc / initial_mc if initial_mc > 0 else 1.0
        emoji = "🎉" if multiplier < 2.5 else "🔥" if multiplier < 5 else "🚀" if multiplier < 10 else "🌙" if multiplier < 50 else "🌕"
        time_diff = format_time_diff(posted_at, now)
        initial_mc_str = format_market_cap(initial_mc)
        current_mc_str = format_market_cap(current_mc)
        milestone_replies = self.db.get_milestone_replies(bot_name)
        milestone_template = None
        for multiplier_threshold, template in milestone_replies:
            if multiplier >= multiplier_threshold and multiplier < multiplier_threshold * 1.1:
                milestone_template = template
                break
        template = milestone_template or self.db.get_reply_template(bot_name)
        data = {
            "emoji": emoji,
            "multiplier": f"{multiplier:.1f}",
            "initial_mc": initial_mc_str,
            "current_mc": current_mc_str,
            "time": time_diff
        }
        reply = template.format(**data)
        sent_message = await self.send_message(client, reply, parse_mode="Markdown", reply_to=message_id)
        if sent_message:
            return f"✅ Test reply sent for {bot_name} with multiplier {multiplier:.1f}x"
        return f"❌ Failed to send test reply for {bot_name}"

# --- Scheduler for Cleanup ---
class Scheduler:
    def __init__(self, db, bot_manager):
        self.db = db
        self.bot_manager = bot_manager

    async def run_cleanup(self, client):
        while True:
            try:
                conn, cursor = self.db.get_connection()
                cursor.execute("SELECT delete_old_calls()")
                conn.commit()
                logger.info("Database cleanup completed")
                await asyncio.sleep(86400)
            except Exception as e:
                logger.error(f"Error in database cleanup: {e}")
                await self.bot_manager.notify_admins(client, f"⚠️ Error in database cleanup: {str(e)}")
                await asyncio.sleep(3600)
            finally:
                if 'conn' in locals():
                    self.db.release_connection(conn, cursor)

# --- Uptime Monitoring ---
class UptimeMonitor:
    def __init__(self, db, bot_manager):
        self.db = db
        self.bot_manager = bot_manager
        self.session = None
        self.running = False
        self.task = None

    async def initialize_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    async def check_url(self, url: str) -> bool:
        await self.initialize_session()
        try:
            async with self.session.get(url, timeout=10) as response:
                return response.status == 200
        except Exception as e:
            logger.error(f"Uptime check failed for {url}: {e}")
            return False

    async def monitor_uptime(self, client):
        if self.running:
            logger.warning("Uptime monitor already running, skipping new instance")
            return
        self.running = True
        logger.info("Starting uptime monitor")
        await self.initialize_session()
        while self.running:
            try:
                urls = self.db.get_uptime_urls()
                if not urls:
                    logger.info("No uptime URLs configured, skipping checks")
                    await asyncio.sleep(300)
                    continue
                for bot_name, url in urls:
                    status = await self.check_url(url)
                    self.db.update_uptime_status(bot_name, status, datetime.now(pytz.utc))
                    utc_time = datetime.now(pytz.utc)
                    status_str = "Up" if status else "Down"
                    logger.info(f"Uptime check for bot {bot_name}: URL={url}, Status={status_str}, Time={utc_time}")
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Error in monitor_uptime: {e}", exc_info=True)
                await self.bot_manager.notify_admins(client, f"⚠️ Critical error in monitor_uptime: {str(e)}")
                await asyncio.sleep(300)
            except asyncio.CancelledError:
                logger.info("Uptime monitor task cancelled")
                self.running = False
                raise

    async def close(self):
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        if self.session:
            await self.session.close()
        self.running = False
        logger.info("Uptime monitor closed")

    def is_running(self):
        return self.running

# --- Message Handling ---
SOLANA_ADDRESS_PATTERN = r'[1-9A-HJ-NP-Za-km-z]{43,44}'
KEYWORD_ALERT_TEMPLATE = "🔔 Keyword Detected! 🔔\nKeyword: {what_keyword_was_detected}\nChat: {name_of_group_chat}\nTime: {detected_at}"
ADDRESS_ALERT_TEMPLATE = """🚨 Address Detected! 🚨
Solana Address: {address}
Chat: {name_of_group_chat}
Time: {detected_at}"""
DEX_ADDRESS_ALERT_TEMPLATE = """🚀 Token Address Alert! 🚀
Solana Address: {address}
Token: {token_name} ({token_symbol})
Status: {bonding_status}
DEX Paid: {dex_paid}
Price (USD): ${price_usd} ({price_change_h24}% in 24h)
ATH: {ath}
Price (Native): {price_native}
Volume (24h): ${volume_h24}
Volume (6h): ${volume_h6}
Volume (1h): ${volume_h1}
Volume (5m): ${volume_m5}
Liquidity: ${liquidity_usd}
FDV: ${fdv}
Market Cap: {market_cap}
Multiplier: {multiplier}x
DEX: {dex_id}
Pair URL: {pair_url}
Chain ID: {chain_id}
Pair Address: {pair_address}
Quote Token: {quote_token_name} ({quote_token_symbol})
Transactions (24h): Buys: {txns_h24_buys}, Sells: {txns_h24_sells}
Transactions (6h): Buys: {txns_h6_buys}, Sells: {txns_h6_sells}
Transactions (1h): Buys: {txns_h1_buys}, Sells: {txns_h1_sells}
Transactions (5m): Buys: {txns_m5_buys}, Sells: {txns_m5_sells}
Price Change (5m): {price_change_m5}%
Price Change (1h): {price_change_h1}%
Price Change (6h): {price_change_h6}%
Pair Age: {pair_created_at}
Caller Stats: 5x Hit Rate: {hit_rate_5x}%, 2x Hit Rate: {hit_rate_2x}%, Migration Rate: {migration_rate}%
Chat: {name_of_group_chat}
Detected At: {detected_at}
{message_text_line}"""
DEFAULT_REPEAT_ALERT_TEMPLATE = """{mention_count} 💊${token_symbol} • {token_name}
└ #{quote_token_symbol} • ⏳ {pair_created_at}
🪬Caller Stats - {first_name_of_the_user}
├ Hit rate 5x: {hit_rate_5x}% ⋅ 2x: {hit_rate_2x}%
└ Migration rate: {migration_rate}%
📊 Token Stats
├ MC: {market_cap} | FDV: {fdv}
├ LIQ: {liquidity_usd}
├ Status: {bonding_status}
├ DEX Paid: {dex_paid}
├ Price: ${price_usd}
├ ATH: {ath}
├ Multiplier: {multiplier}x
└ DEX: {dex_id} | {chain_id}
{message_text_line}
💭 See Comments for more details - @fcalld"""

class MessageHandler(BotManager):
    def __init__(self, config, db, dex_api):
        super().__init__(config, db, dex_api)

    def is_contract_address(self, message_text, address):
        contract_pattern = r'(?:contract\s*address|ca)\s*[:=]?\s*' + re.escape(address)
        match = re.search(contract_pattern, message_text.lower(), re.IGNORECASE)
        if match:
            logger.debug(f"Found contract address pattern for {address} in message: {message_text[:100]}")
        else:
            logger.debug(f"No contract address pattern for {address} in message: {message_text[:100]}")
        return bool(match)

    async def setup_handlers(self, client, bot_name: str):
        try:
            if bot_name in self.handlers:
                client.remove_event_handler(self.handlers[bot_name])
                logger.debug(f"Removed existing handler for {bot_name}")
            target_groups = set(self.db.get_groups(bot_name))
            target_channels = set(self.db.get_channels(bot_name))
            monitored_users = set(self.db.get_users(bot_name))
            channel_keywords = {}
            for channel_id in target_channels:
                keywords = self.db.get_channel_keywords(bot_name, channel_id)
                if keywords:
                    channel_keywords[channel_id] = set(keywords)
            sensitivity = self.db.get_bots()
            sensitivity = next((row[4] for row in sensitivity if row[0] == bot_name), 50.0)
            self.bot_sensitivities[bot_name] = sensitivity
            logger.info(f"Bot {bot_name} monitoring: groups={target_groups}, channels={target_channels}, users={monitored_users}, channel_keywords={channel_keywords}")

            @client.on(events.NewMessage(chats=target_groups | target_channels))
            async def handler(event):
                logger.debug(f"Bot {bot_name} event triggered for chat {event.chat_id}")
                try:
                    if not event.message.text:
                        logger.debug(f"Bot {bot_name} skipping empty message in chat {event.chat_id}")
                        return
                    chat_id = event.chat_id
                    message_text = event.message.text
                    chat = await event.get_chat()
                    chat_name = getattr(chat, 'title', None) or getattr(chat, 'username', None) or str(chat_id)
                    logger.info(f"Bot {bot_name} processing message in chat {chat_id}: '{message_text[:50]}...'")
                    if chat_id in target_channels:
                        custom_name = self.db.get_channel_name(bot_name, chat_id)
                        chat_name = custom_name if custom_name else chat_name
                        found_addresses = set(re.findall(SOLANA_ADDRESS_PATTERN, message_text))
                        channel_keywords_set = channel_keywords.get(chat_id, set())
                        found_channel_keywords = [
                            keyword for keyword in channel_keywords_set
                            if keyword in message_text.lower()
                        ]
                        if found_addresses or found_channel_keywords:
                            sender = await event.get_sender()
                            user_id = str(sender.id) if sender else None
                            sender_name = chat_name
                            logger.info(f"Bot {bot_name} detected in channel {chat_id}: addresses={found_addresses}, keywords={found_channel_keywords}")
                            await self.process_detections(
                                client, bot_name, chat_id, user_id, message_text,
                                found_addresses, found_channel_keywords, sender_name, chat_name, event
                            )
                        return
                    if chat_id in target_groups:
                        sender = await event.get_sender()
                        if not sender:
                            return
                        user_id = str(sender.id)
                        if user_id not in monitored_users:
                            return
                        first_name = getattr(sender, 'first_name', 'Unknown')
                        last_name = getattr(sender, 'last_name', '') or ''
                        sender_name = f"{first_name} {last_name}".strip()
                        found_addresses = set(re.findall(SOLANA_ADDRESS_PATTERN, message_text))
                        user_keywords = self.db.get_keywords(bot_name, user_id)
                        found_user_keywords = [
                            keyword for keyword in user_keywords
                            if keyword in message_text.lower()
                        ]
                        if found_addresses or found_user_keywords:
                            await self.process_detections(
                                client, bot_name, chat_id, user_id, message_text,
                                found_addresses, found_user_keywords, sender_name, chat_name, event
                            )
                except Exception as e:
                    logger.error(f"Bot {bot_name} error in message handler for chat {event.chat_id}: {e}")
                    await self.notify_admins(client, f"⚠️ Bot {bot_name} error in message handler: {str(e)}")
            self.handlers[bot_name] = handler
            logger.info(f"Bot {bot_name} message handler registered")
        except Exception as e:
            logger.error(f"Bot {bot_name} error in setup_handlers: {e}")
            await self.notify_admins(client, f"⚠️ Bot {bot_name} failed to setup handlers: {str(e)}")

    async def process_detections(self, client, bot_name, chat_id, user_id, message_text, found_addresses, found_keywords, sender_name, chat_name, event):
        utc = pytz.utc
        current_time = datetime.now(utc)
        ist = pytz.timezone('Asia/Kolkata')
        formatted_time = current_time.astimezone(ist).strftime("%B %d, %Y, %I:%M %p IST")
        custom_template = self.db.get_custom_alert_template(bot_name)
        repeat_template = self.db.get_repeat_alert_template(bot_name) or DEFAULT_REPEAT_ALERT_TEMPLATE
        message_id = event.message.id
        lock_key = f"{chat_id}:{message_id}"
        if lock_key not in self.processing_locks:
            self.processing_locks[lock_key] = asyncio.Lock()
        async with self.processing_locks[lock_key]:
            logger.info(f"Bot {bot_name} processing detections in chat {chat_id}, message {message_id}: addresses={found_addresses}, keywords={found_keywords}")
            try:
                chat = await event.get_chat()
                chat_username = getattr(chat, 'username', None)
                if found_addresses:
                    for address in found_addresses:
                        if self.db.is_ignored_address(address) and not self.is_contract_address(message_text, address):
                            logger.info(f"Skipping ignored address {address} in chat {chat_id}, message {message_id}")
                            continue
                        try:
                            if self.db.is_duplicate_call(bot_name, chat_id, message_id, address):
                                logger.info(f"Skipping duplicate address {address} in chat {chat_id}, message {message_id}")
                                continue
                            # Log the mention first
                            self.db.log_call(bot_name, address, chat_id, user_id, message_text, message_id, current_time, chat_name, 1)
                            # Get total mentions for this bot and address
                            total_mentions = self.db.get_existing_mention_count(bot_name, address)
                            dex_data = await self.dex_api.fetch_dex_data("solana", address)
                            token_data = dex_data["token_data"]
                            if token_data is None:
                                self.db.add_ignored_address(address)
                                logger.info(f"Marked address {address} as ignored (likely a wallet).")
                                continue
                            market_cap = float(token_data.get("market_cap", 0))
                            is_bonded = dex_data["is_bonded"]
                            min_mc = self.db.get_min_market_cap(bot_name)
                            bonded_only = self.db.get_bonded_only(bot_name)
                            if market_cap < min_mc or (bonded_only and not is_bonded):
                                logger.debug(f"Skipping address {address} due to filters: mc={market_cap}, bonded={is_bonded}")
                                continue
                            tracked_calls = self.db.get_tracked_calls(bot_name)
                            ath_price = 0.0
                            ath_market_cap = 0.0
                            ath_timestamp = None
                            for call in tracked_calls:
                                if call[2] == address and call[1] == bot_name:
                                    ath_price = call[13]
                                    ath_market_cap = call[14]
                                    ath_timestamp = call[15]
                                    break
                            current_mc = float(token_data["market_cap"])
                            current_price = float(token_data["current_price"])
                            new_ath_price = max(ath_price, current_price)
                            new_ath_market_cap = max(ath_market_cap, current_mc)
                            new_ath_timestamp = current_time if new_ath_market_cap > ath_market_cap else ath_timestamp
                            ath_mc_formatted = format_market_cap(new_ath_market_cap)
                            percentage_diff = ((current_mc - ath_market_cap) / ath_market_cap * 100) if ath_market_cap > 0 else 0
                            time_diff = format_time_diff(ath_timestamp, current_time) if ath_timestamp else "now!"
                            ath = f"{ath_mc_formatted} ({percentage_diff:+.0f}% / {time_diff})"
                            bonding_status = "Bonded" if is_bonded else "Not Bonded"
                            dex_paid = "✅" if dex_data["is_paid"] else "❌"
                            stats = self.db.calculate_caller_stats(bot_name, user_id or "unknown")
                            initial_mc = self.db.get_initial_market_cap(bot_name, address)
                            multiplier = current_mc / initial_mc if initial_mc and initial_mc > 0 else 1.0
                            allow_message_text = self.db.get_message_text_permission(bot_name, chat_id)
                            message_text_line = f"Message: \"{message_text[:1000]}\"" if allow_message_text else ""
                            try:
                                data = {
                                    "address": address,
                                    "first_name_of_the_user": sender_name,
                                    "name_of_group_chat": chat_name,
                                    "detected_at": formatted_time,
                                    "hit_rate_5x": stats["hit_rate_5x"],
                                    "hit_rate_2x": stats["hit_rate_2x"],
                                    "migration_rate": stats["migration_rate"],
                                    "mention_count": format_mention_count(total_mentions),
                                    "message_text": message_text[:1000],
                                    "message_text_line": message_text_line,
                                    "token_name": token_data.get("base_token", {}).get("name", "Unknown"),
                                    "token_symbol": token_data.get("base_token", {}).get("symbol", "N/A"),
                                    "bonding_status": bonding_status,
                                    "dex_paid": dex_paid,
                                    "price_usd": token_data.get("price_usd", "N/A"),
                                    "ath": ath,
                                    "price_native": token_data.get("price_native", "N/A"),
                                    "price_change_h24": token_data.get("price_change", {}).get("h24", 0),
                                    "price_change_h6": token_data.get("price_change", {}).get("h6", 0),
                                    "price_change_h1": token_data.get("price_change", {}).get("h1", 0),
                                    "price_change_m5": token_data.get("price_change", {}).get("m5", 0),
                                    "volume_h24": f"{float(token_data.get('volume', {}).get('h24', 0)):,.2f}",
                                    "volume_h6": f"{float(token_data.get('volume', {}).get('h6', 0)):,.2f}",
                                    "volume_h1": f"{float(token_data.get('volume', {}).get('h1', 0)):,.2f}",
                                    "volume_m5": f"{float(token_data.get('volume', {}).get('m5', 0)):,.2f}",
                                    "liquidity_usd": f"{float(token_data.get('liquidity_usd', 0)):,.2f}",
                                    "fdv": f"{float(token_data.get('fdv', 0)):,.2f}",
                                    "market_cap": format_market_cap(token_data.get("market_cap")),
                                    "multiplier": f"{multiplier:.1f}",
                                    "dex_id": token_data.get("dex_id", "N/A"),
                                    "pair_url": token_data.get("url", "N/A"),
                                    "chain_id": token_data.get("chain_id", "N/A"),
                                    "pair_address": token_data.get("pair_address", "N/A"),
                                    "quote_token_name": token_data.get("quote_token", {}).get("name", "Unknown"),
                                    "quote_token_symbol": token_data.get("quote_token", {}).get("symbol", "N/A"),
                                    "txns_h24_buys": token_data.get("txns", {}).get("h24", {}).get("buys", 0),
                                    "txns_h24_sells": token_data.get("txns", {}).get("h24", {}).get("sells", 0),
                                    "txns_h6_buys": token_data.get("txns", {}).get("h6", {}).get("buys", 0),
                                    "txns_h6_sells": token_data.get("txns", {}).get("h6", {}).get("sells", 0),
                                    "txns_h1_buys": token_data.get("txns", {}).get("h1", {}).get("buys", 0),
                                    "txns_h1_sells": token_data.get("txns", {}).get("h1", {}).get("sells", 0),
                                    "txns_m5_buys": token_data.get("txns", {}).get("m5", {}).get("buys", 0),
                                    "txns_m5_sells": token_data.get("txns", {}).get("m5", {}).get("sells", 0),
                                    "pair_created_at": format_time_diff(token_data["pair_created_at"], current_time) if token_data["pair_created_at"] else "N/A"
                                }
                                first_alert_msg_id = self.db.get_first_alert_message_id(address)
                                reply_to = first_alert_msg_id if first_alert_msg_id and total_mentions > 1 else None
                                buttons = self.pending_buttons.get(bot_name, [])
                                if buttons:
                                    logger.info(f"Using pending buttons for {bot_name}: {buttons}")
                                    buttons_markup = buttons
                                    self.pending_buttons[bot_name] = []
                                else:
                                    buttons = self.db.get_buttons(bot_name)
                                    logger.info(f"Fetched buttons for {bot_name}: {buttons}")
                                    buttons_markup = [[Button.url(label, url)] for label, url in buttons]
                                # Handle alert logic
                                if total_mentions == 1:
                                    # First mention: send initial alert and start tracking
                                    template = custom_template or DEX_ADDRESS_ALERT_TEMPLATE
                                    alert_message = template.format(**data)
                                    sent_message = await self.send_message(client, alert_message, parse_mode="Markdown", reply_to=reply_to, buttons=buttons_markup)
                                    if sent_message and token_data.get("market_cap"):
                                        first_call = self.db.get_first_call(address)
                                        global_first_alert_id = sent_message.id
                                        self.db.track_call(
                                            bot_name, address, float(token_data["market_cap"]), dex_data["is_bonded"],
                                            sent_message.id, global_first_alert_id, current_time, chat_id, message_id,
                                            user_id, new_ath_price, new_ath_market_cap, new_ath_timestamp
                                        )
                                else:
                                    # Subsequent mentions
                                    original_caller_user_id = self.db.get_original_caller_user_id(bot_name, address)
                                    last_alert_mc = self.db.get_last_alert_mc(bot_name, address) or initial_mc
                                    if user_id == original_caller_user_id:
                                        sensitivity = self.bot_sensitivities.get(bot_name, 50.0) / 100
                                        if current_mc > last_alert_mc * (1 + sensitivity):
                                            reply = f"Gain Alert: Market cap increased significantly from {format_market_cap(last_alert_mc)} to {format_market_cap(current_mc)}!"
                                            sent_message = await self.send_message(client, reply, parse_mode="Markdown", reply_to=first_alert_msg_id)
                                            if sent_message:
                                                self.db.update_last_alert_mc(bot_name, address, current_mc)
                                    else:
                                        user_mentions = self.db.get_existing_mention_count(bot_name, address)  # This counts all mentions for the user
                                        conn, cursor = self.db.get_connection()
                                        cursor.execute(
                                            "SELECT COUNT(*) FROM calls WHERE bot_name = %s AND address = %s AND user_id = %s",
                                            (bot_name, address, user_id)
                                        )
                                        user_mentions = cursor.fetchone()[0]
                                        self.db.release_connection(conn, cursor)
                                        if user_mentions == 1:
                                            template = repeat_template
                                            alert_message = template.format(**data)
                                            sent_message = await self.send_message(client, alert_message, parse_mode="Markdown", reply_to=reply_to, buttons=buttons_markup)
                            except Exception as e:
                                logger.error(f"Error constructing alert for address {address}: {e}")
                                continue
                        except Exception as e:
                            logger.error(f"Error processing address {address} in chat {chat_id}, message {message_id}: {e}")
                            continue
                if found_keywords:
                    for keyword in found_keywords:
                        if self.db.is_duplicate_call(bot_name, chat_id, message_id, f"keyword:{keyword}"):
                            logger.info(f"Skipping duplicate keyword {keyword} in chat {chat_id}, message {message_id}")
                            continue
                        self.db.log_call(bot_name, f"keyword:{keyword}", chat_id, user_id, message_text, message_id, current_time, chat_name, 1)
                        alert_message = KEYWORD_ALERT_TEMPLATE.format(
                            what_keyword_was_detected=keyword,
                            name_of_group_chat=chat_name,
                            detected_at=formatted_time
                        )
                        await self.send_message(client, alert_message, parse_mode="Markdown")
            finally:
                del self.processing_locks[lock_key]

    async def monitor_tracked_calls(self, client):
        bot_name = next((name for name, c in self.clients.items() if c == client), "unknown")
        while True:
            try:
                tracked_calls = self.db.get_tracked_calls(bot_name)
                for call in tracked_calls:
                    (call_id, call_bot_name, address, initial_mc, orig_initial_mc, is_bonded, max_percentage_increase, 
                     alert_msg_id, first_alert_msg_id, posted_at, orig_chat_id, orig_msg_id, bonding_alert_sent, 
                     ath_price, ath_market_cap, ath_timestamp, original_caller_user_id, last_alert_mc) = call
                    if call_bot_name != bot_name:
                        continue
                    dex_data = await self.dex_api.fetch_dex_data("solana", address)
                    token_data = dex_data["token_data"]
                    if not token_data or not token_data.get("market_cap"):
                        continue
                    current_mc = float(token_data["market_cap"])
                    current_price = float(token_data["current_price"])
                    new_ath_price = max(ath_price, current_price)
                    new_ath_market_cap = max(ath_market_cap, current_mc)
                    new_ath_timestamp = datetime.now(pytz.utc) if new_ath_market_cap > ath_market_cap else ath_timestamp
                    new_max_percentage_increase = max(max_percentage_increase, (current_mc / initial_mc) * 100) if initial_mc > 0 else 0
                    is_bonded_now = dex_data["is_bonded"]
                    
                    if current_mc < 0.7 * initial_mc:
                        self.db.update_tracked_call(call_id, new_max_percentage_increase, datetime.now(pytz.utc), 
                                                    new_ath_price, new_ath_market_cap, new_ath_timestamp, 
                                                    bonding_alert_sent, monitoring=False)
                        logger.info(f"Stopped monitoring {address} for {bot_name}: MC {current_mc} < 70% of initial {initial_mc}")
                        continue
                    
                    sensitivity = self.bot_sensitivities.get(bot_name, 50.0) / 100
                    last_alert_mc = last_alert_mc or initial_mc
                    if current_mc > last_alert_mc * (1 + sensitivity):
                        previous_mc = last_alert_mc
                        time_since_last_alert = format_time_diff(posted_at, datetime.now(pytz.utc))
                        increase_percentage = ((current_mc - previous_mc) / previous_mc) * 100 if previous_mc > 0 else ((current_mc - initial_mc) / initial_mc) * 100
                        emoji = "🎉" if increase_percentage < 10 else "🔥" if increase_percentage < 50 else "🌕"
                        initial_mc_str = format_market_cap(initial_mc)
                        current_mc_str = format_market_cap(current_mc)
                        time_diff = format_time_diff(posted_at, datetime.now(pytz.utc))
                        multiplier = current_mc / initial_mc if initial_mc > 0 else 1.0
                        template = self.db.get_reply_template(bot_name)
                        data = {
                            "emoji": emoji,
                            "multiplier": f"{multiplier:.1f}",
                            "initial_mc": initial_mc_str,
                            "current_mc": current_mc_str,
                            "time": time_diff
                        }
                        reply = template.format(**data)
                        if first_alert_msg_id:
                            sent_message = await self.send_message(client, reply, parse_mode="Markdown", reply_to=first_alert_msg_id)
                            if sent_message:
                                self.db.update_last_alert_mc(bot_name, address, current_mc)

                    if not is_bonded and is_bonded_now and not bonding_alert_sent:
                        time_to_bond = format_time_diff(posted_at, datetime.now(pytz.utc))
                        bonding_alert = f"Token has been **bonded**, achieved `within` **{time_to_bond}**"
                        if first_alert_msg_id:
                            await self.send_message(client, bonding_alert, parse_mode="Markdown", reply_to=first_alert_msg_id)
                        bonding_alert_sent = True

                    self.db.update_tracked_call(call_id, new_max_percentage_increase, datetime.now(pytz.utc), 
                                                new_ath_price, new_ath_market_cap, new_ath_timestamp, 
                                                bonding_alert_sent if not is_bonded and is_bonded_now else bonding_alert_sent)
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Bot {bot_name} error in monitor_tracked_calls: {e}")
                await self.notify_admins(client, f"⚠️ Bot {bot_name} error in monitor_tracked_calls: {str(e)}")
                await asyncio.sleep(60)

# --- Main Application ---
app = Flask(__name__)

@app.route('/')
def health_check():
    return 'OK', 200

flask_running = True

def run_flask(port):
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

async def setup_management_bot():
    config = load_config()
    db = Database(config["DATABASE_URL"])
    dex_api = DexScreenerAPI(config["DEX_API_URL"])
    bot_manager = MessageHandler(config, db, dex_api)
    scheduler = Scheduler(db, bot_manager)
    uptime_monitor = UptimeMonitor(db, bot_manager)
    management_bot = TelegramClient('management', int(config["MANAGEMENT_API_ID"]), config["MANAGEMENT_API_HASH"])
    try:
        if config["BOT_TOKEN"]:
            await management_bot.start(bot_token=config["BOT_TOKEN"])
        else:
            await management_bot.start()
        logger.info("Management bot started successfully")
        await bot_manager.resolve_admin_entities(management_bot)
        bots = db.get_bots()
        for name, api_id, api_hash, session, sensitivity, is_userbot in bots:
            client = TelegramClient(StringSession(session), api_id, api_hash)
            bot_manager.clients[name] = client
            bot_manager.bot_sensitivities[name] = sensitivity
            bot_manager.userbot_status[name] = is_userbot
            await client.connect()
            if is_userbot:
                if not await client.is_user_authorized():
                    logger.error(f"Userbot {name} session invalid. Skipping.")
                    continue
            else:
                if config["BOT_TOKEN"]:
                    await client.start(bot_token=config["BOT_TOKEN"])
                else:
                    logger.error(f"Bot {name} requires BOT_TOKEN but none provided. Skipping.")
                    continue
            await bot_manager.setup_handlers(client, name)
            asyncio.create_task(client.run_until_disconnected())
            logger.info(f"Loaded bot {name} (Userbot: {is_userbot})")

        @management_bot.on(events.NewMessage(pattern=r'^/start'))
        async def start(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this bot.")
                return
            await event.reply(
                "👋 Welcome to the Bot Management System!\n\n"
                "Available commands:\n"
                "/add_bot <api_id> <api_hash> <session> <name> - Add a new bot\n"
                "/remove_bot <name> - Remove a bot\n"
                "/list_bots - List all bots\n"
                "/add_user <bot_name> <user_id> - Add a monitored user\n"
                "/remove_user <bot_name> <user_id> - Remove a monitored user\n"
                "/list_users <bot_name> - List monitored users\n"
                "/add_group <bot_name> <group_id> - Add a target group\n"
                "/remove_group <bot_name> <group_id> - Remove a target group\n"
                "/list_groups <bot_name> - List target groups\n"
                "/add_channel <bot_name> <channel_id> - Add a target channel\n"
                "/remove_channel <bot_name> <channel_id> - Remove a target channel\n"
                "/list_channels <bot_name> - List target channels\n"
                "/set_channel_name <bot_name> <channel_id> <name> - Set custom channel name\n"
                "/add_keyword <bot_name> <user_id> <keyword> - Add a keyword for a user\n"
                "/remove_keyword <bot_name> <user_id> <keyword> - Remove a keyword\n"
                "/list_keywords <bot_name> <user_id> - List keywords for a user\n"
                "/add_channel_keyword <bot_name> <channel_id> <keyword> - Add a keyword for a channel\n"
                "/remove_channel_keyword <bot_name> <channel_id> <keyword> - Remove a channel keyword\n"
                "/list_channel_keywords <bot_name> <channel_id> - List channel keywords\n"
                "/set_alert <channel_id> - Set alert channel\n"
                "/set_sensitivity <bot_name> <sensitivity> - Set bot sensitivity\n"
                "/set_custom_alert <bot_name> <template> - Set custom alert template\n"
                "/get_custom_alert <bot_name> - View custom alert template\n"
                "/set_repeat_alert <bot_name> <template> - Set repeat alert template\n"
                "/get_repeat_alert <bot_name> - View repeat alert template\n"
                "/set_reply <bot_name> <template> - Set reply template\n"
                "/set_milestone_reply <bot_name> <multiplier> <template> - Set milestone reply\n"
                "/list_replies <bot_name> - List reply templates\n"
                "/set_uptime <bot_name> <url> - Set uptime URL\n"
                "/test_reply <bot_name> <address> <initial_mc> <current_mc> <posted_at> - Test reply template\n"
                "/caller_stats <bot_name> <user_id or @username> - Get caller stats\n"
                "/group_stats <bot_name> <group_id or @groupname> - Get group stats\n"
                "/filter mc <bot_name> <amount> - Set minimum market cap filter\n"
                "/filter bonded <bot_name> <on/off> - Set bonded only filter\n"
                "/set_buttons <bot_name> <button_label> <button_url> - Set buttons for a bot\n"
                "/add_post_buttons <bot_name> - Add buttons for next post\n"
                "/done - Finish adding buttons\n"
                "/check_address <contract_address> - Check coin details\n"
                "/check_scan <coin_address> - Comprehensive coin data scan\n"
                "/message_text <bot_name> <entity_id> <allow/deny> - Set message text permission"
            )

        def validate_template_placeholders(template: str, required_placeholders: set) -> bool:
            found_placeholders = set(re.findall(r'\{(\w+)\}', template))
            missing = required_placeholders - found_placeholders
            if missing:
                logger.warning(f"Template missing required placeholders: {missing}")
                return False
            return True

        CUSTOM_ALERT_REQUIRED = {"address", "name_of_group_chat", "detected_at"}
        REPEAT_ALERT_REQUIRED = {"mention_count", "token_symbol", "token_name", "market_cap", "bonding_status"}
        REPLY_REQUIRED = {"emoji", "multiplier", "initial_mc", "current_mc", "time"}

        @management_bot.on(events.NewMessage(pattern=r'^/add_bot\s+(\d+)\s+(\S+)\s+(\S+)\s+(\S+)'))
        async def add_bot(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command  command.")
                return
            api_id, api_hash, session, name = event.pattern_match.groups()
            result = await bot_manager.add_bot(int(api_id), api_hash, session, name)
            await event.reply(result)

        @management_bot.on(events.NewMessage(pattern=r'^/remove_bot\s+(\S+)'))
        async def remove_bot(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            name = event.pattern_match.group(1)
            result = await bot_manager.remove_bot(name)
            await event.reply(result)

        @management_bot.on(events.NewMessage(pattern=r'^/list_bots'))
        async def list_bots(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bots = db.get_bots()
            if not bots:
                await event.reply("📋 No bots registered.")
                return
            response = "📋 Registered Bots:\n"
            for name, _, _, _, sensitivity, is_userbot in bots:
                status = "Userbot" if is_userbot else "Bot"
                response += f"- {name} (Sensitivity: {sensitivity}, Type: {status})\n"
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/add_user\s+(\S+)\s+(\S+)'))
        async def add_user(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, user_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.add_user(bot_name, user_id):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ User {user_id} added to {bot_name} monitored users.")
            else:
                await event.reply(f"❌ User {user_id} already monitored by {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/remove_user\s+(\S+)\s+(\S+)'))
        async def remove_user(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, user_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.remove_user(bot_name, user_id):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ User {user_id} removed from {bot_name} monitored users.")
            else:
                await event.reply(f"❌ User {user_id} not found in {bot_name} monitored users.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_users\s+(\S+)'))
        async def list_users(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            users = db.get_users(bot_name)
            if not users:
                await event.reply(f"📋 No users monitored by {bot_name}.")
                return
            response = f"📋 Monitored Users for {bot_name}:\n" + "\n".join(f"- {user_id}" for user_id in users)
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/add_group\s+(\S+)\s+(-?\d+)'))
        async def add_group(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, group_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.add_group(bot_name, int(group_id)):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Group {group_id} added to {bot_name} target groups.")
            else:
                await event.reply(f"❌ Group {group_id} already monitored by {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/remove_group\s+(\S+)\s+(-?\d+)'))
        async def remove_group(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, group_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.remove_group(bot_name, int(group_id)):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Group {group_id} removed from {bot_name} target groups.")
            else:
                await event.reply(f"❌ Group {group_id} not found in {bot_name} target groups.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_groups\s+(\S+)'))
        async def list_groups(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            groups = db.get_groups(bot_name)
            if not groups:
                await event.reply(f"📋 No groups monitored by {bot_name}.")
                return
            response = f"📋 Target Groups for {bot_name}:\n" + "\n".join(f"- {group_id}" for group_id in groups)
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/add_channel\s+(\S+)\s+(-?\d+)'))
        async def add_channel(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, channel_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.add_channel(bot_name, int(channel_id)):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Channel {channel_id} added to {bot_name} target channels.")
            else:
                await event.reply(f"❌ Channel {channel_id} already monitored by {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/remove_channel\s+(\S+)\s+(-?\d+)'))
        async def remove_channel(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, channel_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.remove_channel(bot_name, int(channel_id)):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Channel {channel_id} removed from {bot_name} target channels.")
            else:
                await event.reply(f"❌ Channel {channel_id} not found in {bot_name} target channels.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_channels\s+(\S+)'))
        async def list_channels(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            channels = db.get_channels(bot_name)
            if not channels:
                await event.reply(f"📋 No channels monitored by {bot_name}.")
                return
            response = f"📋 Target Channels for {bot_name}:\n"
            for channel_id in channels:
                custom_name = db.get_channel_name(bot_name, channel_id)
                name = custom_name or channel_id
                response += f"- {name} (ID: {channel_id})\n"
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/set_channel_name\s+(\S+)\s+(-?\d+)\s+(.+)'))
        async def set_channel_name(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, channel_id, custom_name = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            db.set_channel_name(bot_name, int(channel_id), custom_name.strip())
            await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
            await event.reply(f"✅ Channel {channel_id} name set to '{custom_name}' for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/add_keyword\s+(\S+)\s+(\S+)\s+(.+)'))
        async def add_keyword(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, user_id, keyword = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.add_keyword(bot_name, user_id, keyword.strip().lower()):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Keyword '{keyword}' added for user {user_id} in {bot_name}.")
            else:
                await event.reply(f"❌ Keyword '{keyword}' already exists for user {user_id} in {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/remove_keyword\s+(\S+)\s+(\S+)\s+(.+)'))
        async def remove_keyword(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, user_id, keyword = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.remove_keyword(bot_name, user_id, keyword.strip().lower()):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Keyword '{keyword}' removed for user {user_id} in {bot_name}.")
            else:
                await event.reply(f"❌ Keyword '{keyword}' not found for user {user_id} in {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_keywords\s+(\S+)\s+(\S+)'))
        async def list_keywords(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, user_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            keywords = db.get_keywords(bot_name, user_id)
            if not keywords:
                await event.reply(f"📋 No keywords for user {user_id} in {bot_name}.")
                return
            response = f"📋 Keywords for user {user_id} in {bot_name}:\n" + "\n".join(f"- {keyword}" for keyword in keywords)
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/add_channel_keyword\s+(\S+)\s+(-?\d+)\s+(.+)'))
        async def add_channel_keyword(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, channel_id, keyword = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.add_channel_keyword(bot_name, int(channel_id), keyword.strip().lower()):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Keyword '{keyword}' added for channel {channel_id} in {bot_name}.")
            else:
                await event.reply(f"❌ Keyword '{keyword}' already exists for channel {channel_id} in {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/remove_channel_keyword\s+(\S+)\s+(-?\d+)\s+(.+)'))
        async def remove_channel_keyword(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, channel_id, keyword = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.remove_channel_keyword(bot_name, int(channel_id), keyword.strip().lower()):
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Keyword '{keyword}' removed for channel {channel_id} in {bot_name}.")
            else:
                await event.reply(f"❌ Keyword '{keyword}' not found for channel {channel_id} in {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_channel_keywords\s+(\S+)\s+(-?\d+)'))
        async def list_channel_keywords(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, channel_id = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            keywords = db.get_channel_keywords(bot_name, int(channel_id))
            if not keywords:
                await event.reply(f"📋 No keywords for channel {channel_id} in {bot_name}.")
                return
            response = f"📋 Keywords for channel {channel_id} in {bot_name}:\n" + "\n".join(f"- {keyword}" for keyword in keywords)
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/set_alert\s+(-?\d+)'))
        async def set_alert(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            channel_id = event.pattern_match.group(1)
            bot_manager.alert_channel = int(channel_id)
            set_key('.env', 'ALERT_CHANNEL_ID', channel_id)
            config["ALERT_CHANNEL_ID"] = channel_id
            await event.reply(f"✅ Alert channel set to {channel_id}.")

        @management_bot.on(events.NewMessage(pattern=r'^/set_sensitivity\s+(\S+)\s+(\d+\.?\d*)'))
        async def set_sensitivity(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, sensitivity = event.pattern_match.groups()
            sensitivity = float(sensitivity)
            if not (0 <= sensitivity <= 100):
                await event.reply("❌ Sensitivity must be between 0 and 100.")
                return
            if db.set_sensitivity(bot_name, sensitivity):
                bot_manager.bot_sensitivities[bot_name] = sensitivity
                if bot_name in bot_manager.clients:
                    await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
                await event.reply(f"✅ Sensitivity for {bot_name} set to {sensitivity}.")
            else:
                await event.reply(f"❌ Bot {bot_name} not found.")

        @management_bot.on(events.NewMessage(pattern=r'^/set_custom_alert\s+(\S+)\s+(.+)'))
        async def set_custom_alert(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, template = event.pattern_match.groups()
            if not validate_template_placeholders(template, CUSTOM_ALERT_REQUIRED):
                await event.reply(f"❌ Template must include: {', '.join(CUSTOM_ALERT_REQUIRED)}")
                return
            db.set_custom_alert_template(bot_name, template)
            if bot_name in bot_manager.clients:
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
            await event.reply(f"✅ Custom alert template set for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/get_custom_alert\s+(\S+)'))
        async def get_custom_alert(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            template = db.get_custom_alert_template(bot_name)
            if template:
                await event.reply(f"📋 Custom alert template for {bot_name}:\n{template}")
            else:
                await event.reply(f"📋 No custom alert template set for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/set_repeat_alert\s+(\S+)\s+(.+)'))
        async def set_repeat_alert(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, template = event.pattern_match.groups()
            if not validate_template_placeholders(template, REPEAT_ALERT_REQUIRED):
                await event.reply(f"❌ Template must include: {', '.join(REPEAT_ALERT_REQUIRED)}")
                return
            db.set_repeat_alert_template(bot_name, template)
            if bot_name in bot_manager.clients:
                await bot_manager.setup_handlers(bot_manager.clients[bot_name], bot_name)
            await event.reply(f"✅ Repeat alert template set for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/get_repeat_alert\s+(\S+)'))
        async def get_repeat_alert(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            template = db.get_repeat_alert_template(bot_name)
            if template:
                await event.reply(f"📋 Repeat alert template for {bot_name}:\n{template}")
            else:
                await event.reply(f"📋 No repeat alert template set for {bot_name}. Using default.")

        @management_bot.on(events.NewMessage(pattern=r'^/set_reply\s+(\S+)\s+(.+)'))
        async def set_reply(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, template = event.pattern_match.groups()
            if not validate_template_placeholders(template, REPLY_REQUIRED):
                await event.reply(f"❌ Template must include: {', '.join(REPLY_REQUIRED)}")
                return
            db.set_reply_template(bot_name, template)
            await event.reply(f"✅ Reply template set for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/set_milestone_reply\s+(\S+)\s+(\d+\.?\d*)\s+(.+)'))
        async def set_milestone_reply(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, multiplier, template = event.pattern_match.groups()
            multiplier = float(multiplier)
            if not validate_template_placeholders(template, REPLY_REQUIRED):
                await event.reply(f"❌ Template must include: {', '.join(REPLY_REQUIRED)}")
                return
            db.set_milestone_reply(bot_name, multiplier, template)
            await event.reply(f"✅ Milestone reply set for {bot_name} at {multiplier}x.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_replies\s+(\S+)'))
        async def list_replies(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            default_template = db.get_reply_template(bot_name)
            milestone_replies = db.get_milestone_replies(bot_name)
            response = f"📋 Reply Templates for {bot_name}:\n\nDefault Template:\n{default_template}\n\nMilestone Templates:\n"
            if milestone_replies:
                for multiplier, template in milestone_replies:
                    response += f"- {multiplier}x: {template}\n"
            else:
                response += "No milestone templates set."
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/set_uptime\s+(\S+)\s+(.+)'))
        async def set_uptime(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, url = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            db.set_uptime_url(bot_name, url.strip())
            await event.reply(f"✅ Uptime URL set for {bot_name}: {url}")

        @management_bot.on(events.NewMessage(pattern=r'^/test_reply\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})'))
        async def test_reply(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, address, initial_mc, current_mc, posted_at = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            try:
                initial_mc = parse_shorthand_value(initial_mc)
                current_mc = parse_shorthand_value(current_mc)
                posted_at = datetime.strptime(posted_at, "%Y-%m-%d %H:%M:%S")
                posted_at = pytz.utc.localize(posted_at)
                result = await bot_manager.test_market_cap_reply(
                    bot_manager.clients[bot_name], bot_name, address, initial_mc, current_mc, posted_at, None
                )
                await event.reply(result)
            except ValueError as e:
                await event.reply(f"❌ Invalid input: {str(e)}")
            except Exception as e:
                await event.reply(f"❌ Error testing reply: {str(e)}")

        @management_bot.on(events.NewMessage(pattern=r'^/caller_stats\s+(\S+)\s+(@?\S+)'))
        async def caller_stats(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, identifier = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot `{bot_name}` not found.", parse_mode="Markdown")
                return
            client = bot_manager.clients[bot_name]
            try:
                user_id = identifier
                if identifier.startswith('@'):
                    entity = await client.get_entity(identifier)
                    user_id = str(entity.id)
                else:
                    entity = await client.get_entity(int(identifier))
                username = getattr(entity, 'username', None)
                first_name = getattr(entity, 'first_name', 'Unknown')
                display_name = f"@{username}" if username else f"{first_name} ({user_id})"
                stats = db.calculate_caller_stats(bot_name, user_id)
                response = (
                    f"📊 **Caller Stats for {display_name} in `{bot_name}`**\n"
                    f"- **5x Hit Rate**: {stats['hit_rate_5x']}% (Calls ≥ 5x: {int(stats['hit_rate_5x'] * stats['total_calls'] / 100)})\n"
                    f"- **2x Hit Rate**: {stats['hit_rate_2x']}% (Calls ≥ 2x: {int(stats['hit_rate_2x'] * stats['total_calls'] / 100)})\n"
                    f"- **Migration Rate**: {stats['migration_rate']}%\n"
                    f"- **Total Calls**: {stats['total_calls']}\n"
                )
                best_calls = db.get_caller_best_calls(bot_name, user_id, limit=5)
                if best_calls:
                    response += "\n**Top 5 Calls**:\n"
                    for idx, (address, max_increase, alert_msg_id, posted_at, chat_id, msg_id, message_text) in enumerate(best_calls, 1):
                        token_data = (await dex_api.fetch_dex_data("solana", address))["token_data"]
                        token_symbol = token_data["base_token"]["symbol"] if token_data else "N/A"
                        multiplier = max_increase / 100 if max_increase else 0.0
                        link = get_telegram_link(int(bot_manager.alert_channel), alert_msg_id, config.get("ALERT_CHANNEL_USERNAME"))
                        response += f"{idx}. [${token_symbol}]({link}) - {multiplier:.2f}x on {posted_at.strftime('%Y-%m-%d')}\n> {message_text[:50]}...\n"
                else:
                    response += "\nNo notable calls found."
                await event.reply(response, parse_mode="Markdown")
            except ValueError:
                await event.reply(f"❌ User `{identifier}` not found.", parse_mode="Markdown")
            except Exception as e:
                await event.reply(f"❌ Error retrieving stats: {str(e)}", parse_mode="Markdown")

        @management_bot.on(events.NewMessage(pattern=r'^/group_stats\s+(\S+)\s+(@?\S+)'))
        async def group_stats(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, identifier = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot `{bot_name}` not found.", parse_mode="Markdown")
                return
            client = bot_manager.clients[bot_name]
            try:
                group_id = identifier
                if identifier.startswith('@'):
                    entity = await client.get_entity(identifier)
                    group_id = str(entity.id)
                else:
                    entity = await client.get_entity(int(identifier))
                group_username = getattr(entity, 'username', None)
                group_title = getattr(entity, 'title', 'Unnamed Group')
                display_name = f"@{group_username}" if group_username else f"{group_title} ({group_id})"
                stats = db.calculate_group_stats(bot_name, int(group_id))
                response = (
                    f"📊 **Group Stats for {display_name} in `{bot_name}`**\n"
                    f"- **5x Hit Rate**: {stats['hit_rate_5x']}% (Calls ≥ 5x: {int(stats['hit_rate_5x'] * stats['total_calls'] / 100)})\n"
                    f"- **2x Hit Rate**: {stats['hit_rate_2x']}% (Calls ≥ 2x: {int(stats['hit_rate_2x'] * stats['total_calls'] / 100)})\n"
                    f"- **Migration Rate**: {stats['migration_rate']}%\n"
                    f"- **Total Calls**: {stats['total_calls']}\n"
                    f"- **Monitored Users**: {len(stats['users'])} ({', '.join(stats['users'][:5])}{'...' if len(stats['users']) > 5 else ''})\n"
                )
                best_calls = db.get_group_best_calls(bot_name, int(group_id), limit=5)
                if best_calls:
                    response += "\n**Top 5 Calls**:\n"
                    for idx, (address, max_increase, alert_msg_id, posted_at, chat_id, msg_id, user_id, message_text) in enumerate(best_calls, 1):
                        user = await client.get_entity(int(user_id)) if user_id else None
                        user_display = f"@{user.username}" if user and getattr(user, 'username', None) else user_id or "Unknown"
                        token_data = (await dex_api.fetch_dex_data("solana", address))["token_data"]
                        token_symbol = token_data["base_token"]["symbol"] if token_data else "N/A"
                        multiplier = max_increase / 100 if max_increase else 0.0
                        link = get_telegram_link(chat_id, msg_id, group_username)
                        response += f"{idx}. [${token_symbol}]({link}) by {user_display} - {multiplier:.2f}x\n"
                else:
                    response += "\nNo notable calls found."
                await event.reply(response, parse_mode="Markdown")
            except ValueError:
                await event.reply(f"❌ Group `{identifier}` not found.", parse_mode="Markdown")
            except Exception as e:
                await event.reply(f"❌ Error retrieving stats: {str(e)}", parse_mode="Markdown")

        @management_bot.on(events.NewMessage(pattern=r'^/filter\s+mc\s+(\S+)\s+(.+)'))
        async def filter_mc(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, amount_str = event.pattern_match.groups()
            try:
                amount = parse_shorthand_value(amount_str)
                if db.set_min_market_cap(bot_name, amount):
                    await event.reply(f"✅ Set minimum market cap for {bot_name} to {amount_str}")
                else:
                    await event.reply(f"❌ Bot {bot_name} not found.")
            except ValueError as e:
                await event.reply(f"❌ Invalid amount: {str(e)}")

        @management_bot.on(events.NewMessage(pattern=r'^/filter\s+bonded\s+(\S+)\s+(on|off)$'))
        async def filter_bonded(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, status = event.pattern_match.groups()
            bonded_only = status.lower() == 'on'
            if db.set_bonded_only(bot_name, bonded_only):
                status_str = "on" if bonded_only else "off"
                await event.reply(f"✅ Set bonded only filter for {bot_name} to {status_str}")
            else:
                await event.reply(f"❌ Bot {bot_name} not found.")

        @management_bot.on(events.NewMessage(pattern=r'^/set_buttons\s+(\S+)\s+(.+)\s+(.+)'))
        async def set_buttons(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, button_label, button_url = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.add_button(bot_name, button_label, button_url):
                await event.reply(f"✅ Button '{button_label}' added for {bot_name} with URL {button_url}.")
            else:
                await event.reply(f"❌ Button '{button_label}' already exists for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/remove_button\s+(\S+)\s+(.+)'))
        async def remove_button(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, button_label = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            if db.remove_button(bot_name, button_label):
                await event.reply(f"✅ Button '{button_label}' removed for {bot_name}.")
            else:
                await event.reply(f"❌ Button '{button_label}' not found for {bot_name}.")

        @management_bot.on(events.NewMessage(pattern=r'^/list_buttons\s+(\S+)'))
        async def list_buttons(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            buttons = db.get_buttons(bot_name)
            if not buttons:
                await event.reply(f"📋 No buttons set for {bot_name}.")
                return
            response = f"📋 Buttons for {bot_name}:\n" + "\n".join(f"- {label}: {url}" for label, url in buttons)
            await event.reply(response)

        @management_bot.on(events.NewMessage(pattern=r'^/add_post_buttons\s+(\S+)'))
        async def add_post_buttons(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name = event.pattern_match.group(1)
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            bot_manager.pending_buttons[bot_name] = []
            await event.reply(f"✅ Started adding buttons for {bot_name}. Send button pairs (label URL) one per message, and finish with /done.")

        @management_bot.on(events.NewMessage(pattern=r'^/done'))
        async def done_adding_buttons(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            for bot_name in list(bot_manager.pending_buttons.keys()):
                buttons = bot_manager.pending_buttons[bot_name]
                await event.reply(f"✅ Finished adding buttons for {bot_name}. {len(buttons)} buttons added.")
                del bot_manager.pending_buttons[bot_name]
                return
            await event.reply("❌ No button addition in progress.")

        @management_bot.on(events.NewMessage(pattern=r'(.+)\s+(https?://\S+)'))
        async def add_button_pair(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                return
            for bot_name in bot_manager.pending_buttons:
                label, url = event.pattern_match.groups()
                bot_manager.pending_buttons[bot_name].append([Button.url(label.strip(), url.strip())])
                await event.reply(f"✅ Added button '{label}' for {bot_name}.")
                return

        @management_bot.on(events.NewMessage(pattern=r'^/check_address\s+(\S+)'))
        async def check_address(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            address = event.pattern_match.group(1)
            conn, cursor = db.get_connection()
            try:
                dex_data = await dex_api.fetch_dex_data("solana", address)
                if not dex_data["token_data"]:
                    await event.reply(f"❌ No data found for address `{address}`.", parse_mode="Markdown")
                    return
                token_data = dex_data["token_data"]
                is_paid = dex_data["is_paid"]
                paid_status = "✅" if is_paid else "❌"
                is_bonded = "Bonded" if dex_data["is_bonded"] else "Not Bonded"
                cursor.execute("""
                    SELECT MIN(initial_market_cap), MAX(ath_market_cap), MAX(ath_timestamp) 
                    FROM tracked_calls 
                    WHERE address = %s
                """, (address,))
                historical = cursor.fetchone()
                initial_mc = historical[0] if historical and historical[0] else 0.0
                ath_mc = historical[1] if historical and historical[1] else 0.0
                ath_timestamp = historical[2] if historical and historical[2] else None
                current_mc = float(token_data["market_cap"])
                multiplier = current_mc / initial_mc if initial_mc > 0 else 0.0
                response = (
                    f"📊 **Token Details for `{address}`**\n"
                    f"- **Name**: {token_data['base_token']['name']} (${token_data['base_token']['symbol']})\n"
                    f"- **Current MC**: {format_market_cap(current_mc)}\n"
                    f"- **Initial MC**: {format_market_cap(initial_mc)}\n"
                    f"- **ATH MC**: {format_market_cap(ath_mc)} (at {ath_timestamp.strftime('%Y-%m-%d %H:%M UTC') if ath_timestamp else 'N/A'})\n"
                    f"- **Multiplier**: {multiplier:.2f}x\n"
                    f"- **Price (USD)**: ${token_data['price_usd']} ({token_data['price_change']['h24']}% in 24h)\n"
                    f"- **Liquidity**: ${token_data['liquidity_usd']}\n"
                    f"- **FDV**: ${token_data['fdv']}\n"
                    f"- **Volume (24h)**: ${token_data['volume']['h24']}\n"
                    f"- **Status**: {is_bonded}\n"
                    f"- **DEX Paid**: {paid_status}\n"
                    f"- **Pair URL**: {token_data['url']}\n"
                )
                await event.reply(response, parse_mode="Markdown")
            except Exception as e:
                await event.reply(f"❌ Error checking address: {str(e)}", parse_mode="Markdown")
            finally:
                db.release_connection(conn, cursor)

        @management_bot.on(events.NewMessage(pattern=r'^/check_scan\s+(\S+)'))
        async def check_scan(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            address = event.pattern_match.group(1)
            client = management_bot
            conn, cursor = db.get_connection()
            try:
                cursor.execute("""
                    SELECT c.bot_name, c.chat_id, c.message_id, c.user_id, c.chat_name, c.detected_at 
                    FROM calls c 
                    WHERE c.address = %s 
                    ORDER BY c.detected_at ASC
                """, (address,))
                mentions = cursor.fetchall()
                total_mentions = len(mentions)
                if total_mentions == 0:
                    await event.reply(f"❌ No mentions found for address `{address}`.", parse_mode="Markdown")
                    return
                cursor.execute("""
                    SELECT MAX(ath_market_cap), MAX(ath_timestamp) 
                    FROM tracked_calls 
                    WHERE address = %s
                """, (address,))
                ath_data = cursor.fetchone()
                ath_mc = ath_data[0] if ath_data and ath_data[0] else 0.0
                ath_timestamp = ath_data[1] if ath_data and ath_data[1] else None
                cursor.execute("""
                    SELECT MIN(initial_market_cap), MIN(posted_at) 
                    FROM tracked_calls 
                    WHERE address = %s
                """, (address,))
                initial_data = cursor.fetchone()
                initial_mc = initial_data[0] if initial_data and initial_data[0] else 0.0
                first_detected = initial_data[1] if initial_data and initial_data[1] else None
                dex_data = await dex_api.fetch_dex_data("solana", address)
                token_data = dex_data["token_data"]
                if not token_data:
                    await event.reply(f"❌ No current data available for address `{address}`.", parse_mode="Markdown")
                    return
                current_mc = float(token_data["market_cap"])
                token_symbol = token_data["base_token"]["symbol"]
                token_name = token_data["base_token"]["name"]
                first_call = mentions[0] if mentions else None
                first_caller = None
                if first_call:
                    bot_name, chat_id, message_id, user_id, chat_name, detected_at = first_call
                    try:
                        user_entity = await client.get_entity(int(user_id)) if user_id else None
                        first_caller = f"@{user_entity.username}" if user_entity and getattr(user_entity, 'username', None) else user_id or "Unknown"
                    except Exception:
                        first_caller = user_id or "Unknown"
                multiplier = current_mc / initial_mc if initial_mc > 0 else 0.0
                response = (
                    f"📊 **Scan Results for `{address}`**\n"
                    f"- **Token**: {token_name} (${token_symbol})\n"
                    f"- **Total Mentions**: {total_mentions}\n"
                    f"- **Initial MC**: {format_market_cap(initial_mc)}\n"
                    f"- **ATH**: {format_market_cap(ath_mc)} (at {ath_timestamp.strftime('%Y-%m-%d %H:%M UTC') if ath_timestamp else 'N/A'})\n"
                    f"- **Current MC**: {format_market_cap(current_mc)}\n"
                    f"- **Multiplier from Initial**: {multiplier:.2f}x\n"
                    f"- **First Caller**: {first_caller or 'N/A'}\n"
                    f"- **First Bot**: {first_call[0] if first_call else 'N/A'}\n"
                    f"- **First Detected**: {first_detected.strftime('%Y-%m-%d %H:%M UTC') if first_detected else 'N/A'}\n"
                    f"\n**Mention History**:\n"
                )
                for bot_name, chat_id, message_id, user_id, chat_name, detected_at in mentions[:10]:
                    try:
                        chat = await client.get_entity(int(chat_id))
                        chat_username = getattr(chat, 'username', None)
                        link = get_telegram_link(chat_id, message_id, chat_username)
                        response += f"- [{chat_name}]({link}) at {detected_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                    except Exception:
                        response += f"- {chat_name} (ID: {chat_id}, Msg: {message_id}) at {detected_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                if total_mentions > 10:
                    response += f"...and {total_mentions - 10} more mentions.\n"
                await event.reply(response, parse_mode="Markdown")
            except Exception as e:
                await event.reply(f"❌ Error scanning address: {str(e)}", parse_mode="Markdown")
            finally:
                db.release_connection(conn, cursor)

        @management_bot.on(events.NewMessage(pattern=r'^/message_text\s+(\S+)\s+(-?\d+)\s+(allow|deny)'))
        async def set_message_text_permission(event):
            if not bot_manager.check_admin(str(event.sender_id)):
                await event.reply("❌ You are not authorized to use this command.")
                return
            bot_name, entity_id, action = event.pattern_match.groups()
            if bot_name not in bot_manager.clients:
                await event.reply(f"❌ Bot {bot_name} not found.")
                return
            allow = action.lower() == 'allow'
            db.set_message_text_permission(bot_name, int(entity_id), allow)
            status = "allowed" if allow else "denied"
            await event.reply(f"✅ Message text {status} for entity {entity_id} in {bot_name}.")

        for name, client in bot_manager.clients.items():
            asyncio.create_task(bot_manager.monitor_tracked_calls(client))
        asyncio.create_task(scheduler.run_cleanup(management_bot))
        logger.debug(f"Uptime monitor running: {uptime_monitor.is_running()}")
        if not uptime_monitor.is_running():
            uptime_monitor.task = asyncio.create_task(uptime_monitor.monitor_uptime(management_bot))
            logger.info("Started uptime monitor task")
        else:
            logger.warning("Uptime monitor task not started: already running")

        flask_thread = threading.Thread(target=run_flask, args=(config["PORT"],), daemon=True)
        flask_thread.start()

        await management_bot.run_until_disconnected()

    except Exception as e:
        logger.error(f"Critical error in management bot: {e}")
        await bot_manager.notify_admins(management_bot, f"🚨 Critical error in management bot: {str(e)}")
    finally:
        for client in bot_manager.clients.values():
            await client.disconnect()
        await uptime_monitor.close()
        db.close_pool()
        logger.info("Management bot shut down")

if __name__ == "__main__":
    asyncio.run(setup_management_bot())
