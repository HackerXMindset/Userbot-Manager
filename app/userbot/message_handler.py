"""
Message Handler - Handles message processing and event routing
"""

import logging
from typing import Dict, Any, List, Optional
from telethon import events

from app.db import db
from app.models import BotModel
from .token_monitor import TokenMonitor
from .call_executor import CallExecutor
from .source_manager import SourceManager
from .utils import UserbotUtils

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles incoming messages and routes them appropriately"""
    
    def __init__(self, userbot_id: int, session_manager):
        self.userbot_id = userbot_id
        self.session_manager = session_manager
        self.bot_model = BotModel(db)
        
        # Initialize components
        self.token_monitor = TokenMonitor(userbot_id)
        self.call_executor = CallExecutor(userbot_id, session_manager)
        self.source_manager = SourceManager(userbot_id)
        self.utils = UserbotUtils()
    
    async def setup_event_handlers(self, assigned_groups: List[Dict[str, Any]]):
        """Setup event handlers for global sources system"""
        client = self.session_manager.get_client()
        if not client:
            logger.error("Cannot setup handlers - client not available")
            return
        
        # Get group IDs for outgoing message tracking
        group_ids = [g['tg_chat_id'] for g in assigned_groups]
        
        # Get ALL sources with routing (not just ones for our groups)
        # This allows monitoring all sources that might route to any group
        sources_with_routing = await self.source_manager.get_sources_with_routing()
        source_chat_ids = [s['source_chat_id'] for s in sources_with_routing if s['target_groups']]
        
        # Store assigned groups for reference
        self.assigned_groups = assigned_groups
        
        # Setup global source message monitoring
        if source_chat_ids:
            @client.on(events.NewMessage(chats=source_chat_ids))
            async def handle_source_message(event):
                await self._handle_source_message(event)
            
            @client.on(events.MessageEdited(chats=source_chat_ids))
            async def handle_source_edited(event):
                await self._handle_source_message(event, is_edit=True)
            
            logger.info(f"Setup global monitoring for {len(source_chat_ids)} source chats")
        
        # Setup outgoing message tracking for reply detection
        @client.on(events.NewMessage(chats=group_ids, outgoing=True))
        async def track_outgoing_messages(event):
            await self._track_outgoing_message(event)
        
        logger.info(f"Setup handlers for {len(group_ids)} groups and {len(source_chat_ids)} global source chats")
    
    async def _handle_source_message(self, event, is_edit: bool = False):
        """Handle messages from source chats - extract tokens and route to targets"""
        try:
            # Validate source permissions
            permission_check = await self.source_manager.validate_source_permissions(event)
            
            if not permission_check['allowed']:
                logger.debug(f"Source message rejected: {permission_check['reason']}")
                return
            
            source = permission_check['source']
            
            # Process message for tokens
            addresses = await self.token_monitor.process_source_message(event, event.chat_id)
            
            if addresses:
                # Get all target groups for this source using routing rules
                target_groups = await self.source_manager.get_target_groups_for_source(event.chat_id)
                
                if not target_groups:
                    logger.warning(f"No target groups found for source {event.chat_id}")
                    return
                
                # Forward tokens to all target groups
                total_sent = 0
                total_failed = 0
                
                for target_group in target_groups:
                    group_sent = 0
                    group_failed = 0
                    
                    # Send each token to this target group
                    for address in addresses:
                        try:
                            # Get source info for the call
                            source_info = f"From {source.get('name') or source.get('title') or event.chat_id}"
                            additional_info = self.utils.get_message_text(event.message) if hasattr(event, 'message') else ""
                            
                            # Send call message to this target group
                            result = await self.call_executor.send_call_message(
                                target_chat_id=target_group['tg_chat_id'],
                                token_address=address,
                                additional_info=additional_info,
                                source_info=source_info
                            )
                            
                            if result['success']:
                                group_sent += 1
                                total_sent += 1
                            else:
                                group_failed += 1
                                total_failed += 1
                                logger.warning(f"Failed to send {address[:8]}... to {target_group['title'] or target_group['tg_chat_id']}: {result.get('error')}")
                                
                        except Exception as token_error:
                            group_failed += 1
                            total_failed += 1
                            logger.error(f"Error sending token {address[:8]}... to target {target_group['tg_chat_id']}: {token_error}")
                    
                    if group_sent > 0:
                        logger.debug(f"Sent {group_sent} tokens to {target_group['title'] or target_group['tg_chat_id']}")
                    if group_failed > 0:
                        logger.warning(f"Failed {group_failed} tokens to {target_group['title'] or target_group['tg_chat_id']}")
                
                logger.info(f"Forwarded {len(addresses)} tokens to {len(target_groups)} target groups: {total_sent} sent, {total_failed} failed")
            
            # Update bot last seen
            await self.bot_model.update_last_seen(self.userbot_id)
            
        except Exception as e:
            logger.error(f"Error handling source message: {e}")
    
    async def _track_outgoing_message(self, event):
        """Track outgoing messages for reply detection"""
        try:
            # Let the call executor handle message tracking
            self.call_executor.message_tracker.track_message(event.chat_id, event.message.id)
            
            logger.debug(f"Tracked outgoing message: chat={event.chat_id}, msg_id={event.message.id}")
            
        except Exception as e:
            logger.error(f"Error tracking outgoing message: {e}")
    
    async def send_manual_call(self, target_chat_id: int, token_address: str, 
                             source_info: str = "Manual call") -> Dict[str, Any]:
        """Send a manual call message"""
        try:
            return await self.call_executor.send_call_message(
                target_chat_id=target_chat_id,
                token_address=token_address,
                source_info=source_info
            )
        except Exception as e:
            logger.error(f"Error sending manual call: {e}")
            return {'success': False, 'error': str(e)}
    
    async def process_scheduled_calls(self) -> Dict[str, Any]:
        """Process any scheduled calls for this userbot"""
        try:
            # Get pending calls for this userbot
            calls = await db.fetch("""
                SELECT c.*, t.address, ta.dest_chat_id
                FROM calls c
                JOIN tokens_tracked t ON t.id = c.token_id
                JOIN targets ta ON ta.id = c.target_id
                WHERE c.userbot_id = $1
                AND c.status = 'queued'
                AND c.scheduled_at <= NOW()
                ORDER BY c.scheduled_at
                LIMIT 10
            """, self.userbot_id)
            
            processed = 0
            failed = 0
            
            for call in calls:
                try:
                    # Send the call
                    result = await self.call_executor.send_call_message(
                        target_chat_id=call['dest_chat_id'],
                        token_address=call['address'],
                        source_info="Scheduled call"
                    )
                    
                    if result['success']:
                        # Mark as sent
                        await db.execute("""
                            UPDATE calls 
                            SET status = 'sent', sent_at = NOW()
                            WHERE id = $1
                        """, call['id'])
                        processed += 1
                        
                        logger.info(f"Processed scheduled call {call['id']}")
                    else:
                        # Mark as failed
                        await db.execute("""
                            UPDATE calls 
                            SET status = 'failed', sent_at = NOW()
                            WHERE id = $1
                        """, call['id'])
                        failed += 1
                        
                        logger.error(f"Failed scheduled call {call['id']}: {result.get('error')}")
                        
                except Exception as call_error:
                    logger.error(f"Error processing scheduled call {call['id']}: {call_error}")
                    failed += 1
            
            return {
                'success': True,
                'processed': processed,
                'failed': failed,
                'total': len(calls)
            }
            
        except Exception as e:
            logger.error(f"Error processing scheduled calls: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_message_stats(self) -> Dict[str, Any]:
        """Get message handling statistics"""
        try:
            # Combine stats from different components
            token_stats = await self.token_monitor.get_token_stats()
            call_stats = await self.call_executor.get_call_stats()
            source_stats = await self.source_manager.get_source_stats()
            executor_stats = self.call_executor.get_executor_stats()
            
            return {
                'userbot_id': self.userbot_id,
                'tokens': token_stats,
                'calls': call_stats,
                'sources': source_stats,
                'executor': executor_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting message stats: {e}")
            return {'userbot_id': self.userbot_id, 'error': str(e)}
    
    async def cleanup_old_data(self, days_old: int = 30) -> Dict[str, Any]:
        """Clean up old message-related data"""
        try:
            # Clean up tokens
            tokens_cleaned = await self.token_monitor.cleanup_old_tokens(days_old)
            
            # Clean up sources (if implemented)
            sources_cleaned = await self.source_manager.cleanup_inactive_sources(days_old)
            
            return {
                'success': True,
                'tokens_cleaned': tokens_cleaned,
                'sources_cleaned': sources_cleaned
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_components(self) -> Dict[str, Any]:
        """Get references to internal components for advanced usage"""
        return {
            'token_monitor': self.token_monitor,
            'call_executor': self.call_executor,
            'source_manager': self.source_manager,
            'utils': self.utils
        }