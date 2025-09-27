from telethon import TelegramClient, events, Button
import requests
import re
import datetime
import asyncio
import aiohttp
import logging
import json
import random
import pytz
import mysql.connector.pooling
from typing import Optional, List, Dict, Any, Tuple
import math

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)

# Bot configuration
BOT_TOKEN = "8161364231:AAHK4GJ-8RlqAMsHFxW-CmOOhsaMbDqFAvs"
BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Admin configuration
ADMIN_IDS = [6795467459, 1488443275]  # Add your Telegram user IDs here

# Main destination channel (default alerts)
MAIN_CHANNEL = -1002893520221  # Your main channel ID

# Userbot configuration
api_id = '22462146'
api_hash = '2d30926ba2410d83a5c3128ddab98695'

# Groups to monitor
groups = [
    -1001561952101, -1002650230697, -1002540908992, -1002238854475, -1002624329316,
    -1002210303599, -1001981328001, -1002592094839, -1002292287701,
    -1002170169768, -1002229355115, -1002387619261, -1002292629445,
    -1002226789719, -1002253749273, -1002877084412, -1002671964540,
]

# Moralis API keys
moralis_api_key = [
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6IjJjM2JkZjg1LTdiMjQtNDQzNC05NjZjLTQxNDA5YWEwNmEzZSIsIm9yZ0lkIjoiNDQ5Mzk0IiwidXNlcklkIjoiNDYyMzgwIiwidHlwZUlkIjoiOWI5NGE5ZjYtMWY4NC00NzE0LTk1OGUtYjdiNGJhNDM1YjdkIiwidHlwZSI6IlBST0pFQ1QiLCJpYXQiOjE3NDgzMTk2NTQsImV4cCI6NDkwNDA3OTY1NH0.SAjVtSxdOCDA7lhYRrF_mgVRg46uJSjfZ8IVbGdUqqM",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJub25jZSI6ImQ3Y2FmMDE3LWNkMDktNDNiNS04MGQ4LWY3OWRlM2ZkNDBlNCIsIm9yZ0lkIjoiNDQ3NzYxIiwidXNlcklkIjoiNDYwNjg5IiwidHlwZUlkIjoiM2U2YTA0NmMtMWQwNS00Mjg3LWE5MGItOTE0MmEzNDM2NTg0IiwidHlwZSI6IlBST0pFQ1QiLCJpYXQiOjE3NDc1NzcwOTYsImV4cCI6NDkwMzMzNzA5Nn0.0dOPGdxWoCXRpKNtDCzXbFMj-d1Z4t4RrOYLNxbjqCs"
]

# Smart scanner IDs
smart_scan = [
    8122443713, 6463378973, 7365691947, 5780347299, 6801141049, 7716240682, 8033298827, 1351580394, 5046008695, 6701991593,
    7388333086, 6206816924, 7119219480, 7850196647, 6675247317, 7506357555, 1630882115, 6825835223, 7473355343, 5867338844,
    1202742816, 1969412421, 7988887298, 6556379664, 1296422676, 7346333695, 6180993229, 1482926012, 7310754779, 1634970844,
    6964479059, 7323526511, 1000422479, 6581454764, 7738659269, 8113698023, 6896573120, 1591350650, 7121095053, 970857787,
    8016010821, 816134324, 6500733710, 8012818731, 7484467266, 5351131933, 7123551091, 5705024776, 1438760956, 1264062352,
    6868723153, 1104763594, 1120016737, 5006108864, 6285198013, 8180058794, 6439848200, 1663845440, 7679537630, 6034642934,
    6651974026, 6026565271, 5433153480, 6271862792, 1056059942, 6136630328, 5126233052, 1764958242, 7416536779, 7068658295,
    1778721342, 1357420392, 6237119816, 6577313828, 6464814586, 7725277031, 6150641725, 7493378809, 7824051459, 7156789053,
    7762308928, 5391913178, 7852472623, 7914730585, 5972159286, 7808944025
]

# Clients
user_client = TelegramClient('session_name', api_id, api_hash)
bot_client = TelegramClient('bot_session', api_id, api_hash).start(bot_token=BOT_TOKEN)

# Database configuration
db_config = {
    "host": "localhost",
    "user": "root",
    "password": "nezuka1337",
    "database": "lockin",
    "pool_name": "telegram_pool",
    "pool_size": 10
}

connection_pool = mysql.connector.pooling.MySQLConnectionPool(**db_config)

# Global variables
admin_states = {}
admin_pagination = {}
solana_address_regex = re.compile(r'[1-9A-HJ-NP-Za-km-z]{43,44}')

# ============= DATABASE FUNCTIONS =============

def get_db_conn():
    """Get database connection from pool."""
    return connection_pool.get_connection()

