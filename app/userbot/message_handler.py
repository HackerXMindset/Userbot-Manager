"""
Message Handler - Handles message processing and event routing
"""

import logging
import time
import traceback
from typing import Dict, Any, List, Optional
from telethon import events

from app.db import db
from app.models import BotModel, GroupModel, ScheduleModel, PnlForwardingRuleModel
from .token_monitor import TokenMonitor
from .call_executor import CallExecutor
from .source_manager import SourceManager
from .utils import UserbotUtils
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

logger = logging.getLogger(__name__)

# Set detailed logging for message handler PNL operations
logging.getLogger(__name__).setLevel(logging.DEBUG)


class MessageHandler:
    """Handles incoming messages and routes them appropriately"""
    
    def __init__(self, userbot_id: int, session_manager):
        self.userbot_id = userbot_id
        self.session_manager = session_manager
        self.bot_model = BotModel(db)
        self.group_model = GroupModel(db)
        self.schedule_model = ScheduleModel(db)
        self.cache = {}
        self.cache_time = {}
        
        self.pnl_model = PnlForwardingRuleModel(db)

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

        pnl_rules = await self.pnl_model.get_all_with_details()
        pnl_source_chat_ids = list(set(rule['source_group_chat_id'] for rule in pnl_rules))
        
        logger.info(f"Found {len(pnl_rules)} PNL rules, monitoring {len(pnl_source_chat_ids)} source chats")
        logger.debug(f"PNL source chat IDs: {pnl_source_chat_ids}")

        if pnl_source_chat_ids:
            @client.on(events.NewMessage(chats=pnl_source_chat_ids, pattern=r'/pnl.*'))
            async def handle_pnl_command(event):
                await self._handle_pnl_command(event)
            
            @client.on(events.NewMessage(chats=pnl_source_chat_ids))
            async def handle_pnl_replies(event):
                await self._handle_potential_pnl_reply(event)
    
    def is_fresh(self, key, seconds=600):
        """Check if cache entry is fresh (default 10 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    async def _can_group_accept_calls(self, tg_chat_id: int) -> bool:
        """Check if group can accept calls at current time/day"""
        try:
            # Get current time info for cache key
            from app.config import settings
            now = settings.get_local_time()
            current_day = now.weekday() + 1  # Monday = 1
            current_hour = now.hour
            
            # Check cache first
            cache_key = f"schedule_{tg_chat_id}_{current_day}_{current_hour}"
            if self.is_fresh(cache_key):
                return self.cache[cache_key]
            
            # Get group record
            group = await self.group_model.get_by_chat_id(tg_chat_id)
            if not group or not group['enabled']:
                result = False
                self.cache[cache_key] = result
                self.cache_time[cache_key] = time.time()
                return result
            
            current_time = now.time()
            
            # Check if group has any schedules at all
            all_schedules = await self.schedule_model.get_by_group(group['id'])
            
            # If no schedules defined, allow by default (schedules are optional)
            if not all_schedules:
                result = True
            else:
                # Group has schedules - check if any are currently active
                active_schedules = await self.schedule_model.get_active_schedules(current_day, current_time)
                result = False
                for schedule in active_schedules:
                    if schedule['tg_chat_id'] == tg_chat_id:
                        result = True
                        break
            
            # Cache result for 10 minutes
            self.cache[cache_key] = result
            self.cache_time[cache_key] = time.time()
            return result
            
        except Exception as e:
            logger.error(f"Error checking schedule for group {tg_chat_id}: {e}")
            # Default to allow if schedule check fails
            return True
    
    async def _handle_source_message(self, event, is_edit: bool = False):
        """Handle messages from source chats - extract tokens and route to targets"""
        try:
            # Validate source permissions
            permission_check = await self.source_manager.validate_source_permissions(event)
            
            if not permission_check['allowed']:
                logger.debug(f"Source message rejected: {permission_check['reason']}")
                return
            
            source = permission_check['source']
            
            # Get all target groups for this source using routing rules
            target_groups = await self.source_manager.get_target_groups_for_source(event.chat_id)
            
            if not target_groups:
                logger.warning(f"No target groups found for source {event.chat_id}")
                return
            
            # Process message for tokens
            addresses = await self.token_monitor.process_source_message(event, event.chat_id, target_groups)
            
            if addresses:
                
                # Forward tokens to all target groups
                total_sent = 0
                total_failed = 0
                
                for target_group in target_groups:
                    # Check if group can accept calls at current time/day
                    if not await self._can_group_accept_calls(target_group['tg_chat_id']):
                        logger.info(f"Skipping group {target_group['tg_chat_id']} - outside schedule window")
                        continue
                    
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

    async def _get_cached_pnl_rules(self, group_id: int, seconds: int = 60) -> List[Dict[str, Any]]:
        """Get PNL forwarding rules for a group, with caching."""
        cache_key = f"pnl_rules_{group_id}"
        if self.is_fresh(cache_key, seconds=seconds):
            return self.cache[cache_key]

        rules = await self.pnl_model.get_enabled_rules_for_group(group_id)
        self.cache[cache_key] = rules
        self.cache_time[cache_key] = time.time()
        return rules

    async def _handle_pnl_command(self, event):
        """Handle /pnl commands in monitored source groups with comprehensive debugging."""
        try:
            logger.debug(f"[MessageHandler] PNL command received: chat_id={event.chat_id}, "
                        f"sender_id={event.sender_id}, message_id={event.message.id}, "
                        f"text='{event.message.text[:100]}'")
            
            group = await self.group_model.get_by_chat_id(event.chat_id)
            if not group:
                logger.debug(f"[MessageHandler] No group found for chat {event.chat_id}, ignoring /pnl command")
                return

            rules = await self._get_cached_pnl_rules(group['id'])
            logger.debug(f"[MessageHandler] Found {len(rules)} enabled rules for chat {event.chat_id}")
            
            if not rules:
                logger.debug(f"[MessageHandler] No rules found for chat {event.chat_id}, ignoring /pnl command")
                return

            for rule in rules:
                logger.debug(f"[MessageHandler] Processing rule {rule['id']} for /pnl command")
                allowed_users = rule.get('allowed_pnl_command_user_ids', [])
                logger.debug(f"[MessageHandler] Rule {rule['id']} allowed users: {allowed_users}")
                
                if not allowed_users or event.sender_id in allowed_users:
                    # Only the designated userbot should track the command
                    if self.userbot_id != rule.get('forwarding_userbot_id'):
                        logger.debug(f"[MessageHandler] Skipping /pnl tracking for rule {rule['id']}: not the designated userbot")
                        continue

                    logger.info(f"[MessageHandler] User {event.sender_id} authorized for rule {rule['id']}, tracking /pnl command")
                    
                    try:
                        # This command is from an authorized user, track it.
                        await db.execute("""
                            INSERT INTO pnl_tracked_messages (rule_id, original_message_id, chat_id, sender_id, status)
                            VALUES ($1, $2, $3, $4, 'tracking')
                            ON CONFLICT (original_message_id, chat_id) DO NOTHING
                        """, rule['id'], event.message.id, event.chat_id, event.sender_id)
                        
                        logger.info(f"[MessageHandler] Successfully tracking /pnl command: "
                                   f"message_id={event.message.id}, rule_id={rule['id']}, "
                                   f"chat_id={event.chat_id}, sender_id={event.sender_id}")
                    except Exception as db_err:
                        logger.error(f"[MessageHandler] Database error tracking /pnl command: {db_err}")
                        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
                else:
                    logger.debug(f"[MessageHandler] User {event.sender_id} not authorized for rule {rule['id']} "
                               f"(allowed: {allowed_users})")

        except Exception as e:
            logger.error(f"[MessageHandler] Error handling /pnl command: {e}")
            logger.error(f"[MessageHandler] Event details: chat_id={event.chat_id}, "
                        f"sender_id={event.sender_id}, message_id={event.message.id}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")

    async def _handle_potential_pnl_reply(self, event):
        """Handle potential replies to /pnl commands in real-time."""
        try:
            if not event.message.reply_to_msg_id:
                return  # Not a reply
            
            logger.debug(f"[MessageHandler] Potential PNL reply: chat_id={event.chat_id}, "
                        f"sender_id={event.sender_id}, reply_to={event.message.reply_to_msg_id}")
            
            # Check if this is a reply to a tracked /pnl message
            tracked_messages = await db.fetch("""
                SELECT * FROM pnl_tracked_messages 
                WHERE original_message_id = $1 AND chat_id = $2 AND status = 'tracking'
                AND created_at > NOW() - INTERVAL '3 minutes'
            """, event.message.reply_to_msg_id, event.chat_id)
            
            if not tracked_messages:
                return  # Not replying to a tracked /pnl message
            
            logger.debug(f"[MessageHandler] Found {len(tracked_messages)} tracked PNL messages for reply")
            
            for tracked in tracked_messages:
                # Get the rule
                rule = await self.pnl_model.get_by_id(tracked['rule_id'])
                if not rule or not rule['enabled']:
                    continue
                
                # Only designated userbot should attempt forwarding
                if self.userbot_id != rule.get('forwarding_userbot_id'):
                    logger.debug(f"[MessageHandler] Userbot {self.userbot_id} not designated for rule {rule['id']} (need {rule.get('forwarding_userbot_id')})")
                    continue
                
                # Filter out flex generation messages
                if "💪 Generating flex.." in event.message.text:
                    logger.debug(f"[MessageHandler] Skipping flex generation message {event.message.id}")
                    continue
                
                allowed_reply_users = rule.get('allowed_reply_user_ids', [])
                
                if not allowed_reply_users or event.sender_id in allowed_reply_users:
                    logger.info(f"[MessageHandler] Valid PNL reply detected from user {event.sender_id}, forwarding immediately for rule {rule['id']}")
                    
                    # Forward the message using the designated forwarding userbot
                    success = await self._forward_pnl_reply(rule, event.message)
                    if success:
                        logger.info(f"[MessageHandler] Successfully forwarded PNL reply {event.message.id} for tracking {tracked['id']}")
                    else:
                        logger.error(f"[MessageHandler] Failed to forward PNL reply {event.message.id} for tracking {tracked['id']}")
                        
        except Exception as e:
            logger.error(f"[MessageHandler] Error handling potential PNL reply: {e}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")

    async def _forward_pnl_reply(self, rule: dict, message) -> bool:
        """Forward a PNL reply message to the destination channel."""
        try:
            # Check if this userbot is the designated forwarding userbot
            if self.userbot_id != rule.get('forwarding_userbot_id'):
                logger.debug(f"[MessageHandler] Userbot {self.userbot_id} not designated for forwarding (need {rule.get('forwarding_userbot_id')})")
                return False
            
            client = self.session_manager.get_client()
            if not client:
                logger.error("[MessageHandler] No client available for PNL forwarding")
                return False
            
            logger.debug(f"[MessageHandler] Forwarding PNL reply message {message.id} to channel {rule['destination_channel_id']}")
            
            # Resolve entity using same pattern as call_executor.py
            entity = await self._resolve_entity_safely(client, rule['destination_channel_id'])
            
            await client.forward_messages(
                entity=entity,
                messages=message
            )
            
            logger.info(f"[MessageHandler] Successfully forwarded PNL reply to channel {rule['destination_channel_id']}")
            return True
            
        except Exception as e:
            logger.error(f"[MessageHandler] Error forwarding PNL reply: {e}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
            return False

    async def _resolve_entity_safely(self, client, target_chat_id: int):
        """Safely resolve entity with fallback strategies"""
        try:
            # First try: Direct entity resolution
            entity = await client.get_entity(target_chat_id)
            return entity
        except Exception as resolve_error:
            # Log as debug since this isn't a real error if sending still works
            logger.debug(f"Entity resolution failed for {target_chat_id}: {resolve_error}")
            
            # Fallback: Construct peer directly based on chat ID pattern
            try:
                if target_chat_id < 0:
                    # Supergroup/channel (starts with -100)
                    if str(target_chat_id).startswith('-100'):
                        channel_id = abs(target_chat_id) - 1000000000000
                        return PeerChannel(channel_id)
                    # Regular group (negative but not starting with -100)
                    else:
                        chat_id = abs(target_chat_id)
                        return PeerChat(chat_id)
                else:
                    # User
                    return PeerUser(target_chat_id)
            except Exception as peer_error:
                logger.debug(f"Peer construction failed for {target_chat_id}: {peer_error}")
                # Return original ID as final fallback
                return target_chat_id
    
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