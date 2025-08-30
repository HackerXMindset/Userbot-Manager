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
from app.models.source_chat import SourceChatModel

logger = logging.getLogger(__name__)

class UserbotWorker:
    """Userbot worker for monitoring groups and sending calls"""
    
    def __init__(self, userbot_id: int, session_string: str):
        self.userbot_id = userbot_id
        self.session_string = session_string
        self.client: Optional[TelegramClient] = None
        self.running = False
        
        # Models
        self.bot_model = BotModel(db)
        self.group_model = GroupModel(db)
        self.source_model = SourceChatModel(db)
        
        # Track sent messages to detect replies to our messages
        self.sent_message_ids = set()  # Store (chat_id, message_id) pairs
        self.userbot_username = None   # Store our username for mention detection
        self.userbot_user_id = None    # Store our user ID
        
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
            
            # Get userbot info for mention/reply detection
            me = await self.client.get_me()
            self.userbot_user_id = me.id
            self.userbot_username = me.username
            
            logger.info(f"Userbot initialized: ID={self.userbot_user_id}, Username=@{self.userbot_username}")
            
            # Get assigned groups
            assigned_groups = await self.bot_model.get_assigned_groups(self.userbot_id)
            
            # Set up event handlers
            await self._setup_event_handlers(assigned_groups)
            
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
    
    async def _setup_event_handlers(self, groups: List[Dict[str, Any]]):
        """Setup event handlers for assigned groups and their source chats"""
        if not self.client:
            return
        
        # Get group IDs
        group_ids = [g['tg_chat_id'] for g in groups]
        
        # Get all source chats for these groups
        sources = await self.source_model.get_sources_for_userbot([g['id'] for g in groups])
        source_chat_ids = [s['source_chat_id'] for s in sources] if sources else []
        
        # Monitor source chats for token addresses
        if source_chat_ids:
            @self.client.on(events.NewMessage(chats=source_chat_ids))
            async def handle_source_message(event):
                await self._handle_source_message(event)
            
            @self.client.on(events.MessageEdited(chats=source_chat_ids))
            async def handle_source_edited(event):
                await self._handle_source_message(event, is_edit=True)
        
        # Monitor assigned groups for replies and mentions (removed notification features)
        # This section has been removed - no longer monitoring for replies/mentions
        
        # Handle outgoing messages to track them for reply detection
        @self.client.on(events.NewMessage(chats=group_ids, outgoing=True))
        async def track_outgoing_messages(event):
            # Track all messages we send for reply detection
            self.sent_message_ids.add((event.chat_id, event.message.id))
            logger.debug(f"Tracked outgoing message: chat={event.chat_id}, msg_id={event.message.id}")
            
            # Keep only recent messages (last 1000) to prevent memory bloat
            if len(self.sent_message_ids) > 1000:
                oldest_messages = list(self.sent_message_ids)[:100]
                for msg in oldest_messages:
                    self.sent_message_ids.discard(msg)
        
        # Handle DMs (private messages) - removed notification features
        # This section has been removed - no longer monitoring DMs for notifications
    
    
    
    async def _handle_source_message(self, event, is_edit: bool = False):
        """Handle messages from source chats - extract tokens and forward to targets"""
        try:
            # Check if user is allowed to trigger forwards (for groups)
            is_allowed = await self.source_model.is_user_allowed(event.chat_id, event.sender_id)
            
            if not is_allowed:
                logger.debug(f"User {event.sender_id} not allowed to trigger from source {event.chat_id}")
                return
            
            message = event.message
            
            # Extract Solana addresses
            solana_addresses = self._extract_solana_addresses(message.text or "")
            
            if solana_addresses:
                # Get source chat info
                source = await self.source_model.get_source_by_chat_id(event.chat_id)
                if source:
                    # Forward to group's targets
                    await self._forward_tokens_to_targets(source['group_id'], solana_addresses, event)
            
            # Update last seen
            await self.bot_model.update_last_seen(self.userbot_id)
            
        except Exception as e:
            logger.error(f"Error handling source message: {e}")
    
    async def _forward_tokens_to_targets(self, group_id: int, addresses: List[str], source_event):
        """Forward token addresses from source to group's target chats"""
        try:
            # Get group's targets
            targets = await self.group_model.get_targets(group_id)
            
            if not targets:
                logger.debug(f"No targets configured for group {group_id}")
                return
            
            # Get group info for call creation
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return
            
            for address in addresses:
                # Log the token detection
                logger.info(f"Token {address[:8]}... detected from source, forwarding to {len(targets)} targets")
                
                # Removed event creation for notification system
                
                # Add token to tracking if not already tracked
                from app.dex import DexScreenerService
                dex_service = DexScreenerService()
                await dex_service.add_token(address)
                
                # Send to each target chat
                for target in targets:
                    try:
                        # Get source info for the message
                        source_title = getattr(source_event.chat, 'title', f"Chat {source_event.chat_id}")
                        user_name = self._get_user_name(source_event.sender)
                        source_info = f"{source_title} ({user_name})"
                        
                        # Create formatted call message
                        call_result = await self.send_call_message(
                            target_chat_id=target['dest_chat_id'],
                            token_address=address,
                            additional_info=self._get_message_text(source_event.message),
                            source_info=source_info
                        )
                        
                        if call_result['success']:
                            # Get or create token record first
                            token_record = await db.fetchrow("""
                                INSERT INTO tokens_tracked (address) 
                                VALUES ($1) 
                                ON CONFLICT (address) DO UPDATE SET last_checked_at = NOW()
                                RETURNING id
                            """, address)
                            
                            # Get target record
                            target_record = await db.fetchrow("""
                                SELECT id FROM targets WHERE group_id = $1 AND dest_chat_id = $2
                            """, group_id, target['dest_chat_id'])
                            
                            # Log successful call
                            await db.execute("""
                                INSERT INTO calls (group_id, token_id, target_id, userbot_id, 
                                                 scheduled_at, sent_at, status)
                                VALUES ($1, $2, $3, $4, NOW(), NOW(), 'sent')
                            """, group_id, token_record['id'], 
                                target_record['id'] if target_record else None, 
                                self.userbot_id)
                            
                            logger.info(f"Successfully sent {address[:8]}... to target {target['dest_chat_id']}")
                        else:
                            logger.error(f"Failed to send to target {target['dest_chat_id']}: {call_result.get('error')}")
                            
                    except Exception as target_error:
                        logger.error(f"Error sending to target {target['dest_chat_id']}: {target_error}")
                
        except Exception as e:
            logger.error(f"Error forwarding tokens to targets: {e}")
    
    
    
    def _extract_solana_addresses(self, text: str) -> List[str]:
        """Extract Solana addresses from text"""
        if not text:
            return []
        
        matches = self.solana_pattern.findall(text)
        return list(set(matches))  # Remove duplicates
    
    def _get_message_text(self, message) -> str:
        """Safely get message text as string"""
        if hasattr(message, 'text') and message.text:
            return str(message.text)
        return ""
    
    def _get_user_name(self, sender) -> str:
        """Get user name from sender object"""
        if not sender:
            return "Unknown"
        
        if hasattr(sender, 'first_name'):
            name = sender.first_name or ""
            if hasattr(sender, 'last_name') and sender.last_name:
                name += f" {sender.last_name}"
            return name.strip() or "Unknown"
        
        if hasattr(sender, 'title'):
            return sender.title or "Unknown"
        
        if hasattr(sender, 'username') and sender.username:
            return f"@{sender.username}"
        
        return "Unknown"
    
    async def send_call_message(self, target_chat_id: int, token_address: str, 
                               additional_info: str = "", source_info: str = "") -> Dict[str, Any]:
        """Send a call message to a target chat"""
        try:
            if not self.client:
                return {'success': False, 'error': 'Client not initialized'}
            
            # Send only the contract address, no formatting
            message = token_address
            
            # Send message
            sent_message = await self.client.send_message(target_chat_id, message)
            
            # Track sent message for reply detection
            self.sent_message_ids.add((target_chat_id, sent_message.id))
            logger.debug(f"Tracked sent call message: chat={target_chat_id}, msg_id={sent_message.id}")
            
            # Keep only recent messages (last 1000) to prevent memory bloat
            if len(self.sent_message_ids) > 1000:
                oldest_messages = list(self.sent_message_ids)[:100]
                for msg in oldest_messages:
                    self.sent_message_ids.discard(msg)
            
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