def initialize_database():
    """Initialize database tables."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        
        # CA tracker table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ca_tracker (
                ca VARCHAR(44) PRIMARY KEY,
                name VARCHAR(255),
                symbol VARCHAR(10),
                message_id BIGINT,
                fdv_initial FLOAT,
                ath_market_cap FLOAT,
                ath_timestamp DATETIME DEFAULT NULL,
                max_percentage_increase FLOAT,
                posted_at DATETIME,
                count INT DEFAULT 0,
                smart_count INT DEFAULT 0,
                history JSON,
                smart_users JSON,
                last_mentioned DATETIME,
                last_alerted FLOAT DEFAULT 1.0,
                active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # Filter channels table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS filter_channels (
                id INT AUTO_INCREMENT PRIMARY KEY,
                channel_id BIGINT UNIQUE NOT NULL,
                channel_name VARCHAR(255),
                min_calls INT DEFAULT 0,
                min_smart_calls INT DEFAULT 0,
                min_groups INT DEFAULT 0,
                time_window_minutes INT DEFAULT 0,
                min_fdv FLOAT DEFAULT 0,
                max_fdv FLOAT DEFAULT 0,
                gain_alerts_enabled BOOLEAN DEFAULT TRUE,
                gain_sensitivity FLOAT DEFAULT 0.32,
                active BOOLEAN DEFAULT TRUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                created_by BIGINT,
                stats JSON
            )
        """)
        
        # Channel messages tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS channel_messages (
                id INT AUTO_INCREMENT PRIMARY KEY,
                channel_id BIGINT NOT NULL,
                ca VARCHAR(44) NOT NULL,
                message_id BIGINT,
                posted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_channel_ca (channel_id, ca),
                FOREIGN KEY (channel_id) REFERENCES filter_channels(channel_id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
        logging.info("✅ Database initialized successfully")
    except Exception as e:
        logging.error(f"Database init error: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def ensure_timezone_aware(dt):
    """Ensure datetime is timezone aware (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return pytz.utc.localize(dt)
    return dt

def safe_json_loads(data):
    """Load JSON if string, else return as-is."""
    if isinstance(data, str):
        try:
            return json.loads(data)
        except Exception:
            return []
    elif isinstance(data, (list, dict)):
        return data
    return []

def get_ca_entry(ca):
    """Get CA entry from database."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ca_tracker WHERE ca = %s", (ca,))
        entry = cursor.fetchone()
        if entry:
            # Ensure timezone awareness for datetime fields
            entry['posted_at'] = ensure_timezone_aware(entry['posted_at'])
            entry['last_mentioned'] = ensure_timezone_aware(entry['last_mentioned'])
            entry['ath_timestamp'] = ensure_timezone_aware(entry['ath_timestamp'])
        return entry
    except Exception as e:
        logging.error(f"Get CA {ca} error: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def insert_ca_entry(ca, data):
    """Insert new CA entry."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ca_tracker (
                ca, name, symbol, message_id, fdv_initial, posted_at,
                count, smart_count, history, smart_users, last_mentioned,
                ath_market_cap, ath_timestamp, max_percentage_increase
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            ca,
            data['name'],
            data['symbol'],
            data['message_id'],
            data['fdv'],
            datetime.datetime.now(pytz.utc),
            data['count'],
            data['smart_count'],
            json.dumps(data['history']),
            json.dumps(list(data['smart_users'])),
            data['last_mentioned'],
            data['fdv'],
            datetime.datetime.now(pytz.utc),
            100.0
        ))
        conn.commit()
    except Exception as e:
        logging.error(f"Insert CA {ca} error: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def update_ca_entry(ca, updates):
    """Update CA entry."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        if 'smart_users' in updates:
            updates['smart_users'] = json.dumps(list(updates['smart_users']))
        if 'history' in updates:
            updates['history'] = json.dumps(updates['history'])
        set_clause = ", ".join(f"{key} = %s" for key in updates)
        values = list(updates.values()) + [ca]
        cursor.execute(f"UPDATE ca_tracker SET {set_clause} WHERE ca = %s", values)
        conn.commit()
    except Exception as e:
        logging.error(f"Update CA {ca} error: {str(e)}")
    finally:
        cursor.close()
        conn.close()

# ============= ADMIN FUNCTIONS =============

def is_admin(user_id: int) -> bool:
    """Check if user is an admin."""
    return user_id in ADMIN_IDS

def get_filter_channels(active_only: bool = False) -> List[Dict]:
    """Get all filter channels."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM filter_channels"
        if active_only:
            query += " WHERE active = TRUE"
        query += " ORDER BY created_at DESC"
        cursor.execute(query)
        channels = cursor.fetchall()
        # Ensure timezone awareness
        for channel in channels:
            channel['created_at'] = ensure_timezone_aware(channel['created_at'])
            channel['updated_at'] = ensure_timezone_aware(channel['updated_at'])
        return channels
    except Exception as e:
        logging.error(f"Error getting filter channels: {str(e)}")
        return []
    finally:
        cursor.close()
        conn.close()

def get_filter_channel(channel_id: int) -> Optional[Dict]:
    """Get a specific filter channel."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM filter_channels WHERE channel_id = %s", (channel_id,))
        channel = cursor.fetchone()
        if channel:
            channel['created_at'] = ensure_timezone_aware(channel['created_at'])
            channel['updated_at'] = ensure_timezone_aware(channel['updated_at'])
        return channel
    except Exception as e:
        logging.error(f"Error getting filter channel {channel_id}: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def create_filter_channel(channel_id: int, channel_name: str, created_by: int) -> bool:
    """Create a new filter channel."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO filter_channels (channel_id, channel_name, created_by)
            VALUES (%s, %s, %s)
        """, (channel_id, channel_name, created_by))
        conn.commit()
        logging.info(f"✅ Created filter channel: {channel_name} ({channel_id})")
        return True
    except Exception as e:
        logging.error(f"Error creating filter channel: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

def update_filter_channel(channel_id: int, updates: Dict) -> bool:
    """Update filter channel settings."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        set_clause = ", ".join(f"{key} = %s" for key in updates)
        values = list(updates.values()) + [channel_id]
        cursor.execute(f"UPDATE filter_channels SET {set_clause} WHERE channel_id = %s", values)
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error updating filter channel: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

def delete_filter_channel(channel_id: int) -> bool:
    """Delete a filter channel."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM filter_channels WHERE channel_id = %s", (channel_id,))
        conn.commit()
        return True
    except Exception as e:
        logging.error(f"Error deleting filter channel: {str(e)}")
        return False
    finally:
        cursor.close()
        conn.close()

def check_channel_filters(ca_entry: Dict, channel_config: Dict) -> bool:
    """Check if CA entry passes channel filters."""
    try:
        # Check min calls
        if channel_config['min_calls'] > 0 and ca_entry['count'] < channel_config['min_calls']:
            return False
        
        # Check min smart calls
        if channel_config['min_smart_calls'] > 0 and ca_entry['smart_count'] < channel_config['min_smart_calls']:
            return False
        
        # Check min groups
        if channel_config['min_groups'] > 0:
            history = safe_json_loads(ca_entry['history'])
            unique_groups = set(entry['group'] for entry in history)
            if len(unique_groups) < channel_config['min_groups']:
                return False
        
        # Check time window
        if channel_config['time_window_minutes'] > 0:
            posted_at = ensure_timezone_aware(ca_entry['posted_at'])
            now = datetime.datetime.now(pytz.utc)
            time_diff = now - posted_at
            if time_diff.total_seconds() / 60 > channel_config['time_window_minutes']:
                return False
        
        # Check FDV range
        fdv = ca_entry.get('fdv_initial', 0)
        if channel_config['min_fdv'] > 0 and fdv < channel_config['min_fdv']:
            return False
        if channel_config['max_fdv'] > 0 and fdv > channel_config['max_fdv']:
            return False
        
        return True
    except Exception as e:
        logging.error(f"Error checking channel filters: {str(e)}")
        return False

def get_channel_message_id(channel_id: int, ca: str) -> Optional[int]:
    """Get message ID for a CA in a specific channel."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT message_id FROM channel_messages 
            WHERE channel_id = %s AND ca = %s
        """, (channel_id, ca))
        result = cursor.fetchone()
        return result['message_id'] if result else None
    except Exception as e:
        logging.error(f"Error getting channel message ID: {str(e)}")
        return None
    finally:
        cursor.close()
        conn.close()

def save_channel_message(channel_id: int, ca: str, message_id: int):
    """Save message ID for a CA in a specific channel."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO channel_messages (channel_id, ca, message_id)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE message_id = VALUES(message_id)
        """, (channel_id, ca, message_id))
        
        # Update channel stats
        cursor.execute("""
            UPDATE filter_channels 
            SET stats = JSON_SET(
                COALESCE(stats, '{}'),
                '$.total_alerts', COALESCE(JSON_EXTRACT(stats, '$.total_alerts'), 0) + 1,
                '$.last_alert', NOW()
            )
            WHERE channel_id = %s
        """, (channel_id,))
        
        conn.commit()
    except Exception as e:
        logging.error(f"Error saving channel message: {str(e)}")
    finally:
        cursor.close()
        conn.close()

