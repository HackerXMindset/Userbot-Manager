"""
Event Processor - Handles event creation and processing for the userbot system
"""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from app.db import db
from app.models import EventModel

logger = logging.getLogger(__name__)


class EventProcessor:
    """Processes and creates events from userbot activities"""
    
    def __init__(self, userbot_id: int):
        self.userbot_id = userbot_id
        self.event_model = EventModel(db)
    
    async def create_token_call_event(self, token_address: str, source_chat_id: int,
                                     target_chat_id: int, source_event) -> Optional[int]:
        """Create a token call event"""
        try:
            from .utils import UserbotUtils
            utils = UserbotUtils()
            
            # Prepare event payload
            payload = {
                'token_address': token_address,
                'source_chat_id': source_chat_id,
                'target_chat_id': target_chat_id,
                'source_title': utils.get_chat_title(source_event.chat),
                'user_name': utils.get_user_name(source_event.sender),
                'message_text': utils.get_message_text(source_event.message),
                'userbot_id': self.userbot_id
            }
            
            # Create event record with required parameters
            event_record = await self.event_model.create_event(
                kind='token_call',
                src_chat_id=source_chat_id,
                src_msg_id=source_event.message.id,
                user_id=source_event.sender_id,
                payload=payload
            )
            
            event_id = event_record['id'] if event_record else None
            logger.debug(f"Created token call event {event_id} for {token_address[:8]}...")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating token call event: {e}")
            return None
    
    async def create_source_token_event(self, token_address: str, source_chat_id: int,
                                       source_event) -> Optional[int]:
        """Create a source token detection event"""
        try:
            from .utils import UserbotUtils
            utils = UserbotUtils()
            
            # Prepare event payload
            payload = {
                'token_address': token_address,
                'source_chat_id': source_chat_id,
                'source_title': utils.get_chat_title(source_event.chat),
                'user_name': utils.get_user_name(source_event.sender),
                'message_text': utils.get_message_text(source_event.message),
                'userbot_id': self.userbot_id,
                'detection_time': datetime.now().isoformat()
            }
            
            # Create event record with required parameters
            event_record = await self.event_model.create_event(
                kind='source_token_call',
                src_chat_id=source_chat_id,
                src_msg_id=source_event.message.id,
                user_id=source_event.sender_id,
                payload=payload
            )
            
            event_id = event_record['id'] if event_record else None
            logger.debug(f"Created source token event {event_id} for {token_address[:8]}...")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating source token event: {e}")
            return None
    
    async def create_system_event(self, event_type: str, data: Dict[str, Any],
                                 user_id: Optional[int] = None) -> Optional[int]:
        """Create a system event"""
        try:
            payload = {
                'event_type': event_type,
                'userbot_id': self.userbot_id,
                'timestamp': datetime.now().isoformat(),
                **data
            }
            
            # For system events, use 0 as dummy chat_id and msg_id since they're not from a specific message
            event_record = await self.event_model.create_event(
                kind='system',
                src_chat_id=0,  # System events don't have a source chat
                src_msg_id=0,   # System events don't have a source message
                user_id=user_id or 0,  # Use 0 if no user_id provided
                payload=payload
            )
            
            event_id = event_record['id'] if event_record else None
            logger.debug(f"Created system event {event_id}: {event_type}")
            return event_id
            
        except Exception as e:
            logger.error(f"Error creating system event: {e}")
            return None
    
    async def process_pending_events(self, limit: int = 50) -> Dict[str, Any]:
        """Process pending events for this userbot"""
        try:
            # Get unprocessed events for this userbot
            events = await db.fetch("""
                SELECT * FROM events
                WHERE payload::json->>'userbot_id' = $1
                AND created_at > NOW() - INTERVAL '1 hour'
                ORDER BY created_at DESC
                LIMIT $2
            """, str(self.userbot_id), limit)
            
            processed = 0
            
            for event in events:
                try:
                    await self._process_single_event(dict(event))
                    processed += 1
                except Exception as event_error:
                    logger.error(f"Error processing event {event['id']}: {event_error}")
            
            return {
                'success': True,
                'processed': processed,
                'total': len(events)
            }
            
        except Exception as e:
            logger.error(f"Error processing pending events: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _process_single_event(self, event: Dict[str, Any]):
        """Process a single event"""
        try:
            event_kind = event.get('kind')
            
            if event_kind == 'token_call':
                await self._process_token_call_event(event)
            elif event_kind == 'source_token_call':
                await self._process_source_token_event(event)
            elif event_kind == 'system':
                await self._process_system_event(event)
            else:
                logger.debug(f"Unknown event kind: {event_kind}")
            
            # Mark event as processed
            await self.event_model.mark_routed(event['id'], self.userbot_id)
            
        except Exception as e:
            logger.error(f"Error processing single event {event.get('id')}: {e}")
    
    async def _process_token_call_event(self, event: Dict[str, Any]):
        """Process a token call event"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            # Log token call processing
            logger.info(f"Processing token call: {payload.get('token_address', 'unknown')[:8]}...")
            
            # Here you could add additional processing logic, such as:
            # - Updating statistics
            # - Triggering alerts
            # - Logging to external systems
            
        except Exception as e:
            logger.error(f"Error processing token call event: {e}")
    
    async def _process_source_token_event(self, event: Dict[str, Any]):
        """Process a source token detection event"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            # Log source token detection
            logger.info(f"Processing source token detection: {payload.get('token_address', 'unknown')[:8]}...")
            
            # Update detection statistics
            await self._update_detection_stats(payload)
            
        except Exception as e:
            logger.error(f"Error processing source token event: {e}")
    
    async def _process_system_event(self, event: Dict[str, Any]):
        """Process a system event"""
        try:
            payload = json.loads(event['payload']) if isinstance(event['payload'], str) else event['payload']
            
            event_type = payload.get('event_type')
            logger.debug(f"Processing system event: {event_type}")
            
            # Handle different system event types
            if event_type == 'userbot_started':
                await self._handle_userbot_started(payload)
            elif event_type == 'userbot_stopped':
                await self._handle_userbot_stopped(payload)
            elif event_type == 'connection_error':
                await self._handle_connection_error(payload)
            
        except Exception as e:
            logger.error(f"Error processing system event: {e}")
    
    async def _update_detection_stats(self, payload: Dict[str, Any]):
        """Update token detection statistics"""
        try:
            token_address = payload.get('token_address')
            if not token_address:
                return
            
            # Update token last seen timestamp
            await db.execute("""
                UPDATE tokens_tracked 
                SET last_checked_at = NOW()
                WHERE address = $1
            """, token_address)
            
        except Exception as e:
            logger.error(f"Error updating detection stats: {e}")
    
    async def _handle_userbot_started(self, payload: Dict[str, Any]):
        """Handle userbot started event"""
        logger.info(f"Userbot {self.userbot_id} started successfully")
    
    async def _handle_userbot_stopped(self, payload: Dict[str, Any]):
        """Handle userbot stopped event"""
        logger.info(f"Userbot {self.userbot_id} stopped")
    
    async def _handle_connection_error(self, payload: Dict[str, Any]):
        """Handle connection error event"""
        error_msg = payload.get('error', 'Unknown error')
        logger.error(f"Userbot {self.userbot_id} connection error: {error_msg}")
    
    async def get_event_stats(self) -> Dict[str, Any]:
        """Get event processing statistics"""
        try:
            stats = await db.fetchrow("""
                SELECT
                    COUNT(*) as total_events,
                    COUNT(*) FILTER (WHERE kind = 'token_call') as token_call_events,
                    COUNT(*) FILTER (WHERE kind = 'source_token_call') as source_token_events,
                    COUNT(*) FILTER (WHERE kind = 'system') as system_events,
                    0 as processed_events,
                    COUNT(*) as pending_events
                FROM events
                WHERE payload::json->>'userbot_id' = $1
                AND created_at > NOW() - INTERVAL '24 hours'
            """, str(self.userbot_id))
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting event stats: {e}")
            return {}
    
    async def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent events for this userbot"""
        try:
            events = await db.fetch("""
                SELECT * FROM events 
                WHERE payload::json->>'userbot_id' = $1
                ORDER BY created_at DESC
                LIMIT $2
            """, str(self.userbot_id), limit)
            
            return [dict(event) for event in events]
            
        except Exception as e:
            logger.error(f"Error getting recent events: {e}")
            return []
    
    async def cleanup_old_events(self, days_old: int = 7) -> int:
        """Clean up old processed events"""
        try:
            deleted_count = await db.fetchval("""
                DELETE FROM events
                WHERE payload::json->>'userbot_id' = $1
                AND created_at < NOW() - INTERVAL $2
                RETURNING COUNT(*)
            """, str(self.userbot_id), f"{days_old} days")
            
            if deleted_count:
                logger.info(f"Cleaned up {deleted_count} old events for userbot {self.userbot_id}")
            
            return deleted_count or 0
            
        except Exception as e:
            logger.error(f"Error cleaning up old events: {e}")
            return 0