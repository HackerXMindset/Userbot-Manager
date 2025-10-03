import asyncio
import logging
import re
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Set, List, Dict, Optional, Union
import base58
import requests
import random
from telethon import TelegramClient, events, functions, types
from telethon.tl.types import (
    MessageEntityBotCommand, 
    KeyboardButtonCallback,
    ReplyInlineMarkup,
    KeyboardButtonUrl,
    Channel,
    Chat,
    User
)
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    FloodWaitError,
    ChatAdminRequiredError,
    UserNotParticipantError,
    ChannelPrivateError,
    ChatWriteForbiddenError,
    UsernameNotOccupiedError,
    PeerIdInvalidError
)
from telethon.tl.functions.channels import JoinChannelRequest, GetFullChannelRequest
from telethon.tl.functions.messages import GetHistoryRequest
from dotenv import load_dotenv
import hashlib
import time
from collections import defaultdict

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('userbot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class SolanaUserbot:
    def __init__(self):
        # Validate required environment variables
        required_vars = ['API_ID', 'API_HASH', 'PHONE_NUMBER']
        missing_vars = []
        
        for var in required_vars:
            if not os.getenv(var):
                missing_vars.append(var)
        
        if missing_vars:
            logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        try:
            self.api_id = int(os.getenv('API_ID'))
        except (ValueError, TypeError):
            logger.error("API_ID must be a valid integer")
            raise ValueError("API_ID must be a valid integer")
            
        self.api_hash = os.getenv('API_HASH')
        self.phone = os.getenv('PHONE_NUMBER')
        self.session_name = os.getenv('SESSION_NAME', 'userbot_session')
        
        # Legacy single user support
        self.monitor_username = os.getenv('MONITOR_USERNAME')
        self.monitor_user_id = int(os.getenv('MONITOR_USER_ID', 0)) if os.getenv('MONITOR_USER_ID') else None
        
        # Multi-user support
        monitor_usernames = os.getenv('MONITOR_USERNAMES', '')
        self.monitor_usernames = set()
        if monitor_usernames:
            self.monitor_usernames = {username.strip().lower() for username in monitor_usernames.split(',') if username.strip()}
        if self.monitor_username:
            self.monitor_usernames.add(self.monitor_username.lower())
        
        monitor_user_ids = os.getenv('MONITOR_USER_IDS', '')
        self.monitor_user_ids = set()
        if monitor_user_ids:
            self.monitor_user_ids = {int(uid.strip()) for uid in monitor_user_ids.split(',') if uid.strip().isdigit()}
        if self.monitor_user_id:
            self.monitor_user_ids.add(self.monitor_user_id)
        
        # Multi-source chat support
        self.source_chat_id = int(os.getenv('SOURCE_CHAT_ID')) if os.getenv('SOURCE_CHAT_ID') else None
        source_chat_ids = os.getenv('SOURCE_CHAT_IDS', '')
        self.source_chat_ids = set()
        if source_chat_ids:
            self.source_chat_ids = {int(chat_id.strip()) for chat_id in source_chat_ids.split(',') if chat_id.strip().lstrip('-').isdigit()}
        if self.source_chat_id:
            self.source_chat_ids.add(self.source_chat_id)
        
        public_groups = os.getenv('PUBLIC_GROUPS_TO_MONITOR', '')
        self.public_groups_to_monitor = [group.strip() for group in public_groups.split(',') if group.strip()]
        
        target_chats = os.getenv('TARGET_CHAT_IDS', '')
        self.target_chat_ids = [int(chat_id.strip()) for chat_id in target_chats.split(',') if chat_id.strip()]
        
        self.scanner_bot_id = int(os.getenv('SCANNER_BOT_ID', 7178305557))
        self.button_text = os.getenv('BUTTON_TEXT', '🛰 Just Scanning')
        self.exact_button_match = os.getenv('EXACT_BUTTON_MATCH', 'true').lower() == 'true'
        self.button_click_retries = int(os.getenv('BUTTON_CLICK_RETRIES', 3))
        self.button_retry_delay = int(os.getenv('BUTTON_RETRY_DELAY', 2))
        
        self.monitor_without_joining = os.getenv('MONITOR_WITHOUT_JOINING', 'true').lower() == 'true'
        self.polling_interval = int(os.getenv('POLLING_INTERVAL', 30))
        
        self.pnl_delay_minutes = int(os.getenv('PNL_DELAY_MINUTES', 30))
        self.forward_delay_seconds = int(os.getenv('FORWARD_DELAY_SECONDS', 5))
        self.enable_forward_delay = os.getenv('ENABLE_FORWARD_DELAY', 'true').lower() == 'true'
        
        self.notification_chat_id = int(os.getenv('NOTIFICATION_CHAT_ID')) if os.getenv('NOTIFICATION_CHAT_ID') else None
        self.monitor_bot_username = os.getenv('MONITOR_BOT_USERNAME', '').strip('@').lower()
        
        excluded_users = os.getenv('EXCLUDED_USER_IDS', '')
        self.excluded_user_ids = set()
        if excluded_users:
            self.excluded_user_ids = {int(uid.strip()) for uid in excluded_users.split(',') if uid.strip().isdigit()}
        
        self.client = TelegramClient(self.session_name, self.api_id, self.api_hash)
        
        self.db_path = 'userbot_data.db'
        self.setup_database()
        
        self.posted_addresses: Set[str] = set()
        self.user_posted_addresses: Dict[int, Set[str]] = {}
        self.message_tracking: Dict[int, Dict] = {}
        self.button_retry_tracking: Dict[int, Dict] = {}
        self.pnl_scheduled_tasks: Dict[str, asyncio.Task] = {}
        
        self.monitored_public_groups: Dict[Union[int, str], Dict] = {}
        self.last_message_ids: Dict[Union[int, str], int] = {}
        
        self.solana_pattern = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')
        
        self.load_posted_addresses()
        
        self.last_clear_time = datetime.now()
        
        self.monitoring_task = None
        
        # API rate limiting
        self.api_calls = defaultdict(list)
        self.api_rate_limit = 5  # calls per second
        self.api_rate_window = 1  # seconds

    def setup_database(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS posted_addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT UNIQUE NOT NULL,
                user_id INTEGER,
                username TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                source_chat_id INTEGER,
                target_chat_ids TEXT,
                initial_market_cap REAL DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_message_id INTEGER,
                forwarded_message_id INTEGER,
                target_chat_id INTEGER,
                address TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS monitored_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_identifier TEXT UNIQUE NOT NULL,
                group_id INTEGER,
                title TEXT,
                username TEXT,
                last_message_id INTEGER DEFAULT 0,
                is_accessible BOOLEAN DEFAULT 1,
                last_checked TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS pnl_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                address TEXT NOT NULL,
                target_chat_id INTEGER NOT NULL,
                scheduled_time TIMESTAMP NOT NULL,
                sent BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                initial_market_cap REAL DEFAULT 0
            )
        ''')
        
        conn.commit()
        conn.close()

    def load_posted_addresses(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT address, user_id FROM posted_addresses')
        rows = cursor.fetchall()
        
        for address, user_id in rows:
            self.posted_addresses.add(address)
            if user_id not in self.user_posted_addresses:
                self.user_posted_addresses[user_id] = set()
            self.user_posted_addresses[user_id].add(address)
        
        cursor.execute('SELECT group_identifier, group_id, last_message_id FROM monitored_groups')
        groups = cursor.fetchall()
        
        for group_identifier, group_id, last_msg_id in groups:
            self.last_message_ids[group_identifier] = last_msg_id
            if group_id:
                self.last_message_ids[group_id] = last_msg_id
        
        conn.close()
        logger.info(f"Loaded {len(self.posted_addresses)} previously posted addresses")

    def is_valid_solana_address(self, address: str) -> bool:
        if not address or len(address) < 32 or len(address) > 44:
            return False
        
        try:
            decoded = base58.b58decode(address)
            return len(decoded) == 32
        except Exception:
            return False

    def extract_solana_addresses(self, text: str) -> List[str]:
        if not text:
            return []
        
        potential_addresses = self.solana_pattern.findall(text)
        valid_addresses = []
        
        for addr in potential_addresses:
            if self.is_valid_solana_address(addr):
                valid_addresses.append(addr)
        
        return valid_addresses

    def is_target_user(self, sender) -> bool:
        """Check if the sender is one of our target users to monitor"""
        if not sender:
            return False
        
        # Check by user ID
        if sender.id in self.monitor_user_ids:
            return True
        
        # Check by username
        if hasattr(sender, 'username') and sender.username:
            if sender.username.lower() in self.monitor_usernames:
                return True
        
        return False

    def is_source_chat(self, chat_id: int) -> bool:
        """Check if the chat ID is one of our monitored source chats"""
        if not self.source_chat_ids:
            return True  # If no specific source chats configured, monitor all
        return chat_id in self.source_chat_ids

    async def rate_limit_api_call(self, api_name: str):
        """Rate limit API calls to prevent 429 errors"""
        current_time = time.time()
        
        # Clean old calls outside the window
        self.api_calls[api_name] = [
            call_time for call_time in self.api_calls[api_name] 
            if current_time - call_time < self.api_rate_window
        ]
        
        # If we're at the rate limit, wait
        if len(self.api_calls[api_name]) >= self.api_rate_limit:
            sleep_time = self.api_rate_window - (current_time - self.api_calls[api_name][0])
            if sleep_time > 0:
                logger.debug(f"Rate limiting {api_name} API call, sleeping {sleep_time:.2f}s")
                await asyncio.sleep(sleep_time)
        
        # Record this call
        self.api_calls[api_name].append(current_time)

    async def get_market_cap(self, address: str) -> float:
        try:
            await self.rate_limit_api_call('dexscreener')
            
            url = f"https://api.dexscreener.com/tokens/v1/solana/{address}"
            response = requests.get(url, headers={"Accept": "*/*"}, timeout=10)
            
            if response.status_code == 429:
                logger.warning(f"Rate limited by DexScreener API, retrying in 5 seconds...")
                await asyncio.sleep(5)
                response = requests.get(url, headers={"Accept": "*/*"}, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    token_data = data[0]
                    market_cap = token_data.get('marketCap')
                    return float(market_cap) if market_cap else 0
            
            logger.warning(f"DexScreener API returned status {response.status_code} for {address}")
            return 0
        except Exception as e:
            logger.error(f"Error fetching market cap for {address}: {e}")
            return 0

    async def format_notification_message(self, sender, message_type: str, message_text: str, chat_title: str = None, message_link: str = None) -> str:
        sender_name = getattr(sender, 'first_name', 'Unknown')
        sender_username = f"@{sender.username}" if getattr(sender, 'username', None) else "No username"
        
        preview = message_text[:100] + "..." if len(message_text) > 100 else message_text
        
        notification = f"🔔 **{message_type}**\n\n"
        notification += f"👤 **From:** {sender_name} ({sender_username})\n"
        
        if chat_title:
            notification += f"💬 **In:** {chat_title}\n"
        
        notification += f"📝 **Message:** {preview}\n"
        
        if message_link:
            notification += f"🔗 **Link:** {message_link}"
        
        return notification

    async def save_posted_address(self, address: str, user_id: int, username: str, source_chat_id: int, target_chat_ids: List[int], initial_market_cap: float):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO posted_addresses 
                (address, user_id, username, source_chat_id, target_chat_ids, initial_market_cap)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (address, user_id, username, source_chat_id, ','.join(map(str, target_chat_ids)), initial_market_cap))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving address to database: {e}")
        finally:
            conn.close()

    async def save_message_tracking(self, original_msg_id: int, forwarded_msg_id: int, target_chat_id: int, address: str):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT INTO message_tracking 
                (original_message_id, forwarded_message_id, target_chat_id, address)
                VALUES (?, ?, ?, ?)
            ''', (original_msg_id, forwarded_msg_id, target_chat_id, address))
            conn.commit()
        except Exception as e:
            logger.error(f"Error saving message tracking: {e}")
        finally:
            conn.close()

    async def schedule_pnl_message(self, address: str, target_chat_id: int, initial_market_cap: float):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            scheduled_time = datetime.now() + timedelta(minutes=self.pnl_delay_minutes)
            cursor.execute('''
                INSERT INTO pnl_schedule 
                (address, target_chat_id, scheduled_time, initial_market_cap)
                VALUES (?, ?, ?, ?)
            ''', (address, target_chat_id, scheduled_time, initial_market_cap))
            conn.commit()
            
            task_key = f"{address}_{target_chat_id}_{int(time.time())}"
            
            tasks_to_cancel = []
            for existing_key in self.pnl_scheduled_tasks:
                if existing_key.startswith(f"{address}_{target_chat_id}_"):
                    tasks_to_cancel.append(existing_key)
            
            for key in tasks_to_cancel:
                if key in self.pnl_scheduled_tasks:
                    self.pnl_scheduled_tasks[key].cancel()
                    del self.pnl_scheduled_tasks[key]
            
            self.pnl_scheduled_tasks[task_key] = asyncio.create_task(
                self.send_pnl_message_after_delay(address, target_chat_id, self.pnl_delay_minutes * 60, task_key, initial_market_cap)
            )
            
            logger.info(f"Scheduled PnL message for {address} in {self.pnl_delay_minutes} minutes to chat {target_chat_id}")
            
        except Exception as e:
            logger.error(f"Error scheduling PnL message: {e}")
        finally:
            conn.close()

    async def send_pnl_message_after_delay(self, address: str, target_chat_id: int, delay_seconds: int, task_key: str, initial_market_cap: float):
        try:
            logger.info(f"Waiting {delay_seconds} seconds before sending PnL for {address}")
            await asyncio.sleep(delay_seconds)
            
            current_market_cap = await self.get_market_cap(address)
            logger.info(f"Address {address}: Initial MC: ${initial_market_cap:,.2f}, Current MC: ${current_market_cap:,.2f}")
            
            if current_market_cap >= (initial_market_cap * 2):
                pnl_message = f"/pnl {address}"
                
                try:
                    sent_message = await self.client.send_message(target_chat_id, pnl_message)
                    logger.info(f"✅ PnL sent for {address} to chat {target_chat_id} (MC doubled: ${initial_market_cap:,.2f} -> ${current_market_cap:,.2f})")
                    
                    conn = sqlite3.connect(self.db_path)
                    cursor = conn.cursor()
                    cursor.execute('''
                        UPDATE pnl_schedule 
                        SET sent = 1 
                        WHERE address = ? AND target_chat_id = ? AND sent = 0
                    ''', (address, target_chat_id))
                    conn.commit()
                    conn.close()
                    
                except Exception as e:
                    logger.error(f"❌ Failed to send PnL message for {address} to chat {target_chat_id}: {e}")
            else:
                logger.info(f"❌ PnL NOT sent for {address} - MC condition not met (${current_market_cap:,.2f} < ${initial_market_cap * 2:,.2f})")
            
        except asyncio.CancelledError:
            logger.info(f"PnL task cancelled for {address}")
        except Exception as e:
            logger.error(f"Error in PnL message task: {e}")
        finally:
            if task_key in self.pnl_scheduled_tasks:
                del self.pnl_scheduled_tasks[task_key]

    async def update_monitored_group(self, group_identifier: str, group_id: int, title: str, username: str, last_message_id: int, is_accessible: bool):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO monitored_groups 
                (group_identifier, group_id, title, username, last_message_id, is_accessible, last_checked)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (group_identifier, group_id, title, username, last_message_id, is_accessible, datetime.now()))
            conn.commit()
        except Exception as e:
            logger.error(f"Error updating monitored group: {e}")
        finally:
            conn.close()

    async def clear_old_data(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                DELETE FROM posted_addresses 
                WHERE posted_at < datetime('now', '-1 day')
            ''')
            
            cursor.execute('''
                DELETE FROM message_tracking 
                WHERE created_at < datetime('now', '-1 day')
            ''')
            
            cursor.execute('''
                DELETE FROM pnl_schedule 
                WHERE created_at < datetime('now', '-1 day')
            ''')
            
            deleted_addresses = cursor.rowcount
            conn.commit()
            
            self.posted_addresses.clear()
            self.user_posted_addresses.clear()
            self.load_posted_addresses()
            
            logger.info(f"Cleared {deleted_addresses} old records from database")
            
        except Exception as e:
            logger.error(f"Error clearing old data: {e}")
        finally:
            conn.close()

    async def auto_clear_check(self):
        current_time = datetime.now()
        if current_time - self.last_clear_time >= timedelta(hours=24):
            await self.clear_old_data()
            self.last_clear_time = current_time

    async def resolve_group_entity(self, group_identifier: Union[str, int]) -> Optional[Union[Channel, Chat]]:
        try:
            if isinstance(group_identifier, str):
                username = group_identifier.lstrip('@')
                entity = await self.client.get_entity(username)
            else:
                entity = await self.client.get_entity(group_identifier)
            
            return entity
        except (UsernameNotOccupiedError, PeerIdInvalidError, ValueError) as e:
            logger.error(f"Cannot resolve group {group_identifier}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error resolving group {group_identifier}: {e}")
            return None

    async def can_access_group(self, entity: Union[Channel, Chat]) -> bool:
        try:
            if isinstance(entity, Channel):
                if entity.username:
                    return True
                try:
                    full_channel = await self.client(GetFullChannelRequest(entity))
                    return True
                except ChannelPrivateError:
                    return False
            elif isinstance(entity, Chat):
                return False
            
            return False
        except Exception as e:
            logger.error(f"Error checking group access: {e}")
            return False

    async def get_group_messages(self, entity: Union[Channel, Chat], limit: int = 50, offset_id: int = 0) -> List:
        try:
            messages = await self.client.get_messages(entity, limit=limit, offset_id=offset_id)
            return messages
        except Exception as e:
            logger.error(f"Error getting messages from {entity.id}: {e}")
            return []

    async def setup_public_group_monitoring(self):
        logger.info("Setting up public group monitoring...")
        
        for group_identifier in self.public_groups_to_monitor:
            try:
                entity = await self.resolve_group_entity(group_identifier)
                if not entity:
                    logger.warning(f"Could not resolve group: {group_identifier}")
                    continue
                
                if await self.can_access_group(entity):
                    self.monitored_public_groups[group_identifier] = {
                        'entity': entity,
                        'id': entity.id,
                        'title': getattr(entity, 'title', 'Unknown'),
                        'username': getattr(entity, 'username', None),
                        'accessible': True
                    }
                    
                    if group_identifier not in self.last_message_ids:
                        messages = await self.get_group_messages(entity, limit=1)
                        if messages:
                            self.last_message_ids[group_identifier] = messages[0].id
                            self.last_message_ids[entity.id] = messages[0].id
                        else:
                            self.last_message_ids[group_identifier] = 0
                    
                    await self.update_monitored_group(
                        group_identifier, 
                        entity.id, 
                        getattr(entity, 'title', 'Unknown'),
                        getattr(entity, 'username', None),
                        self.last_message_ids.get(group_identifier, 0),
                        True
                    )
                    
                    logger.info(f"Successfully setup monitoring for public group: {getattr(entity, 'title', group_identifier)}")
                else:
                    logger.warning(f"Cannot access group without joining: {group_identifier}")
                    await self.update_monitored_group(group_identifier, 0, 'Unknown', None, 0, False)
                    
            except Exception as e:
                logger.error(f"Error setting up monitoring for {group_identifier}: {e}")

    async def poll_public_groups(self):
        while True:
            try:
                await self.auto_clear_check()
                
                for group_identifier, group_info in self.monitored_public_groups.items():
                    if not group_info['accessible']:
                        continue
                    
                    entity = group_info['entity']
                    last_message_id = self.last_message_ids.get(group_identifier, 0)
                    
                    try:
                        messages = await self.get_group_messages(entity, limit=50)
                        
                        new_messages = []
                        for msg in messages:
                            if msg.id > last_message_id:
                                new_messages.append(msg)
                        
                        if new_messages:
                            new_messages.sort(key=lambda x: x.id)
                            
                            self.last_message_ids[group_identifier] = new_messages[-1].id
                            self.last_message_ids[entity.id] = new_messages[-1].id
                            
                            for message in new_messages:
                                await self.process_message(message, entity.id)
                            
                            await self.update_monitored_group(
                                group_identifier,
                                entity.id,
                                group_info['title'],
                                group_info['username'],
                                new_messages[-1].id,
                                True
                            )
                            
                            logger.info(f"Processed {len(new_messages)} new messages from {group_info['title']}")
                        
                    except Exception as e:
                        logger.error(f"Error polling group {group_identifier}: {e}")
                        await self.update_monitored_group(
                            group_identifier,
                            group_info['id'],
                            group_info['title'],
                            group_info['username'],
                            self.last_message_ids.get(group_identifier, 0),
                            False
                        )
                
                await asyncio.sleep(self.polling_interval)
                
            except Exception as e:
                logger.error(f"Error in public group polling: {e}")
                await asyncio.sleep(self.polling_interval)

    async def process_message(self, message, source_chat_id: int):
        try:
            if not message.sender:
                return
            
            sender = message.sender
            
            if not self.is_target_user(sender):
                return
            
            addresses = self.extract_solana_addresses(message.text)
            if not addresses:
                return
            
            user_id = sender.id
            if user_id not in self.user_posted_addresses:
                self.user_posted_addresses[user_id] = set()
            
            new_addresses = []
            for addr in addresses:
                if addr not in self.user_posted_addresses[user_id]:
                    new_addresses.append(addr)
                    self.user_posted_addresses[user_id].add(addr)
                    self.posted_addresses.add(addr)
            
            if not new_addresses:
                logger.info(f"No new addresses from user {getattr(sender, 'username', sender.first_name)}")
                return
            
            address_to_post = new_addresses[0]
            initial_market_cap = await self.get_market_cap(address_to_post)
            
            logger.info(f"Found new Solana address: {address_to_post} with market cap: ${initial_market_cap:,.2f}")
            
            for i, target_chat_id in enumerate(self.target_chat_ids):
                try:
                    if i > 0 and self.enable_forward_delay:
                        delay = random.uniform(0, self.forward_delay_seconds)
                        logger.info(f"Waiting {delay:.2f} seconds before forwarding to next chat...")
                        await asyncio.sleep(delay)
                    
                    sent_message = await self.client.send_message(
                        target_chat_id,
                        address_to_post
                    )
                    
                    await self.save_message_tracking(
                        message.id, 
                        sent_message.id, 
                        target_chat_id, 
                        address_to_post
                    )
                    
                    self.message_tracking[sent_message.id] = {
                        'chat_id': target_chat_id,
                        'address': address_to_post,
                        'timestamp': datetime.now()
                    }
                    
                    await self.schedule_pnl_message(address_to_post, target_chat_id, initial_market_cap)
                    
                    logger.info(f"Forwarded address to chat {target_chat_id}")
                    
                except Exception as e:
                    logger.error(f"Error forwarding to chat {target_chat_id}: {e}")
            
            await self.save_posted_address(
                address_to_post, 
                user_id, 
                getattr(sender, 'username', sender.first_name) or "Unknown",
                source_chat_id,
                self.target_chat_ids,
                initial_market_cap
            )
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def login(self):
        try:
            await self.client.start(phone=self.phone)
            
            if not await self.client.is_user_authorized():
                logger.info("User not authorized, starting login process...")
                
                await self.client.send_code_request(self.phone)
                
                code = input("Enter the code you received: ")
                
                try:
                    await self.client.sign_in(self.phone, code)
                except SessionPasswordNeededError:
                    password = input("Enter your 2FA password: ")
                    await self.client.sign_in(password=password)
                except PhoneCodeInvalidError:
                    logger.error("Invalid phone code entered")
                    return False
                except Exception as e:
                    logger.error(f"Login error: {e}")
                    return False
            
            me = await self.client.get_me()
            logger.info(f"Successfully logged in as {me.username or me.first_name} (ID: {me.id})")
            return True
            
        except Exception as e:
            logger.error(f"Login failed: {e}")
            return False

    async def join_chat_if_needed(self, chat_id: int):
        try:
            chat = await self.client.get_entity(chat_id)
            
            try:
                await self.client.get_permissions(chat)
                logger.info(f"Already a member of chat {chat_id}")
                return True
            except UserNotParticipantError:
                logger.info(f"Not a member of chat {chat_id}, attempting to join...")
                
                if hasattr(chat, 'broadcast') and chat.broadcast:
                    await self.client(JoinChannelRequest(chat))
                    logger.info(f"Successfully joined channel {chat_id}")
                else:
                    logger.warning(f"Cannot auto-join group {chat_id} - might need invite link")
                    return False
                    
        except Exception as e:
            logger.error(f"Error checking/joining chat {chat_id}: {e}")
            return False
        
        return True

    async def setup_monitoring(self):
        
        @self.client.on(events.NewMessage)
        async def handle_new_message(event):
            try:
                await self.auto_clear_check()
                
                sender = await event.get_sender()
                if not sender:
                    return
                
                if not self.is_target_user(sender):
                    return
                
                if not self.is_source_chat(event.chat_id):
                    return
                
                await self.process_message(event.message, event.chat_id)
                
            except Exception as e:
                logger.error(f"Error in message handler: {e}")

        @self.client.on(events.NewMessage)
        async def handle_bot_replies(event):
            try:
                if not event.sender_id or event.sender_id != self.scanner_bot_id:
                    return
                
                if not event.reply_to_msg_id:
                    return
                
                if event.reply_to_msg_id not in self.message_tracking:
                    return
                
                tracking_info = self.message_tracking[event.reply_to_msg_id]
                
                if event.chat_id != tracking_info['chat_id']:
                    return
                
                logger.info(f"Detected reply from scanner bot for address: {tracking_info['address']}")
                
                button_found = False
                if event.buttons:
                    for row in event.buttons:
                        for button in row:
                            if hasattr(button, 'text'):
                                button_match = (button.text == self.button_text if self.exact_button_match 
                                              else self.button_text in button.text)
                                
                                if button_match:
                                    button_found = True
                                    success = await self.click_button_with_retry(
                                        button, event.reply_to_msg_id, tracking_info['address']
                                    )
                                    
                                    if success:
                                        del self.message_tracking[event.reply_to_msg_id]
                                        if event.reply_to_msg_id in self.button_retry_tracking:
                                            del self.button_retry_tracking[event.reply_to_msg_id]
                                    return
                
                if not button_found:
                    logger.warning(f"Button '{self.button_text}' not found in scanner bot reply")
                
            except Exception as e:
                logger.error(f"Error in bot reply handler: {e}")

    async def click_button_with_retry(self, button, reply_msg_id: int, address: str) -> bool:
        msg_id_key = reply_msg_id
        
        if msg_id_key not in self.button_retry_tracking:
            self.button_retry_tracking[msg_id_key] = {
                'attempts': 0,
                'address': address,
                'last_attempt': None
            }
        
        tracking = self.button_retry_tracking[msg_id_key]
        
        for attempt in range(tracking['attempts'], self.button_click_retries):
            tracking['attempts'] = attempt + 1
            tracking['last_attempt'] = datetime.now()
            
            try:
                await button.click()
                logger.info(f"Successfully clicked '{self.button_text}' button for {address} (attempt {attempt + 1})")
                return True
                
            except Exception as e:
                logger.error(f"Button click attempt {attempt + 1} failed for {address}: {e}")
                
                if attempt < self.button_click_retries - 1:
                    logger.info(f"Retrying button click in {self.button_retry_delay} seconds...")
                    await asyncio.sleep(self.button_retry_delay)
                else:
                    logger.error(f"All {self.button_click_retries} button click attempts failed for {address}")
        
        return False

        @self.client.on(events.NewMessage)
        async def handle_notifications(event):
            try:
                if not self.notification_chat_id:
                    logger.debug("Notification handler: No notification chat configured")
                    return
                
                sender = await event.get_sender()
                if not sender:
                    logger.debug("Notification handler: No sender found")
                    return
                    
                if sender.id in self.excluded_user_ids:
                    logger.debug(f"Notification handler: Sender {sender.id} is in excluded users")
                    return
                
                logger.debug(f"Notification handler: Processing message from {getattr(sender, 'username', sender.first_name)} (ID: {sender.id})")
                logger.debug(f"Notification handler: Event is_private: {event.is_private}, chat_id: {event.chat_id}")
                logger.debug(f"Notification handler: Reply to msg ID: {event.reply_to_msg_id}")
                
                message_text = event.message.text or "[Media/Non-text message]"
                chat = await event.get_chat()
                chat_title = getattr(chat, 'title', 'Private Chat')
                
                notification_type = None
                message_link = None
                
                if event.is_private:
                    notification_type = "Direct Message"
                    logger.debug("Notification handler: Detected direct message")
                elif event.reply_to_msg_id:
                    logger.debug(f"Notification handler: Reply detected, checking if {event.reply_to_msg_id} in message_tracking")
                    logger.debug(f"Notification handler: Message tracking keys: {list(self.message_tracking.keys())}")
                    if event.reply_to_msg_id in self.message_tracking:
                        notification_type = "Reply to Bot"
                        logger.debug("Notification handler: Detected reply to bot")
                        if hasattr(event.message, 'id') and hasattr(chat, 'username') and chat.username:
                            message_link = f"https://t.me/{chat.username}/{event.message.id}"
                        elif hasattr(event.message, 'id'):
                            message_link = f"https://t.me/c/{str(chat.id)[4:]}/{event.message.id}"
                elif self.monitor_bot_username and self.monitor_bot_username in message_text.lower():
                    notification_type = "Bot Mention"
                    logger.debug(f"Notification handler: Detected mention of @{self.monitor_bot_username}")
                    if hasattr(event.message, 'id') and hasattr(chat, 'username') and chat.username:
                        message_link = f"https://t.me/{chat.username}/{event.message.id}"
                    elif hasattr(event.message, 'id'):
                        message_link = f"https://t.me/c/{str(chat.id)[4:]}/{event.message.id}"
                
                if notification_type:
                    logger.debug(f"Notification handler: Sending {notification_type} notification")
                    notification_message = await self.format_notification_message(
                        sender, notification_type, message_text, 
                        chat_title if not event.is_private else None, 
                        message_link
                    )
                    
                    try:
                        await self.client.send_message(self.notification_chat_id, notification_message)
                        logger.info(f"✅ Sent {notification_type.lower()} notification from {getattr(sender, 'username', sender.first_name)}")
                    except Exception as e:
                        logger.error(f"❌ Error sending notification: {e}")
                else:
                    logger.debug("Notification handler: No notification type matched")
                        
            except Exception as e:
                logger.error(f"Error in notification handler: {e}")

    async def cleanup_tasks(self):
        """Gracefully cleanup all running tasks and connections"""
        logger.info("Starting cleanup process...")
        
        try:
            # Cancel monitoring task
            if self.monitoring_task and not self.monitoring_task.done():
                logger.info("Cancelling public group monitoring task...")
                self.monitoring_task.cancel()
                try:
                    await asyncio.wait_for(self.monitoring_task, timeout=5.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
            
            # Cancel all PnL scheduled tasks
            if self.pnl_scheduled_tasks:
                logger.info(f"Cancelling {len(self.pnl_scheduled_tasks)} PnL tasks...")
                for task_key, task in list(self.pnl_scheduled_tasks.items()):
                    if not task.done():
                        task.cancel()
                        try:
                            await asyncio.wait_for(task, timeout=2.0)
                        except (asyncio.CancelledError, asyncio.TimeoutError):
                            pass
                    del self.pnl_scheduled_tasks[task_key]
            
            # Disconnect Telegram client
            if self.client and self.client.is_connected():
                logger.info("Disconnecting Telegram client...")
                await self.client.disconnect()
                
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        
        logger.info("Cleanup completed")

    async def start(self):
        logger.info("Starting Solana Memecoin Monitor Userbot...")
        
        if not await self.login():
            logger.error("Login failed, exiting...")
            return
        
        await self.setup_monitoring()
        
        for chat_id in self.target_chat_ids:
            await self.join_chat_if_needed(chat_id)
        
        if self.monitor_without_joining and self.public_groups_to_monitor:
            await self.setup_public_group_monitoring()
            
            self.monitoring_task = asyncio.create_task(self.poll_public_groups())
            logger.info("Started public group monitoring task")
        
        logger.info("Userbot is now running and monitoring...")
        
        # Log monitored users
        monitored_users_info = []
        if self.monitor_usernames:
            monitored_users_info.extend([f"@{username}" for username in self.monitor_usernames])
        if self.monitor_user_ids:
            monitored_users_info.extend([str(uid) for uid in self.monitor_user_ids])
        logger.info(f"Monitoring users: {', '.join(monitored_users_info) if monitored_users_info else 'None configured'}")
        
        # Log source chats
        if self.source_chat_ids:
            logger.info(f"Source chats: {', '.join(map(str, self.source_chat_ids))}")
        else:
            logger.info("Source chats: Any chat")
        logger.info(f"Target chats: {self.target_chat_ids}")
        logger.info(f"Public groups to monitor: {self.public_groups_to_monitor}")
        logger.info(f"Monitor without joining: {self.monitor_without_joining}")
        logger.info(f"Scanner bot ID: {self.scanner_bot_id}")
        logger.info(f"Button text to click: '{self.button_text}'")
        logger.info(f"PnL delay: {self.pnl_delay_minutes} minutes")
        logger.info(f"Notification chat: {self.notification_chat_id or 'Disabled'}")
        logger.info(f"Excluded users: {len(self.excluded_user_ids)} users")
        
        try:
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("Userbot stopped by user")
        except Exception as e:
            logger.error(f"Userbot error: {e}")
        finally:
            await self.cleanup_tasks()

async def main():
    try:
        userbot = SolanaUserbot()
        await userbot.start()
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        return 1
    except KeyboardInterrupt:
        logger.info("Application interrupted by user")
        return 0
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