def get_channel_stats(channel_id: int) -> Dict:
    """Get statistics for a filter channel."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        # Get channel info
        cursor.execute("SELECT stats FROM filter_channels WHERE channel_id = %s", (channel_id,))
        result = cursor.fetchone()
        if result:
            stats = json.loads(result['stats']) if result['stats'] else {}
            
            # Get recent alerts count
            cursor.execute("""
                SELECT COUNT(*) as total_alerts,
                       MAX(posted_at) as last_alert
                FROM channel_messages
                WHERE channel_id = %s
                  AND posted_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            """, (channel_id,))
            recent = cursor.fetchone()
            
            stats['alerts_24h'] = recent['total_alerts'] if recent else 0
            stats['last_alert'] = recent['last_alert'].isoformat() if recent and recent['last_alert'] else None
            
            return stats
        return {}
    except Exception as e:
        logging.error(f"Error getting channel stats: {str(e)}")
        return {}
    finally:
        cursor.close()
        conn.close()

def get_ca_entries_paginated(page: int = 1, per_page: int = 5) -> Tuple[List[Dict], int]:
    """Get paginated CA entries from database."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get total count
        cursor.execute("SELECT COUNT(*) as total FROM ca_tracker")
        total = cursor.fetchone()['total']
        total_pages = math.ceil(total / per_page)
        
        # Get paginated results
        offset = (page - 1) * per_page
        cursor.execute("""
            SELECT ca, name, symbol, fdv_initial, count, smart_count, 
                   max_percentage_increase, posted_at, last_mentioned, active
            FROM ca_tracker
            ORDER BY last_mentioned DESC
            LIMIT %s OFFSET %s
        """, (per_page, offset))
        
        entries = cursor.fetchall()
        # Ensure timezone awareness
        for entry in entries:
            entry['posted_at'] = ensure_timezone_aware(entry['posted_at'])
            entry['last_mentioned'] = ensure_timezone_aware(entry['last_mentioned'])
        
        return entries, total_pages
    except Exception as e:
        logging.error(f"Error getting paginated CA entries: {str(e)}")
        return [], 0
    finally:
        cursor.close()
        conn.close()

# ============= UTILITY FUNCTIONS =============

