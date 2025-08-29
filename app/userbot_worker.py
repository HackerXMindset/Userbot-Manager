import asyncio
import logging
import re
from typing import Dict, Any, Optional, List
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import Message

from app.config import settings
from app.db import db
from app.models import BotModel, GroupModel
from app.events import EventRouter

logger = logging.getLogger(__name__)

class UserbotWorker:
    """Userbot worker for monitoring groups and sending calls"""
    
    def __init__(self, userbot_id: int, session_string: str):
        self.userbot_id = userbot_id
        self.session_string = session_string
        self.client: Optional[TelegramClient] = None
        self.running = False
        self.event_router = EventRouter()
        
        # Models
        self.bot_model = BotModel(db)
        self.group_model = GroupModel(db)
        
        # Solana address pattern
        self.solana_pattern = re.compile(settings.solana_pattern)
    
    async def start(self):
        """Start the userbot worker"""
        if self.running:
            return
        
        try:
            # Initialize Telegram client
            self.client = TelegramClient(
                StringSession(self.session_string),
                settings.api_id,
                settings.api_hash
            )
            
            await self.client.start()
            
            # Get assigned groups
            assigned_groups = await self.bot_model.get_assigned_groups(self.userbot_id)
            
            # Set up event handlers
            self._setup_event_handlers(assigned_groups)
            
            # Update bot status
            await self.bot_model.set_status(self.userbot_id, 'active')
            
            self.running = True
            
            logger.info(f"Userbot {self.userbot_id} started monitoring {len(assigned_groups)} groups")
            
        except Exception as e:
            logger.error(f"Error starting userbot {self.userbot_id}: {e}")
            await self.bot_model.set_status(self.userbot_id, 'error')
            raise
    
    async def stop(self):
        """Stop the userbot worker"""
        if not self.running:
            return
        
        self.running = False
        
        if self.client:
            await self.client.disconnect()
            self.client = None
        
        await self.bot_model.set_status(self.userbot_id, 'inactive')
        
        logger.info(f"Userbot {self.userbot_id} stopped")
    
    def _setup_event_handlers(self, groups: List[Dict[str, Any]]):
        """Setup event handlers for assigned groups"""
        if not self.client:
            return
        
        group_ids = [g['tg_chat_id'] for g in groups]
        
        @self.client.on(events.NewMessage(chats=group_ids))
        async def handle_new_message(event):
            await self._handle_message(event)
        
        @self.client.on(events.MessageEdited(chats=group_ids))
        async def handle_edited_message(event):
            await self._handle_message(event, is_edit=True)
        
        # Handle replies to our messages
        @self.client.on(events.NewMessage(incoming=True))
        async def handle_replies(event):
            if event.is_reply:
                await self._handle_reply(event)
        
        # Handle mentions
        @self.client.on(events.NewMessage(pattern=r'.*@.*'))
        async def handle_mentions(event):
            await self._handle_mention(event)
        
        # Handle DMs
        @self.client.on(events.NewMessage(incoming=True))
        async def handle_dms(event):
            if event.is_private:
                await self._handle_dm(event)
    
    async def _handle_message(self, event, is_edit: bool = False):
        """Handle new/edited messages in monitored groups"""
        try:
            message = event.message
            
            # Extract Solana addresses
            solana_addresses = self._extract_solana_addresses(message.text or "")
            
            if solana_addresses:
                await self._process_token_addresses(event, solana_addresses, is_edit)
            
            # Update last seen
            await self.bot_model.update_last_seen(self.userbot_id)
            
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_reply(self, event):
        """Handle replies to messages"""
        try:
            reply_to = await event.message.get_reply_message()
            
            if reply_to and reply_to.sender_id:
                # Check if reply is to one of our sent messages
                # This would require tracking our sent message IDs
                
                # Create reply event
                await self.event_router.create_event(
                    kind='reply',
                    src_chat_id=event.chat_id,
                    src_msg_id=event.message.id,
                    user_id=event.sender_id,
                    payload={
                        'message_text': event.message.text,
                        'reply_to_text': reply_to.text,
                        'chat_title': getattr(event.chat, 'title', 'Private'),
                        'user_name': self._get_user_name(event.sender)
                    }
                )
            
        except Exception as e:
            logger.error(f"Error handling reply: {e}")
    
    async def _handle_mention(self, event):
        """Handle mentions"""
        try:
            # Check if message contains mentions of tracked users/bots
            if '@' in (event.message.text or ''):
                await self.event_router.create_event(
                    kind='mention',
                    src_chat_id=event.chat_id,
                    src_msg_id=event.message.id,
                    user_id=event.sender_id,
                    payload={
                        'message_text': event.message.text,
                        'chat_title': getattr(event.chat, 'title', 'Private'),
                        'user_name': self._get_user_name(event.sender)
                    }
                )
            
        except Exception as e:
            logger.error(f"Error handling mention: {e}")
    
    async def _handle_dm(self, event):
        """Handle direct messages"""
        try:
            await self.event_router.create_event(
                kind='dm',
                src_chat_id=event.chat_id,
                src_msg_id=event.message.id,
                user_id=event.sender_id,
                payload={
                    'message_text': event.message.text,
                    'user_name': self._get_user_name(event.sender)
                }
            )
            
        except Exception as e:
            logger.error(f"Error handling DM: {e}")
    
    def _extract_solana_addresses(self, text: str) -> List[str]:
        """Extract Solana addresses from text"""
        if not text:
            return []
        
        matches = self.solana_pattern.findall(text)
        return list(set(matches))  # Remove duplicates
    
    async def _process_token_addresses(self, event, addresses: List[str], is_edit: bool = False):
        """Process detected token addresses"""
        try:
            for address in addresses:
                # Create token call event
                await self.event_router.create_event(
                    kind='token_call',
                    src_chat_id=event.chat_id,
                    src_msg_id=event.message.id,
                    user_id=event.sender_id,
                    payload={
                        'token_address': address,
                        'message_text': event.message.text,
                        'is_edit': is_edit,
                        'chat_title': getattr(event.chat, 'title', 'Unknown'),
                        'user_name': self._get_user_name(event.sender)
                    }
                )
                
                logger.info(f"Detected token {address[:8]}... in chat {event.chat_id}")
            
        except Exception as e:
            logger.error(f"Error processing token addresses: {e}")
    
    def _get_user_name(self, sender) -> str:
        """Get user name from sender object"""
        if not sender:
            return "Unknown"
        
        if hasattr(sender, 'first_name'):
            name = sender.first_name or ""
            if hasattr(sender, 'last_name') and sender.last_name:
                name += f" {sender.last_name}"
            return name.strip()
        
        if hasattr(sender, 'title'):
            return sender.title or "Unknown"
        
        return "Unknown"
    
    async def send_call_message(self, target_chat_id: int, token_address: str, 
                               additional_info: str = "") -> Dict[str, Any]:
        """Send a call message to a target chat"""
        try:
            if not self.client:
                return {'success': False, 'error': 'Client not initialized'}
            
            # Format call message
            message = f"🚀 CALL: {token_address}"
            if additional_info:
                message += f"\n\n{additional_info}"
            
            # Add scanner bot button if configured
            if settings.scanner_bot_id and settings.scanner_button_text:
                from telethon.tl.types import KeyboardButtonUrl
                from telethon.tl.types import ReplyKeyboardMarkup
                
                # Create inline button (this is simplified - actual implementation may vary)
                message += f"\n\n[{settings.scanner_button_text}](t.me/{settings.scanner_bot_id})"
            
            # Send message
            sent_message = await self.client.send_message(target_chat_id, message)
            
            logger.info(f"Sent call for {token_address[:8]}... to chat {target_chat_id}")
            
            return {
                'success': True,
                'message_id': sent_message.id,
                'chat_id': target_chat_id
            }
            
        except Exception as e:
            logger.error(f"Error sending call message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_worker_info(self) -> Dict[str, Any]:
        """Get worker information"""
        try:
            if self.client:
                me = await self.client.get_me()
                assigned_groups = await self.bot_model.get_assigned_groups(self.userbot_id)
                
                return {
                    'userbot_id': self.userbot_id,
                    'running': self.running,
                    'user_info': {
                        'id': me.id,
                        'first_name': me.first_name,
                        'username': me.username
                    },
                    'assigned_groups': len(assigned_groups),
                    'groups': [{
                        'id': g['id'],
                        'title': g['title'],
                        'chat_id': g['tg_chat_id']
                    } for g in assigned_groups]
                }
            else:
                return {
                    'userbot_id': self.userbot_id,
                    'running': self.running,
                    'error': 'Client not initialized'
                }
                
        except Exception as e:
            logger.error(f"Error getting worker info: {e}")
            return {
                'userbot_id': self.userbot_id,
                'error': str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        try:
            if not self.client:
                return {'healthy': False, 'error': 'Client not initialized'}
            
            if not self.client.is_connected():
                return {'healthy': False, 'error': 'Client not connected'}
            
            # Try to get self info
            me = await self.client.get_me()
            
            return {
                'healthy': True,
                'user_id': me.id,
                'connected': True,
                'running': self.running
            }
            
        except Exception as e:
            logger.error(f"Health check failed for userbot {self.userbot_id}: {e}")
            return {
                'healthy': False,
                'error': str(e)
            }

class UserbotManager:
    """Manager for all userbot workers"""
    
    def __init__(self):
        self.workers: Dict[int, UserbotWorker] = {}
        self.bot_model = BotModel(db)
    
    async def start_all_workers(self):
        """Start all configured userbot workers"""
        try:
            userbots = await self.bot_model.get_active_userbots()
            
            for userbot in userbots:
                if userbot.get('session_string'):
                    await self.start_worker(userbot['id'], userbot['session_string'])
            
            logger.info(f"Started {len(self.workers)} userbot workers")
            
        except Exception as e:
            logger.error(f"Error starting userbot workers: {e}")
    
    async def start_worker(self, userbot_id: int, session_string: str):
        """Start a specific userbot worker"""
        try:
            if userbot_id in self.workers:
                logger.warning(f"Userbot {userbot_id} already running")
                return
            
            worker = UserbotWorker(userbot_id, session_string)
            await worker.start()
            
            self.workers[userbot_id] = worker
            
            logger.info(f"Started userbot worker {userbot_id}")
            
        except Exception as e:
            logger.error(f"Error starting userbot worker {userbot_id}: {e}")
    
    async def stop_worker(self, userbot_id: int):
        """Stop a specific userbot worker"""
        try:
            if userbot_id in self.workers:
                await self.workers[userbot_id].stop()
                del self.workers[userbot_id]
                
                logger.info(f"Stopped userbot worker {userbot_id}")
            
        except Exception as e:
            logger.error(f"Error stopping userbot worker {userbot_id}: {e}")
    
    async def stop_all_workers(self):
        """Stop all userbot workers"""
        try:
            for userbot_id in list(self.workers.keys()):
                await self.stop_worker(userbot_id)
            
            logger.info("Stopped all userbot workers")
            
        except Exception as e:
            logger.error(f"Error stopping userbot workers: {e}")
    
    async def get_worker_status(self) -> Dict[str, Any]:
        """Get status of all workers"""
        try:
            status = {
                'total_workers': len(self.workers),
                'workers': {}
            }
            
            for userbot_id, worker in self.workers.items():
                worker_info = await worker.get_worker_info()
                status['workers'][userbot_id] = worker_info
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            return {'error': str(e)}
    
    async def health_check_all(self) -> Dict[str, Any]:
        """Health check all workers"""
        try:
            results = {}
            
            for userbot_id, worker in self.workers.items():
                results[userbot_id] = await worker.health_check()
            
            healthy_count = sum(1 for r in results.values() if r.get('healthy', False))
            
            return {
                'total_workers': len(self.workers),
                'healthy_workers': healthy_count,
                'unhealthy_workers': len(self.workers) - healthy_count,
                'details': results
            }
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {'error': str(e)}
