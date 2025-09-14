import asyncio
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.config import settings
from app.db import db
from app.models import EventModel

logger = logging.getLogger(__name__)

class EventRouter:
    """Event routing system for handling Telegram events"""
    
    def __init__(self):
        self.event_model = EventModel(db)
        self.running = False
        self._task: Optional[asyncio.Task] = None
        self.mgmt_bot = None
    
    def set_management_bot(self, bot):
        self.mgmt_bot = bot
    
    async def start(self):
        """Start the event routing system"""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._processing_loop())
        logger.info("Event router started")
    
    async def stop(self):
        """Stop the event routing system"""
        if not self.running:
            return
        
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Event router stopped")
    
    async def _processing_loop(self):
        """Main event processing loop"""
        while self.running:
            try:
                await self._process_pending_events()
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Event router error: {e}")
                await asyncio.sleep(10)
    
    async def _process_pending_events(self):
        """Process events that haven't been routed yet"""
        try:
            unrouted_events = await self.event_model.get_unrouted_events()
            
            for event in unrouted_events:
                await self._route_event(event)
                
        except Exception as e:
            logger.error(f"Error processing pending events: {e}")
    
    async def _route_event(self, event: Dict[str, Any]):
        """Route a single event to appropriate channels"""
        try:
            # Convert asyncpg.Record to dict if needed
            if hasattr(event, '_mapping'):
                event = dict(event)
            
            event_kind = event.get('kind')
            user_id = event.get('user_id')
            
            if not event_kind:
                logger.warning(f"Event {event.get('id')} has no kind")
                return
            
            if event_kind == 'token_call':
                await self._handle_token_call_event(event)
            elif event_kind == 'source_token_call':
                await self._handle_token_call_event(event)  # Handle same as token_call
            elif event_kind == 'system':
                await self._handle_system_event(event)
            elif event_kind.startswith('notification_'):
                await self._handle_notification_event(event)
            elif event_kind in ['reply', 'mention', 'dm', 'test']:
                # These event types are no longer supported (notification feature removed)
                # Silently mark as processed without logging warnings
                pass
            else:
                logger.warning(f"Unknown event kind: {event_kind}")
            
            # Mark as processed
            # For system events, use -1 as channel_id to indicate processed but not routed to a specific channel
            current_channel_id = event.get('routed_to_channel_id')
            if event_kind == 'system' and current_channel_id is None:
                channel_id = -1  # Special value for processed system events
            else:
                channel_id = current_channel_id or 0
            await self.event_model.mark_routed(event.get('id', 0), channel_id)
            
        except Exception as e:
            event_id = event.get('id', 'unknown') if isinstance(event, dict) else 'unknown'
            logger.error(f"Error routing event {event_id}: {e}")
    
    async def _handle_notification_event(self, event: Dict[str, Any]):
        """Handle notification events"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            # Get notification channel
            settings = await db.fetchrow("SELECT * FROM notification_settings LIMIT 1")
            if not settings or not settings['notification_channel_id']:
                logger.warning("Notification channel not set, cannot send notification")
                return

            notification_channel_id = settings['notification_channel_id']

            # Format message
            event_type = payload.get('event_type', 'unknown')
            user_id = payload.get('user_id')
            chat_id = payload.get('chat_id')
            chat_title = payload.get('chat_title')
            message_id = payload.get('message_id')
            message_text = payload.get('message_text')
            userbot_username = payload.get('userbot_username')

            if not self.mgmt_bot:
                logger.error("Management bot not set in EventRouter, cannot send notification")
                return
            
            bot = self.mgmt_bot.bot

            # Get user and chat info
            try:
                user = await bot.get_chat(user_id)
                user_name = user.full_name
            except Exception:
                user_name = f"User {user_id}"

            if not chat_title:
                try:
                    chat = await bot.get_chat(chat_id)
                    chat_title = chat.title
                except Exception:
                    chat_title = f"Chat {chat_id}"

            # Format message link
            if str(chat_id).startswith("-100"):
                chat_id_stripped = str(chat_id)[4:]
                message_link = f"https://t.me/c/{chat_id_stripped}/{message_id}"
            else:
                # This will not work for private groups without a username
                message_link = f"https://t.me/c/{abs(chat_id)}/{message_id}"


            text = f"- - - - - - - - - - - - - - - - - -\n"
            text += f"🔔 **New {event_type.title()}**\n"
            text += f"- - - - - - - - - - - - - - - - - -\n"
            text += f"**Userbot:** @{userbot_username}\n"
            text += f"**Group:** {chat_title}\n"
            text += f"**From:** {user_name} (`{user_id}`)\n"
            text += f"**Message:**\n> {message_text}\n\n"
            text += f"[🔗 View Message]({message_link})\n"
            text += f"- - - - - - - - - - - - -- - - - - -"

            await bot.send_message(notification_channel_id, text, parse_mode="Markdown", disable_web_page_preview=True)

        except Exception as e:
            logger.error(f"Error handling notification event: {e}")
    
    
    async def _handle_system_event(self, event: Dict[str, Any]):
        """Handle system events"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            event_type = payload.get('event_type', 'unknown')
            userbot_id = payload.get('userbot_id', 'unknown')
            
            logger.debug(f"Processing system event: {event_type} for userbot {userbot_id}")
            
            # System events are informational - just log them
            if event_type == 'userbot_started':
                logger.info(f"Userbot {userbot_id} started successfully")
            elif event_type == 'userbot_stopped':
                logger.info(f"Userbot {userbot_id} stopped")
            elif event_type == 'connection_error':
                error_msg = payload.get('error', 'Unknown error')
                logger.warning(f"Userbot {userbot_id} connection error: {error_msg}")
            else:
                logger.debug(f"System event {event_type} for userbot {userbot_id}")
                
        except Exception as e:
            logger.error(f"Error handling system event: {e}")
    
    async def _handle_token_call_event(self, event: Dict[str, Any]):
        """Handle token call events"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            token_address = payload.get('token_address')
            
            if not token_address:
                return
            
            # Add token to tracking if not already tracked
            from app.dex import get_dex_service
            dex_service = get_dex_service()
            result = await dex_service.add_token(token_address)
            
            if result['success']:
                logger.info(f"Added token {token_address[:8]}... for tracking from event")
            
        except Exception as e:
            logger.error(f"Error handling token call event: {e}")
    
    async def create_event(self, kind: str, src_chat_id: int, src_msg_id: int, 
                          user_id: int, payload: Dict[str, Any], 
                          token_id: Optional[int] = None) -> Dict[str, Any]:
        """Create a new event"""
        try:
            event = await self.event_model.create_event(
                kind=kind,
                src_chat_id=src_chat_id,
                src_msg_id=src_msg_id,
                user_id=user_id,
                payload=payload,
                token_id=token_id
            )
            
            logger.debug(f"Created {kind} event from chat {src_chat_id}")
            
            return {
                'success': True,
                'event_id': event['id']
            }
            
        except Exception as e:
            logger.error(f"Error creating event: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_event_statistics(self) -> Dict[str, Any]:
        """Get event system statistics"""
        try:
            stats = await self.event_model.get_event_stats()
            
            # Add system info
            unrouted_count = len(await self.event_model.get_unrouted_events())
            
            return {
                'running': self.running,
                'unrouted_events': unrouted_count,
                'event_types': stats
            }
            
        except Exception as e:
            logger.error(f"Error getting event statistics: {e}")
            return {'error': str(e)}
    
    async def replay_events(self, event_kind: Optional[str] = None, hours: int = 24) -> Dict[str, Any]:
        """Replay events from the last N hours"""
        try:
            if event_kind:
                events = await self.event_model.get_events_by_type(event_kind, limit=100)
            else:
                events = await db.fetch("""
                    SELECT * FROM events 
                    WHERE created_at > NOW() - INTERVAL '%s hours'
                    ORDER BY created_at DESC
                    LIMIT 100
                """ % hours)
            
            replayed = 0
            for event in events:
                try:
                    await self._route_event(dict(event))
                    replayed += 1
                except Exception as e:
                    logger.error(f"Error replaying event {event['id']}: {e}")
            
            return {
                'success': True,
                'replayed_count': replayed,
                'total_events': len(events)
            }
            
        except Exception as e:
            logger.error(f"Error replaying events: {e}")
            return {
                'success': False,
                'error': str(e)
            }