def format_market_cap(value: float) -> str:
    """Format market cap value."""
    if value is None:
        return "N/A"
    try:
        if value >= 1_000_000_000:
            return f"{value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"{value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"{value / 1_000:.2f}K"
        return f"{value:,.2f}"
    except Exception as e:
        logging.error(f"Error formatting market cap {value}: {e}")
        return "Invalid"

def format_time_diff(start: datetime.datetime, end: datetime.datetime) -> str:
    """Format time difference between two datetimes."""
    start = ensure_timezone_aware(start)
    end = ensure_timezone_aware(end)
    
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

def format_time_ago(timestamp_str: str, current_time: datetime.datetime) -> str:
    """Format timestamp as 'time ago' relative to current time."""
    try:
        time_parts = timestamp_str.split(':')
        hours = int(time_parts[0])
        minutes = int(time_parts[1])
        seconds = int(time_parts[2])
        
        today = current_time.date()
        timestamp_dt = datetime.datetime.combine(today, datetime.time(hours, minutes, seconds))
        timestamp_dt = timestamp_dt.replace(tzinfo=pytz.utc)
        
        if timestamp_dt > current_time:
            timestamp_dt = timestamp_dt - datetime.timedelta(days=1)
        
        diff = current_time - timestamp_dt
        total_seconds = int(diff.total_seconds())
        
        if total_seconds < 60:
            return f"{total_seconds}s ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}min ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            if minutes == 0:
                return f"{hours}h ago"
            else:
                return f"{hours}h:{minutes:02d}min ago"
        else:
            days = diff.days
            hours = (total_seconds % 86400) // 3600
            if hours == 0:
                return f"{days}d ago"
            else:
                return f"{days}d {hours}h ago"
                
    except Exception as e:
        logging.error(f"Error formatting time ago for {timestamp_str}: {e}")
        return timestamp_str

def create_expandable_history_block(history_lines):
    """Create an expandable blockquote for the history section."""
    if not history_lines:
        return ""
    
    history_text = "\n".join(history_lines)
    return f"<blockquote expandable>{history_text}</blockquote>"

# ============= API FUNCTIONS =============

async def fetch_token_metadata(ca):
    """Fetch token metadata from Moralis or Dexscreener."""
    url = f"https://solana-gateway.moralis.io/token/mainnet/{ca}/metadata"
    dex_url = f"https://api.dexscreener.com/token-pairs/v1/solana/{ca}"
    headers = {"X-API-Key": random.choice(moralis_api_key)}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status == 200:
                    response_json = await response.text()
                    data = json.loads(response_json)
                    return {
                        'name': data['name'],
                        'symbol': data['symbol'],
                        'fdv': float(data['fullyDilutedValue'])
                    }
                elif response.status == 404:
                    async with session.get(dex_url) as dex_response:
                        if dex_response.status == 200:
                            dex_data = await dex_response.json()
                            if isinstance(dex_data, list) and len(dex_data) > 0:
                                pair = dex_data[0]
                                return {
                                    "name": pair["baseToken"]["name"],
                                    "symbol": pair["baseToken"]["symbol"],
                                    "fdv": float(pair.get("fdv", 0))
                                }
                            else:
                                logging.error(f"Dexscreener API returned no pairs for {ca}")
                                return {'name': 'Unknown', 'symbol': 'UNKNOWN', 'fdv': 0}
                        else:
                            logging.error(f"Dexscreener API error for {ca}")
                            return {'name': 'Unknown', 'symbol': 'UNKNOWN', 'fdv': 0}
                else:
                    logging.error(f"Moralis API error for {ca}: Status {response.status}")
                    return {'name': 'Unknown', 'symbol': 'UNKNOWN', 'fdv': 0}
    except Exception as e:
        logging.error(f"Metadata fetch error for {ca}: {str(e)}")
        return {'name': 'Unknown', 'symbol': 'UNKNOWN', 'fdv': 0}

async def send_to_channel_via_bot(message, reply_to=None, channel_id=None):
    """Send message to channel using Bot API."""
    target_channel = channel_id if channel_id else MAIN_CHANNEL
    
    # Normalize chat ID
    def normalize_chat_id(chat):
        if isinstance(chat, int):
            s = str(chat)
            if not s.startswith("-100"):
                return int("-100" + s.lstrip("-"))
            return chat
        elif isinstance(chat, str):
            if chat.startswith("@"):
                return chat
            if chat.isdigit() or (chat.startswith("-") and chat[1:].isdigit()):
                return int("-100" + chat.lstrip("-"))
            return chat
        return chat
    
    chat_id = normalize_chat_id(target_channel)
    
    # Truncate if too long
    if len(message) > 3900:
        message = message[:3900] + "\n\n[...truncated]"
    
    data = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    if reply_to:
        data['reply_to_message_id'] = reply_to
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{BOT_API_URL}/sendMessage", json=data) as response:
                resp_text = await response.text()
                if response.status == 200:
                    result = await response.json()
                    if result.get('ok'):
                        return result['result']['message_id']
                    else:
                        logging.error(f"Bot API error: {result}")
                        return None
                else:
                    logging.error(f"HTTP error {response.status} when sending to {chat_id}: {resp_text}")
                    return None
    except Exception as e:
        logging.error(f"⚠️ Error sending message via bot to {chat_id}: {str(e)}")
        return None

async def send_to_filter_channels(ca_entry, metadata, current_user, current_group, is_new):
    """Send alerts to all matching filter channels."""
    channels = get_filter_channels(active_only=True)
    
    if not channels:
        logging.info("No active filter channels configured")
        return
    
    for channel in channels:
        try:
            # Check if CA passes channel filters
            if not check_channel_filters(ca_entry, channel):
                logging.debug(f"CA {ca_entry['ca']} did not pass filters for channel {channel['channel_id']}")
                continue
            
            # Check if this is a new alert for this channel
            existing_msg_id = get_channel_message_id(channel['channel_id'], ca_entry['ca'])
            if not is_new and existing_msg_id:
                reply_to = existing_msg_id
            else:
                reply_to = None
            
            # Prepare message
            now = datetime.datetime.now(pytz.utc)
            header = f"🚨 <b>${metadata['symbol']}</b> NEW!" if is_new else f"🔔 <b>${metadata['symbol']}</b> MENTIONED!"
            
            history = safe_json_loads(ca_entry['history'])
            
            first_caller = history[0]['user'] if history else current_user
            first_caller_line = (
                f"{format_time_ago(history[0]['timestamp'], now)} - {first_caller} "
                f"@{format_market_cap(history[0]['fdv_call'])} in {history[0]['group']} [FC]"
                if history else ""
            )
            
            recent_entries = history[1:] if len(history) > 1 else []
            recent_entries = recent_entries[-10:]
            
            history_lines = []
            if first_caller_line:
                history_lines.append(first_caller_line)
            
            history_lines.extend([
                f"{format_time_ago(entry['timestamp'], now)} - {entry['user']} "
                f"@{format_market_cap(entry['fdv_call'])} in {entry['group']}"
                for entry in recent_entries
            ])
            
            expandable_history = create_expandable_history_block(history_lines)
            
            if not is_new and ca_entry.get('max_percentage_increase', 100) > 100:
                multiplier = ca_entry['max_percentage_increase'] / 100
                recent_history_header = f"🌕 <b>Recent History</b> (<i>{multiplier:.1f}x from call</i>)"
            else:
                recent_history_header = "🌕 <b>Recent History</b>"
            
            message = f"""
{header}
{metadata['name']}
<code>{ca_entry['ca']}</code>

┌ <code>FDV:</code>           <b>{format_market_cap(metadata.get('fdv', 0))}</b>  
├ <code>Caller:</code>    <b>{current_user}</b>  
├ <code>Group:</code>      <b>{current_group}</b>  
├ <code>Scans:</code>      <b>{ca_entry['count']}</b>
└ <code>Smart:</code>      <b>{ca_entry['smart_count']}</b>

{recent_history_header}
{expandable_history}
            """.strip()
            
            # Send to filter channel
            sent_message_id = await send_to_channel_via_bot(message, reply_to=reply_to, channel_id=channel['channel_id'])
            
            if sent_message_id:
                save_channel_message(channel['channel_id'], ca_entry['ca'], sent_message_id)
                logging.info(f"✅ Sent alert to filter channel {channel['channel_name']} ({channel['channel_id']})")
                
        except Exception as e:
            logging.error(f"Error sending to filter channel {channel['channel_id']}: {str(e)}")

# ============= BOT COMMAND HANDLERS =============

@bot_client.on(events.NewMessage(pattern='/start'))
async def start_handle(event):
    """Welcome message and bot information."""
    is_admin_user = is_admin(event.sender_id)
    admin_status = "✅ Admin Access Enabled" if is_admin_user else "❌ Regular User"
    
    message = f"""
🚀 <b>Multi-Channel Crypto Alert Bot</b>

Welcome! This bot tracks cryptocurrency mentions across multiple Telegram groups and sends filtered alerts.

<b>Your Status:</b> {admin_status}
<b>Your ID:</b> <code>{event.sender_id}</code>

<b>Available Commands:</b>
• /start - Show this message
• /myid - Get your Telegram ID
{"/admin - Open admin panel" if is_admin_user else "• /admin - Admin panel (restricted)"}

<i>Bot is actively monitoring {len(groups)} groups.</i>
    """
    
    await event.reply(message, parse_mode='html')

@bot_client.on(events.NewMessage(pattern='/myid'))
async def show_user_id(event):
    """Show user their Telegram ID."""
    user_id = event.sender_id
    username = event.sender.username if event.sender.username else "Not set"
    first_name = event.sender.first_name if event.sender.first_name else "Unknown"
    
    message = f"""
🆔 <b>Your Telegram Information</b>

<b>User ID:</b> <code>{user_id}</code>
<b>Username:</b> @{username}
<b>Name:</b> {first_name}

<i>Add your User ID to the ADMIN_IDS list in the bot configuration to access admin features.</i>
    """
    
    await event.reply(message, parse_mode='html')

@bot_client.on(events.NewMessage(pattern='/admin'))
async def admin_panel(event):
    """Main admin panel."""
    if not is_admin(event.sender_id):
        await event.reply("⛔ You are not authorized to use this command.")
        return
    
    buttons = [
        [Button.inline("📊 View Channels", "view_channels"),
         Button.inline("➕ Create Channel", "create_channel")],
        [Button.inline("📈 Database Browser", "browse_db"),
         Button.inline("📉 Statistics", "global_stats")],
        [Button.inline("ℹ️ Help", "admin_help"),
         Button.inline("❌ Close", "close_panel")]
    ]
    
    message = """
🔧 <b>Admin Control Panel</b>

Welcome to the Multi-Channel Alert Filter System!
Use the buttons below to manage filter channels and view statistics.

<i>Current Active Channels: {}</i>
    """.format(len(get_filter_channels(active_only=True)))
    
    await event.reply(message, buttons=buttons, parse_mode='html')

@bot_client.on(events.NewMessage(pattern='/createchannel'))
async def create_channel_command(event):
    """Create a new filter channel via command."""
    if not is_admin(event.sender_id):
        await event.reply("⛔ You are not authorized to use this command.")
        return
    
    args = event.text.split()
    if len(args) < 2:
        await event.reply(
            "❌ Usage: /createchannel <channel_id> [channel_name]\n"
            "Example: /createchannel -1001234567890 MyFilterChannel"
        )
        return
    
    try:
        channel_id = int(args[1])
        channel_name = ' '.join(args[2:]) if len(args) > 2 else f"Channel_{channel_id}"
        
        if create_filter_channel(channel_id, channel_name, event.sender_id):
            await event.reply(f"✅ Channel created successfully!\nID: {channel_id}\nName: {channel_name}")
        else:
            await event.reply("❌ Failed to create channel. It may already exist.")
    except ValueError:
        await event.reply("❌ Invalid channel ID. Must be a number.")
    except Exception as e:
        await event.reply(f"❌ Error: {str(e)}")

@bot_client.on(events.NewMessage(pattern='/setfilters'))
async def set_filters_command(event):
    """Set all filters for a channel in one command."""
    if not is_admin(event.sender_id):
        await event.reply("⛔ You are not authorized to use this command.")
        return
    
    args = event.text.split()
    if len(args) < 8:
        await event.reply(
            "❌ Usage: /setfilters <channel_id> <min_calls> <min_smart> <min_groups> "
            "<time_window_min> <min_fdv> <max_fdv>\n\n"
            "Use 0 to disable any filter.\n"
            "Example: /setfilters -1001234567890 5 2 3 60 10000 1000000"
        )
        return
    
    try:
        channel_id = int(args[1])
        updates = {
            'min_calls': int(args[2]),
            'min_smart_calls': int(args[3]),
            'min_groups': int(args[4]),
            'time_window_minutes': int(args[5]),
            'min_fdv': float(args[6]),
            'max_fdv': float(args[7])
        }
        
        if update_filter_channel(channel_id, updates):
            await event.reply(
                f"✅ Filters updated for channel {channel_id}:\n"
                f"• Min Calls: {updates['min_calls']}\n"
                f"• Min Smart: {updates['min_smart_calls']}\n"
                f"• Min Groups: {updates['min_groups']}\n"
                f"• Time Window: {updates['time_window_minutes']} min\n"
                f"• FDV Range: ${updates['min_fdv']:,.0f} - ${updates['max_fdv']:,.0f}"
            )
        else:
            await event.reply("❌ Failed to update filters. Channel may not exist.")
    except (ValueError, IndexError) as e:
        await event.reply(f"❌ Invalid parameters: {str(e)}")

# ============= BUTTON CALLBACKS =============

@bot_client.on(events.CallbackQuery)
async def callback_handler(event):
    """Handle all button callbacks."""
    if not is_admin(event.sender_id):
        await event.answer("⛔ Unauthorized", alert=True)
        return
    
    data = event.data.decode('utf-8')
    
    # Main panel navigation
    if data == "view_channels":
        await show_channels_list(event)
    elif data == "create_channel":
        await show_create_channel(event)
    elif data == "browse_db":
        await show_database_browser(event, page=1)
    elif data == "global_stats":
        await show_global_stats(event)
    elif data == "admin_help":
        await show_admin_help(event)
    elif data == "close_panel":
        await event.delete()
    elif data == "back_to_main":
        await show_main_panel(event)
    
    # Channel management
    elif data.startswith("channel_"):
        await handle_channel_action(event, data)
    
    # Database browser pagination
    elif data.startswith("db_page_"):
        page = int(data.split("_")[2])
        await show_database_browser(event, page)
    
    # Filter editing
    elif data.startswith("edit_"):
        await handle_edit_action(event, data)

async def show_main_panel(event):
    """Show main admin panel."""
    buttons = [
        [Button.inline("📊 View Channels", "view_channels"),
         Button.inline("➕ Create Channel", "create_channel")],
        [Button.inline("📈 Database Browser", "browse_db"),
         Button.inline("📉 Statistics", "global_stats")],
        [Button.inline("ℹ️ Help", "admin_help"),
         Button.inline("❌ Close", "close_panel")]
    ]
    
    message = """
🔧 <b>Admin Control Panel</b>

Welcome to the Multi-Channel Alert Filter System!
Use the buttons below to manage filter channels and view statistics.

<i>Current Active Channels: {}</i>
    """.format(len(get_filter_channels(active_only=True)))
    
    await event.edit(message, buttons=buttons, parse_mode='html')

async def show_channels_list(event):
    """Show list of all filter channels."""
    channels = get_filter_channels()
    
    if not channels:
        buttons = [
            [Button.inline("➕ Create Channel", "create_channel")],
            [Button.inline("🔙 Back", "back_to_main")]
        ]
        await event.edit("📊 No filter channels configured yet.", buttons=buttons)
        return
    
    buttons = []
    for channel in channels[:10]:  # Show max 10 channels
        status = "✅" if channel['active'] else "❌"
        btn_text = f"{status} {channel['channel_name']} ({channel['channel_id']})"
        btn_data = f"channel_view_{channel['channel_id']}"
        buttons.append([Button.inline(btn_text, btn_data)])
    
    buttons.append([Button.inline("🔙 Back", "back_to_main")])
    
    message = f"📊 <b>Filter Channels ({len(channels)} total)</b>\n\nSelect a channel to manage:"
    await event.edit(message, buttons=buttons, parse_mode='html')

async def show_create_channel(event):
    """Show create channel instructions."""
    message = """
➕ <b>Create New Filter Channel</b>

To create a new filter channel, use the command:
<code>/createchannel [channel_id] [name]</code>

Example:
<code>/createchannel -1001234567890 MyAlerts</code>

After creation, use:
<code>/setfilters [channel_id] [min_calls] [min_smart] [min_groups] [time_window] [min_fdv] [max_fdv]</code>

Example:
<code>/setfilters -1001234567890 5 2 3 60 10000 1000000</code>

<i>Use 0 for any filter to disable it.</i>
    """
    
    buttons = [[Button.inline("🔙 Back", "back_to_main")]]
    await event.edit(message, buttons=buttons, parse_mode='html')

async def handle_channel_action(event, data):
    """Handle channel-specific actions."""
    parts = data.split("_")
    action = parts[1]
    channel_id = int(parts[2])
    
    if action == "view":
        await show_channel_details(event, channel_id)
    elif action == "toggle":
        channel = get_filter_channel(channel_id)
        if channel:
            new_status = not channel['active']
            update_filter_channel(channel_id, {'active': new_status})
            await show_channel_details(event, channel_id)
    elif action == "gains":
        channel = get_filter_channel(channel_id)
        if channel:
            new_status = not channel['gain_alerts_enabled']
            update_filter_channel(channel_id, {'gain_alerts_enabled': new_status})
            await show_channel_details(event, channel_id)
    elif action == "delete":
        delete_filter_channel(channel_id)
        await show_channels_list(event)
    elif action == "test":
        await test_channel_filters(event, channel_id)
    elif action == "stats":
        await show_channel_stats(event, channel_id)

async def show_channel_details(event, channel_id):
    """Show detailed view of a channel."""
    channel = get_filter_channel(channel_id)
    if not channel:
        await event.edit("❌ Channel not found.", buttons=[[Button.inline("🔙 Back", "view_channels")]])
        return
    
    status = "✅ Active" if channel['active'] else "❌ Inactive"
    gains = "✅ Enabled" if channel['gain_alerts_enabled'] else "❌ Disabled"
    
    message = f"""
📊 <b>Channel Details</b>

<b>Name:</b> {channel['channel_name']}
<b>ID:</b> <code>{channel['channel_id']}</code>
<b>Status:</b> {status}
<b>Gain Alerts:</b> {gains}

<b>📋 Filter Settings:</b>
• Min Calls: {channel['min_calls']} (0=disabled)
• Min Smart Calls: {channel['min_smart_calls']}
• Min Groups: {channel['min_groups']}
• Time Window: {channel['time_window_minutes']} min
• Min FDV: ${channel['min_fdv']:,.0f}
• Max FDV: ${channel['max_fdv']:,.0f}
• Gain Sensitivity: {channel['gain_sensitivity']*100:.0f}%

<b>📈 Stats:</b>
• Created: {channel['created_at'].strftime('%Y-%m-%d %H:%M')}
• Updated: {channel['updated_at'].strftime('%Y-%m-%d %H:%M')}
    """
    
    toggle_text = "🔴 Deactivate" if channel['active'] else "🟢 Activate"
    gains_text = "🔕 Disable Gains" if channel['gain_alerts_enabled'] else "🔔 Enable Gains"
    
    buttons = [
        [Button.inline(toggle_text, f"channel_toggle_{channel_id}"),
         Button.inline(gains_text, f"channel_gains_{channel_id}")],
        [Button.inline("✏️ Edit Filters", f"edit_start_{channel_id}"),
         Button.inline("📊 View Stats", f"channel_stats_{channel_id}")],
        [Button.inline("🧪 Test Filters", f"channel_test_{channel_id}"),
         Button.inline("🗑 Delete", f"channel_delete_{channel_id}")],
        [Button.inline("🔙 Back", "view_channels")]
    ]
    
    await event.edit(message, buttons=buttons, parse_mode='html')

async def show_channel_stats(event, channel_id):
    """Show channel statistics."""
    channel = get_filter_channel(channel_id)
    stats = get_channel_stats(channel_id)
    
    message = f"""
📊 <b>Channel Statistics</b>
<b>{channel['channel_name']}</b>

• Total Alerts: {stats.get('total_alerts', 0)}
• Alerts (24h): {stats.get('alerts_24h', 0)}
• Last Alert: {stats.get('last_alert', 'Never')}
    """
    
    buttons = [[Button.inline("🔙 Back", f"channel_view_{channel_id}")]]
    await event.edit(message, buttons=buttons, parse_mode='html')

async def test_channel_filters(event, channel_id):
    """Test channel filters with current CA entries."""
    channel = get_filter_channel(channel_id)
    if not channel:
        await event.answer("Channel not found", alert=True)
        return
    
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM ca_tracker WHERE active = TRUE ORDER BY last_mentioned DESC LIMIT 10")
        entries = cursor.fetchall()
        
        matching = []
        for entry in entries:
            # Ensure timezone awareness
            entry['posted_at'] = ensure_timezone_aware(entry['posted_at'])
            entry['last_mentioned'] = ensure_timezone_aware(entry['last_mentioned'])
            entry['ath_timestamp'] = ensure_timezone_aware(entry['ath_timestamp'])
            
            if check_channel_filters(entry, channel):
                matching.append(f"• {entry['symbol']} - {entry['count']} calls")
        
        if matching:
            message = f"✅ {len(matching)} CAs would pass filters:\n" + "\n".join(matching[:5])
        else:
            message = "❌ No current CAs pass the filters"
        
        await event.answer(message, alert=True)
    finally:
        cursor.close()
        conn.close()

async def show_database_browser(event, page=1):
    """Show paginated database browser."""
    entries, total_pages = get_ca_entries_paginated(page=page, per_page=5)
    
    if not entries:
        await event.edit("📈 No entries in database.", 
                        buttons=[[Button.inline("🔙 Back", "back_to_main")]])
        return
    
    message = f"📈 <b>Database Browser (Page {page}/{total_pages})</b>\n\n"
    
    for entry in entries:
        status = "✅" if entry['active'] else "❌"
        multiplier = entry['max_percentage_increase'] / 100 if entry['max_percentage_increase'] else 1
        
        message += f"""
{status} <b>{entry['symbol']}</b> ({entry['name'][:20]})
• CA: <code>{entry['ca'][:10]}...</code>
• Calls: {entry['count']} (Smart: {entry['smart_count']})
• FDV: ${format_market_cap(entry['fdv_initial'])}
• Max: {multiplier:.1f}x
• Last: {entry['last_mentioned'].strftime('%H:%M:%S') if entry['last_mentioned'] else 'N/A'}
─────────────────
"""
    
    # Pagination buttons
    buttons = []
    nav_buttons = []
    
    if page > 1:
        nav_buttons.append(Button.inline("◀️ Prev", f"db_page_{page-1}"))
    
    nav_buttons.append(Button.inline(f"{page}/{total_pages}", "noop"))
    
    if page < total_pages:
        nav_buttons.append(Button.inline("Next ▶️", f"db_page_{page+1}"))
    
    buttons.append(nav_buttons)
    buttons.append([Button.inline("🔙 Back", "back_to_main")])
    
    await event.edit(message, buttons=buttons, parse_mode='html')

async def show_global_stats(event):
    """Show global statistics."""
    conn = get_db_conn()
    try:
        cursor = conn.cursor(dictionary=True)
        
        # Get overall stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_cas,
                COUNT(CASE WHEN active = TRUE THEN 1 END) as active_cas,
                AVG(count) as avg_calls,
                AVG(smart_count) as avg_smart_calls,
                MAX(max_percentage_increase) as max_gain
            FROM ca_tracker
        """)
        stats = cursor.fetchone()
        
        # Get filter channel stats
        cursor.execute("""
            SELECT 
                COUNT(*) as total_channels,
                COUNT(CASE WHEN active = TRUE THEN 1 END) as active_channels
            FROM filter_channels
        """)
        channel_stats = cursor.fetchone()
        
        message = f"""
📉 <b>Global Statistics</b>

<b>📊 CA Tracker:</b>
• Total CAs: {stats['total_cas']}
• Active CAs: {stats['active_cas']}
• Avg Calls: {stats['avg_calls']:.1f}
• Avg Smart Calls: {stats['avg_smart_calls']:.1f}
• Max Gain: {stats['max_gain']/100:.1f}x

<b>🔧 Filter Channels:</b>
• Total Channels: {channel_stats['total_channels']}
• Active Channels: {channel_stats['active_channels']}
        """
        
        buttons = [[Button.inline("🔙 Back", "back_to_main")]]
        await event.edit(message, buttons=buttons, parse_mode='html')
        
    finally:
        cursor.close()
        conn.close()

async def show_admin_help(event):
    """Show admin help information."""
    message = """
ℹ️ <b>Admin Help</b>

<b>Commands:</b>
• /admin - Open admin panel
• /createchannel [id] [name] - Create filter channel
• /setfilters [id] [...] - Configure filters

<b>Filter Parameters:</b>
• min_calls - Minimum total calls
• min_smart - Minimum smart caller calls
• min_groups - Minimum unique groups
• time_window - Max minutes since first call
• min_fdv/max_fdv - FDV range

<b>Tips:</b>
• Use 0 to disable any filter
• Test filters before activating
• Monitor channel stats regularly
• Gain alerts can be toggled per channel

<b>Support:</b>
Contact bot developer for assistance.
    """
    
    buttons = [[Button.inline("🔙 Back", "back_to_main")]]
    await event.edit(message, buttons=buttons, parse_mode='html')

async def handle_edit_action(event, data):
    """Handle filter editing."""
    parts = data.split("_")
    
    if parts[1] == "start":
        channel_id = int(parts[2])
        admin_states[event.sender_id] = {'editing': channel_id, 'step': 'menu'}
        
        message = """
✏️ <b>Edit Filters</b>

Send new values in format:
<code>[min_calls] [min_smart] [min_groups] [time_window] [min_fdv] [max_fdv]</code>

Example:
<code>5 2 3 60 10000 1000000</code>

Or use buttons below for quick presets:
        """
        
        buttons = [
            [Button.inline("🔰 Low Filter", f"edit_preset_{channel_id}_low"),
             Button.inline("⚡ Medium Filter", f"edit_preset_{channel_id}_med")],
            [Button.inline("💎 High Filter", f"edit_preset_{channel_id}_high"),
             Button.inline("🚀 Ultra Filter", f"edit_preset_{channel_id}_ultra")],
            [Button.inline("❌ Cancel", f"channel_view_{channel_id}")]
        ]
        
        await event.edit(message, buttons=buttons, parse_mode='html')
    
    elif parts[1] == "preset":
        channel_id = int(parts[2])
        preset = parts[3]
        
        presets = {
            'low': {'min_calls': 2, 'min_smart_calls': 0, 'min_groups': 1, 
                   'time_window_minutes': 120, 'min_fdv': 5000, 'max_fdv': 0},
            'med': {'min_calls': 5, 'min_smart_calls': 1, 'min_groups': 2, 
                   'time_window_minutes': 60, 'min_fdv': 10000, 'max_fdv': 1000000},
            'high': {'min_calls': 10, 'min_smart_calls': 3, 'min_groups': 3, 
                    'time_window_minutes': 30, 'min_fdv': 50000, 'max_fdv': 500000},
            'ultra': {'min_calls': 20, 'min_smart_calls': 5, 'min_groups': 5, 
                     'time_window_minutes': 15, 'min_fdv': 100000, 'max_fdv': 250000}
        }
        
        if preset in presets:
            update_filter_channel(channel_id, presets[preset])
            await event.answer(f"✅ Applied {preset.upper()} preset", alert=True)
            await show_channel_details(event, channel_id)

# ============= BACKGROUND TASKS =============

async def cleanup_old_entries():
    """Clean up old inactive entries."""
    while True:
        try:
            now = datetime.datetime.now(pytz.utc)
            conn = get_db_conn()
            try:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE ca_tracker 
                    SET active = FALSE 
                    WHERE last_mentioned < %s
                """, (now - datetime.timedelta(seconds=21600),))
                conn.commit()
                affected = cursor.rowcount
                if affected > 0:
                    logging.info(f"Cleaned up {affected} old entries")
            finally:
                cursor.close()
                conn.close()
            await asyncio.sleep(3600)
        except Exception as e:
            logging.error(f"Cleanup error: {str(e)}")
            await asyncio.sleep(60)

