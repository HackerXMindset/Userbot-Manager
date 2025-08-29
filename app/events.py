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
            event_kind = event['kind']
            
            if event_kind == 'reply':
                await self._handle_reply_event(event)
            elif event_kind == 'mention':
                await self._handle_mention_event(event)
            elif event_kind == 'dm':
                await self._handle_dm_event(event)
            elif event_kind == 'token_call':
                await self._handle_token_call_event(event)
            else:
                logger.warning(f"Unknown event kind: {event_kind}")
            
            # Mark as processed
            await self.event_model.mark_routed(event['id'], event.get('routed_to_channel_id', 0))
            
        except Exception as e:
            logger.error(f"Error routing event {event['id']}: {e}")
    
    async def _handle_reply_event(self, event: Dict[str, Any]):
        """Handle reply events"""
        try:
            # Get notification channel
            notif_channel = await db.fetchval(
                "SELECT value FROM settings WHERE key = 'default_notif_channel_id'"
            )
            
            if not notif_channel:
                return
            
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            # Format message
            message = (
                f"💬 <b>REPLY DETECTED</b>\n\n"
                f"Chat: {payload.get('chat_title', 'Unknown')}\n"
                f"User: {payload.get('user_name', 'Unknown')}\n"
                f"Reply to: {payload.get('reply_to_text', 'Unknown')[:100]}...\n\n"
                f"Message: {payload.get('message_text', '')[:200]}...\n\n"
                f"Time: {event['created_at'].strftime('%H:%M:%S')}"
            )
            
            # TODO: Send via notification bot
            logger.debug(f"Reply detected in {payload.get('chat_title', 'Unknown')} from {payload.get('user_name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Error handling reply event: {e}")
    
    async def _handle_mention_event(self, event: Dict[str, Any]):
        """Handle mention events"""
        try:
            # Get notification channel
            notif_channel = await db.fetchval(
                "SELECT value FROM settings WHERE key = 'default_notif_channel_id'"
            )
            
            if not notif_channel:
                return
            
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            # Format message
            message = (
                f"📢 <b>MENTION DETECTED</b>\n\n"
                f"Chat: {payload.get('chat_title', 'Unknown')}\n"
                f"User: {payload.get('user_name', 'Unknown')}\n\n"
                f"Message: {payload.get('message_text', '')[:200]}...\n\n"
                f"Time: {event['created_at'].strftime('%H:%M:%S')}"
            )
            
            # TODO: Send via notification bot
            logger.debug(f"Mention detected in {payload.get('chat_title', 'Unknown')} from {payload.get('user_name', 'Unknown')}")
            
        except Exception as e:
            logger.error(f"Error handling mention event: {e}")
    
    async def _handle_dm_event(self, event: Dict[str, Any]):
        """Handle DM events"""
        try:
            # Get notification channel
            notif_channel = await db.fetchval(
                "SELECT value FROM settings WHERE key = 'default_notif_channel_id'"
            )
            
            if not notif_channel:
                return
            
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            # Format message
            message = (
                f"💌 <b>DIRECT MESSAGE</b>\n\n"
                f"From: {payload.get('user_name', 'Unknown')}\n"
                f"User ID: <code>{event['user_id']}</code>\n\n"
                f"Message: {payload.get('message_text', '')[:300]}...\n\n"
                f"Time: {event['created_at'].strftime('%H:%M:%S')}"
            )
            
            # TODO: Send via notification bot
            logger.debug(f"DM received from {payload.get('user_name', 'Unknown')} (ID: {event['user_id']})")
            
        except Exception as e:
            logger.error(f"Error handling DM event: {e}")
    
    async def _handle_token_call_event(self, event: Dict[str, Any]):
        """Handle token call events"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            token_address = payload.get('token_address')
            
            if not token_address:
                return
            
            # Add token to tracking if not already tracked
            from app.dex import DexScreenerService
            dex_service = DexScreenerService()
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