@user_client.on(events.NewMessage(chats=groups))
async def handle_message(event):
    """Handle new messages from monitored groups."""
    try:
        msg = event.message
        addresses = solana_address_regex.findall(msg.text)
        
        if not addresses or not msg.sender or msg.sender.bot:
            return

        for ca in addresses:
            metadata = await fetch_token_metadata(ca)
            ca_entry = get_ca_entry(ca)
            
            now = datetime.datetime.now(pytz.utc)
            timestamp = now.strftime("%H:%M:%S")
            current_user = msg.sender.first_name
            current_group = event.chat.title
            current_senderid = msg.sender.id
            
            if ca_entry is None:
                # New CA entry
                ca_entry = {
                    'ca': ca,
                    'name': metadata['name'],
                    'symbol': metadata['symbol'],
                    'fdv': metadata['fdv'],
                    'count': 1,
                    'smart_count': 1 if current_senderid in smart_scan else 0,
                    'smart_users': {current_senderid} if current_senderid in smart_scan else set(),
                    'history': [{
                        'user': current_user,
                        'group': current_group,
                        'timestamp': timestamp,
                        'fdv_call': float(metadata.get('fdv', 0))
                    }],
                    'last_mentioned': now,
                    'message_id': None
                }
                is_new = True
            else:
                # Update existing entry
                is_new = False
                ca_entry['count'] += 1
                
                history = safe_json_loads(ca_entry['history'])
                history = history.copy()
                
                smart_users = set(safe_json_loads(ca_entry['smart_users'])) if ca_entry['smart_users'] else set()
                smart_users = smart_users.copy()
                
                if current_senderid in smart_scan and current_senderid not in smart_users:
                    ca_entry['smart_count'] += 1
                    smart_users.add(current_senderid)
                
                duplicate_exists = any(
                    entry['user'] == current_user and 
                    entry['group'] == current_group
                    for entry in history
                )
                
                if not duplicate_exists:
                    history.append({
                        'user': current_user,
                        'group': current_group,
                        'timestamp': timestamp,
                        'fdv_call': float(metadata.get('fdv', 0))
                    })
                
                ca_entry['history'] = history
                ca_entry['smart_users'] = smart_users
                ca_entry['last_mentioned'] = now
            
            # Prepare message
            header = f"🚨 <b>${metadata['symbol']}</b> NEW!" if is_new else f"🔔 <b>${metadata['symbol']}</b> MENTIONED!"
            
            history = safe_json_loads(ca_entry['history'])
            
            first_caller = history[0]['user'] if history else current_user
            first_caller_line = (
                f"{format_time_ago(history[0]['timestamp'], now)} - {first_caller} "
                f"@{format_market_cap(history[0]['fdv_call'])} in {history[0]['group']} [FC]"
                if history else ""
            )
            
            recent_entries = history[1:] if len(history) > 1 else []
            recent_entries = recent_entries[-10:]
            
            history_lines = []
            if first_caller_line:
                history_lines.append(first_caller_line)
            
            history_lines.extend([
                f"{format_time_ago(entry['timestamp'], now)} - {entry['user']} "
                f"@{format_market_cap(entry['fdv_call'])} in {entry['group']}"
                for entry in recent_entries
            ])
            
            expandable_history = create_expandable_history_block(history_lines)
            
            if not is_new and ca_entry.get('max_percentage_increase', 100) > 100:
                multiplier = ca_entry['max_percentage_increase'] / 100
                recent_history_header = f"🌕 <b>Recent History</b> (<i>{multiplier:.1f}x from call</i>)"
            else:
                recent_history_header = "🌕 <b>Recent History</b>"
            
            message = f"""
{header}
{metadata['name']}
<code>{ca}</code>

┌ <code>FDV:</code>           <b>{format_market_cap(metadata.get('fdv', 0))}</b>  
├ <code>Caller:</code>    <b>{current_user}</b>  
├ <code>Group:</code>      <b>{current_group}</b>  
├ <code>Scans:</code>      <b>{ca_entry['count']}</b>
└ <code>Smart:</code>      <b>{ca_entry['smart_count']}</b>

{recent_history_header}
{expandable_history}
            """.strip()

            # Send to main channel
            reply_to = ca_entry['message_id'] if ca_entry['message_id'] else None
            sent_message_id = await send_to_channel_via_bot(message, reply_to=reply_to)
            
            if sent_message_id:
                ca_entry['message_id'] = ca_entry['message_id'] or sent_message_id
                if is_new:
                    insert_ca_entry(ca, ca_entry)
                else:
                    update_ca_entry(ca, {
                        'count': ca_entry['count'],
                        'smart_count': ca_entry['smart_count'],
                        'history': ca_entry['history'],
                        'smart_users': ca_entry['smart_users'],
                        'last_mentioned': ca_entry['last_mentioned'],
                        'message_id': ca_entry['message_id']
                    })
                
                # Send to filter channels
                await send_to_filter_channels(ca_entry, metadata, current_user, current_group, is_new)

    except Exception as e:
        logging.error(f"⚠️ Error processing message: {str(e)}")

async def check_price_alerts(sensitivity=0.32):
    """Check price alerts for main and filter channels."""
    while True:
        try:
            conn = get_db_conn()
            try:
                cursor = conn.cursor(dictionary=True)
                cursor.execute("""
                    SELECT ca, fdv_initial, ath_market_cap, max_percentage_increase, 
                           message_id, posted_at, ath_timestamp
                    FROM ca_tracker 
                    WHERE active = TRUE
                """)
                entries = cursor.fetchall()
            finally:
                cursor.close()
                conn.close()
            
            for entry in entries:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(
                            f'https://api.dexscreener.com/tokens/v1/solana/{entry["ca"]}',
                            timeout=10
                        ) as resp:
                            if resp.status != 200:
                                logging.warning(f"DexScreener API returned {resp.status} for CA {entry['ca']}")
                                continue
                            
                            ds_data = await resp.json()
                            if not isinstance(ds_data, list) or len(ds_data) == 0:
                                logging.info(f"No pairs found for CA {entry['ca']}")
                                continue
                            
                            pair_data = ds_data[0]
                            current_fdv = float(pair_data.get('marketCap', 0))
                            fdv_initial = float(entry['fdv_initial'] or 0)
                            if fdv_initial <= 0:
                                logging.warning(f"Invalid initial market cap for CA {entry['ca']}")
                                continue
                            
                            # Check if fallen too much
                            if current_fdv < 0.6 * fdv_initial:
                                update_ca_entry(entry['ca'], {'active': False})
                                logging.info(f"Stopped monitoring CA {entry['ca']} because below -60% from initial_fdv")
                                continue
                            
                            current_multiplier = current_fdv / fdv_initial
                            new_max_percentage_increase = max(
                                entry['max_percentage_increase'] or 0,
                                current_multiplier * 100
                            )
                            new_ath_market_cap = max(
                                entry['ath_market_cap'] or 0,
                                current_fdv
                            )
                            new_ath_timestamp = (
                                datetime.datetime.now(pytz.utc)
                                if new_ath_market_cap > (entry['ath_market_cap'] or 0) or entry['ath_timestamp'] is None
                                else ensure_timezone_aware(entry['ath_timestamp'])
                            )

                            update_ca_entry(entry['ca'], {
                                'max_percentage_increase': new_max_percentage_increase,
                                'ath_market_cap': new_ath_market_cap,
                                'ath_timestamp': new_ath_timestamp
                            })

                            # Check main channel alert
                            if (current_fdv > fdv_initial and 
                                current_fdv > (entry['ath_market_cap'] or 0) * (1 + sensitivity)):
                                multiplier = current_fdv / fdv_initial
                                emoji = (
                                    "🎉" if multiplier < 2 else
                                    "🔥" if multiplier < 3 else
                                    "🚀" if multiplier < 5 else
                                    "🌙" if multiplier < 10 else
                                    "🌕"
                                )
                                
                                posted_at = ensure_timezone_aware(entry['posted_at'])
                                time_diff = format_time_diff(posted_at, datetime.datetime.now(pytz.utc))
                                
                                initial_mc_str = format_market_cap(fdv_initial)
                                current_mc_str = format_market_cap(current_fdv)
                                
                                message = (
                                    f"{emoji} <b>{multiplier:.1f}x</b> | <i>From</i> <b>{initial_mc_str}</b> → <b>{current_mc_str}</b> within ⏰<b>{time_diff}</b>"
                                )
                                
                                # Send to main channel
                                await send_to_channel_via_bot(
                                    message,
                                    reply_to=entry['message_id']
                                )
                                
                                # Send to filter channels with gain alerts enabled
                                channels = get_filter_channels(active_only=True)
                                for channel in channels:
                                    if channel['gain_alerts_enabled']:
                                        # Check if CA was posted to this channel
                                        channel_msg_id = get_channel_message_id(channel['channel_id'], entry['ca'])
                                        if channel_msg_id:
                                            # Check channel-specific sensitivity
                                            channel_sensitivity = channel.get('gain_sensitivity', 0.32)
                                            if current_fdv > (entry['ath_market_cap'] or 0) * (1 + channel_sensitivity):
                                                await send_to_channel_via_bot(
                                                    message,
                                                    reply_to=channel_msg_id,
                                                    channel_id=channel['channel_id']
                                                )
                                
                                update_ca_entry(entry['ca'], {
                                    'last_alerted': multiplier
                                })
                            
                            await asyncio.sleep(2)
                            
                except Exception as e:
                    logging.error(f"Error checking CA {entry['ca']}: {str(e)}")
                    continue
            
            await asyncio.sleep(10)
            
        except Exception as e:
            logging.error(f"Error in check_price_alerts: {str(e)}")
            await asyncio.sleep(60)

# ============= MAIN EXECUTION =============

if __name__ == '__main__':
    try:
        # Initialize database
        initialize_database()

        # Start both clients
        user_client.start()
        bot_client.start()

        # Background tasks run on userbot
        user_client.loop.create_task(cleanup_old_entries())
        user_client.loop.create_task(check_price_alerts())

        logging.info("✅ Userbot started for group monitoring")
        logging.info("✅ Bot started for commands and menus")
        logging.info(f"✅ Main channel: {MAIN_CHANNEL}")
        logging.info(f"✅ Monitoring {len(groups)} groups")
        logging.info(f"✅ {len(ADMIN_IDS)} admins configured")

        # Run both clients until disconnected
        user_client.run_until_disconnected()
        bot_client.run_until_disconnected()
    except Exception as e:
        logging.error(f"Fatal startup error: {str(e)}")
        raise
