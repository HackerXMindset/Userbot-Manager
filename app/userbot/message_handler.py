
"""
Message Handler - Handles message processing and event routing
"""

import logging
import time
import traceback
import json
from typing import Dict, Any, List, Optional
from telethon import events

from app.db import db
from app.models import BotModel, GroupModel, ScheduleModel, PnlForwardingRuleModel, CommandForwardingRuleModel, CommandTrackedMessageModel, AutoButtonClickRuleModel, CuratedAlphaRuleModel, CuratedAlphaTokenStateModel
from app.models.source_chat import SourceChatModel
from app.models.call_queue import CallQueueModel
from .token_monitor import TokenMonitor
from .call_executor import CallExecutor
from .source_manager import SourceManager
from .utils import UserbotUtils
from .notification_handler import NotificationHandler
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

logger = logging.getLogger(__name__)

# Set detailed logging for message handler operations
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
        self.cmd_fwd_model = CommandForwardingRuleModel(db)
        self.cmd_tracked_model = CommandTrackedMessageModel(db)
        self.rule_model = AutoButtonClickRuleModel(db)
        self.source_model = SourceChatModel(db)
        self.call_queue_model = CallQueueModel(db)
        self.curated_alpha_rule_model = CuratedAlphaRuleModel(db)
        self.curated_alpha_token_state_model = CuratedAlphaTokenStateModel(db)

        # Initialize components
        self.token_monitor = TokenMonitor(userbot_id)
        self.call_executor = CallExecutor(userbot_id, session_manager)
        self.source_manager = SourceManager(userbot_id)
        self.notification_handler = NotificationHandler(userbot_id, session_manager)
        self.utils = UserbotUtils()
    
    async def setup_event_handlers(self, assigned_groups: List[Dict[str, Any]]):
        """Setup event handlers for global sources system"""
        client = self.session_manager.get_client()
        if not client:
            logger.error("Cannot setup handlers - client not available")
            return

        @client.on(events.NewMessage(incoming=True))
        async def handle_all_incoming(event):
            await self._process_incoming_event(event)

        @client.on(events.MessageEdited(incoming=True))
        async def handle_all_edited(event):
            await self._process_incoming_event(event, is_edit=True)

        logger.info(f"Setup event handlers for all incoming messages and edits")

    async def _process_incoming_event(self, event, is_edit=False):
        logger.debug(f"[MessageHandler] Processing incoming event - Chat: {event.chat_id}, Userbot: {self.userbot_id}, Edit: {is_edit}, Sender: {event.sender_id}")

        is_dm = event.is_private
        is_mention = event.mentioned
        is_reply_to_me = False
        if event.is_reply:
            me = await self.session_manager.get_me()
            if me:
                reply_to_msg = await event.get_reply_message()
                if reply_to_msg and reply_to_msg.sender_id == me.id:
                    is_reply_to_me = True

        # Handle notifications (only for new messages)
        if not is_edit:
            if is_dm:
                await self.notification_handler.handle_notification_event(event, "dm")
            if is_mention:
                await self.notification_handler.handle_notification_event(event, "mention")
            if is_reply_to_me:
                await self.notification_handler.handle_notification_event(event, "reply")

        # Handle PNL forwarding logic
        if not is_edit:
            if event.text and event.text.startswith('/pnl'):
                await self._handle_pnl_command(event)
            if event.is_reply:
                await self._handle_potential_pnl_reply(event)

        # Handle Command forwarding logic
        if not is_edit:
            if event.text:
                await self._handle_custom_command(event)
            if event.is_reply:
                await self._handle_potential_custom_reply(event)

        # Handle source logic
        is_source = await self.source_manager.get_source_by_chat_id(event.chat_id)
        if is_source:
            logger.debug(f"[MessageHandler] Source message detected in chat {event.chat_id} by userbot {self.userbot_id}")
            await self._handle_source_message(event, is_edit=is_edit)
        else:
            logger.debug(f"[MessageHandler] Not a source message - chat {event.chat_id} not monitored by userbot {self.userbot_id}")

        # Handle auto click
        if not is_edit:
            await self._handle_auto_click(event)
    
    def is_fresh(self, key, seconds=600):
        """Check if cache entry is fresh (default 10 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    def invalidate_cache(self):
        """Invalidates the internal cache."""
        self.cache.clear()
        self.cache_time.clear()
        logger.info(f"Cache invalidated for userbot {self.userbot_id}")
    
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
            logger.info(f"[SPLIT-RESP] Processing source message - Chat: {event.chat_id}, Userbot: {self.userbot_id}, Edit: {is_edit}")

            # Validate source permissions
            permission_check = await self.source_manager.validate_source_permissions(event)
            logger.debug(f"[SPLIT-RESP] Source permission check result: {permission_check}")

            if not permission_check['allowed']:
                logger.debug(f"[SPLIT-RESP] Source message rejected: {permission_check['reason']}")
                return

            source = permission_check['source']
            live_source_name = self.utils.get_chat_title(getattr(event, 'chat', None))

            source_type_value = source.get('source_type')
            if not source_type_value:
                if event.is_private:
                    source_type_value = 'dm'
                elif event.is_channel:
                    source_type_value = 'channel'
                else:
                    source_type_value = 'group'

            if live_source_name:
                try:
                    await self.source_model.update(source['id'], {'display_name': live_source_name})
                    source['display_name'] = live_source_name
                except Exception as update_error:
                    logger.debug(f"[SPLIT-RESP] Unable to update source display name: {update_error}")

            logger.info(
                f"[SPLIT-RESP] Source validated - ID: {source['id']}, Name: {live_source_name or source.get('display_name') or source.get('name', 'N/A')}"
            )

            # Check if this userbot is assigned to monitor this source
            routing_rules = await self.source_model.get_routing_rules(source['id'])
            logger.info(f"[SPLIT-RESP] Found {len(routing_rules)} routing rules for source {source['id']}")

            # Check source-level bot assignments first (NEW FEATURE)
            source_monitor_bot = source.get('default_monitoring_userbot_id')
            source_forward_bot = source.get('default_forwarding_userbot_id')

            monitoring_allowed = False
            primary_monitor_id = None
            designated_monitors = set()  # Initialize to avoid UnboundLocalError

            if source_monitor_bot:
                # Source has a designated monitor bot - use it
                primary_monitor_id = source_monitor_bot
                if self.userbot_id == source_monitor_bot:
                    monitoring_allowed = True
                    logger.info(f"[SPLIT-RESP] Userbot {self.userbot_id} is the source-level designated monitor for source {source['id']}")
                else:
                    logger.debug(f"[SPLIT-RESP] Userbot {self.userbot_id} not source-level monitor (assigned: {source_monitor_bot})")
            else:
                # Fallback to routing rules logic
                designated_monitors = {rule['monitoring_userbot_id'] for rule in routing_rules if rule['monitoring_userbot_id'] is not None}
                logger.debug(f"[SPLIT-RESP] Designated monitors for source {source['id']}: {designated_monitors}")

                if designated_monitors:
                    # If there are explicit assignments, only ONE bot should monitor.
                    # By convention, we'll deterministically pick the one with the lowest ID.
                    primary_monitor_id = min(designated_monitors)
                    if self.userbot_id == primary_monitor_id:
                        monitoring_allowed = True
                        logger.info(f"[SPLIT-RESP] Userbot {self.userbot_id} is the designated primary monitor (min ID) for source {source['id']}")
                    else:
                        logger.debug(f"[SPLIT-RESP] Userbot {self.userbot_id} not primary monitor (primary: {primary_monitor_id})")
                else:
                    # BACKWARD COMPATIBILITY: No explicit monitor is set.
                    # To prevent a race condition, we'll deterministically assign monitoring duty
                    # to the forwarding bot of the *first* routing rule found.
                    if routing_rules and routing_rules[0]['forwarding_userbot_id']:
                        primary_monitor_id = routing_rules[0]['forwarding_userbot_id']
                        if self.userbot_id == primary_monitor_id:
                            monitoring_allowed = True
                            logger.info(f"[SPLIT-RESP] Userbot {self.userbot_id} assigned as monitor by backward compatibility rule (first forwarder) for source {source['id']}")
                        else:
                            logger.debug(f"[SPLIT-RESP] Userbot {self.userbot_id} not assigned as backward compatibility monitor (assigned: {primary_monitor_id})")
                    else:
                        logger.warning(f"[SPLIT-RESP] No routing rules or forwarding userbot found for source {source['id']}")

            if not monitoring_allowed:
                logger.debug(f"[SPLIT-RESP] ⏭️ Userbot {self.userbot_id} SKIPPING - not designated monitor for source {event.chat_id}")
                logger.debug(f"[SPLIT-RESP] Designated monitors: {designated_monitors}, Primary: {primary_monitor_id if designated_monitors else 'source-level or backward compatibility'}")
                return
            else:
                logger.debug(f"[SPLIT-RESP] ✅ Userbot {self.userbot_id} IS designated monitor for source {event.chat_id}")

            # Get all target groups for this source using routing rules
            target_groups = await self.source_manager.get_target_groups_for_source(event.chat_id)

            # Process message for tokens regardless of routing rules (needed for curated alpha)
            addresses = await self.token_monitor.process_source_message(event, event.chat_id, target_groups or [])

            # Handle Curated Alpha logic independently (works without routing rules)
            if addresses:
                await self._handle_curated_alpha(addresses, event.chat_id, event)

            # Early return if no routing rules for regular forwarding
            if not target_groups:
                logger.warning(f"[SPLIT-RESP] No target groups found for source {event.chat_id} - skipping regular forwarding")
                return

            logger.info(f"[SPLIT-RESP] Found {len(target_groups)} target groups: {[f'{g['title']}({g['id']})' for g in target_groups]}")

            if not addresses:
                logger.debug(f"[SPLIT-RESP] No token addresses found in message")
                return
            
            logger.info(f"[SPLIT-RESP] Extracted {len(addresses)} token addresses: {[addr[:8] + '...' for addr in addresses]}")

            # Filter out recently forwarded tokens
            unseen_addresses = []
            for address in addresses:
                recently_forwarded = await db.fetchval("""
                    SELECT 1 FROM forwarded_tokens_log
                    WHERE token_address = $1 AND source_chat_id = $2
                    AND forwarded_at > NOW() - INTERVAL '24 hours'
                    LIMIT 1
                """, address, event.chat_id)

                if recently_forwarded:
                    logger.info(f"Token {address[:8]}... from source {event.chat_id} was already forwarded recently. Skipping.")
                else:
                    unseen_addresses.append(address)

            if not unseen_addresses:
                logger.info("All extracted tokens were recently forwarded. Nothing to do.")
                return
            
            addresses_to_forward = unseen_addresses
            logger.info(f"[SPLIT-RESP] Starting job queue population for {len(addresses_to_forward)} new tokens across {len(target_groups)} target groups")

            # Queue tokens for all target groups
            total_queued = 0
            total_failed = 0

            for target_group in target_groups:
                logger.debug(f"[SPLIT-RESP] Processing target group: {target_group['title']}({target_group['id']})")

                # Check if group can accept calls at current time/day
                if not await self._can_group_accept_calls(target_group['tg_chat_id']):
                    logger.info(f"[SPLIT-RESP] Skipping group {target_group['tg_chat_id']} - outside schedule window")
                    continue

                group_queued = 0
                group_failed = 0

                # Find routing rule and forwarding userbot for this target group
                routing_rule = None
                forwarding_userbot_id = None

                for rule in routing_rules:
                    if rule['target_group_id'] == target_group['id'] and rule['enabled']:
                        routing_rule = rule
                        forwarding_userbot_id = rule['forwarding_userbot_id']
                        logger.debug(f"[SPLIT-RESP] Matched routing rule {rule['id']} for group {target_group['id']}, forwarding_userbot: {forwarding_userbot_id}")
                        break

                if not routing_rule:
                    logger.warning(f"[SPLIT-RESP] No routing rule found for target group {target_group['id']} - SKIPPING")
                    continue

                # Use any active userbot if no forwarding userbot assigned (backward compatibility)
                if not forwarding_userbot_id:
                    forwarding_userbot_id = self.userbot_id
                    logger.info(f"[SPLIT-RESP] No forwarding userbot assigned, using current userbot {self.userbot_id} (backward compatibility)")
                else:
                    logger.info(f"[SPLIT-RESP] Using assigned forwarding userbot {forwarding_userbot_id}")

                # Queue each token for this target group
                for address in addresses_to_forward:
                    try:
                        # Get source info for the call
                        display_source_name = live_source_name or source.get('display_name') or source.get('name') or source.get('title')
                        source_info = f"From {display_source_name or event.chat_id}"
                        additional_info_dict = {
                            "message_text": self.utils.get_message_text(event.message) if hasattr(event, 'message') else "",
                            "caller_name": self.utils.get_user_name(event.sender),
                            "source_name": display_source_name,
                            "source_type": source_type_value,
                            "source_chat_id": event.chat_id,
                            "seen_sources": [
                                {
                                    'chat_id': event.chat_id,
                                    'name': display_source_name,
                                    'source_type': source_type_value,
                                    'caller_name': self.utils.get_user_name(event.sender),
                                    'caller_user_id': event.sender_id,
                                }
                            ],
                            "caller_user_id": event.sender_id,
                        }

                        logger.debug(f"[SPLIT-RESP] Queueing token {address[:8]}... for target {target_group['id']} via userbot {forwarding_userbot_id}")

                        # Add job to call queue
                        job = await self.call_queue_model.add_job(
                            routing_rule_id=routing_rule['id'],
                            token_address=address,
                            source_message_id=event.id,
                            source_chat_id=event.chat_id,
                            source_user_id=event.sender_id,
                            target_group_id=target_group['id'],
                            target_chat_id=target_group['tg_chat_id'],
                            forwarding_userbot_id=forwarding_userbot_id,
                            source_info=json.dumps(source_info),
                            additional_info=json.dumps(additional_info_dict)
                        )

                        if job:
                            group_queued += 1
                            total_queued += 1
                            logger.debug(f"[SPLIT-RESP] ✅ Job {job['id']} created for {address[:8]}... → {target_group['title']}")
                        else:
                            group_failed += 1
                            total_failed += 1
                            logger.warning(f"[SPLIT-RESP] ❌ Failed to queue {address[:8]}... for {target_group['title'] or target_group['tg_chat_id']}")

                    except Exception as token_error:
                        group_failed += 1
                        total_failed += 1
                        logger.error(f"[SPLIT-RESP] ❌ Error queuing token {address[:8]}... for target {target_group['tg_chat_id']} via userbot {self.userbot_id}: {token_error}")
                        import traceback
                        logger.error(f"[SPLIT-RESP] Full traceback: {traceback.format_exc()}")

                if group_queued > 0:
                    logger.info(f"[SPLIT-RESP] ✅ Group {target_group['title']}: {group_queued} tokens queued")
                if group_failed > 0:
                    logger.warning(f"[SPLIT-RESP] ❌ Group {target_group['title']}: {group_failed} tokens failed")

            logger.info(f"[SPLIT-RESP] 🎯 QUEUE SUMMARY: {total_queued} jobs created, {total_failed} failed across {len(target_groups)} target groups by userbot {self.userbot_id}")
            
            # After successfully queuing the jobs, log the new tokens as forwarded
            if total_queued > 0:
                try:
                    # Use executemany for efficiency if available, otherwise loop
                    if hasattr(db.pool, 'executemany'):
                        await db.pool.executemany("""
                            INSERT INTO forwarded_tokens_log (token_address, source_chat_id)
                            VALUES ($1, $2)
                        """, [(addr, event.chat_id) for addr in addresses_to_forward])
                    else: # Fallback for pools that don't support it
                        for addr in addresses_to_forward:
                             await db.execute("""
                                INSERT INTO forwarded_tokens_log (token_address, source_chat_id)
                                VALUES ($1, $2)
                            """, addr, event.chat_id)
                    logger.info(f"Logged {len(addresses_to_forward)} new tokens to forwarded_tokens_log for source {event.chat_id}")
                except Exception as log_error:
                    logger.error(f"Failed to log forwarded tokens: {log_error}")

            # Update bot last seen
            await self.bot_model.update_last_seen(self.userbot_id)
            
        except Exception as e:
            logger.error(f"[SPLIT-RESP] ❌ Critical error handling source message in chat {event.chat_id} by userbot {self.userbot_id}: {e}")
            import traceback
            logger.error(f"[SPLIT-RESP] Full traceback: {traceback.format_exc()}")

    async def _handle_auto_click(self, event):
        if not event.is_reply:
            return

        reply_to_msg_id = event.message.reply_to_msg_id
        if not reply_to_msg_id:
            return

        # Check if this is a reply to a message we are tracking for auto-click
        tracked_msg = await db.fetchrow(
            "SELECT * FROM autoclick_tracked_messages WHERE original_message_id = $1 AND chat_id = $2 AND status = 'tracking'",
            reply_to_msg_id, event.chat_id
        )
        if not tracked_msg:
            return

        # Get the rule associated with this tracked message
        rule = await self.rule_model.get_by_id(tracked_msg['rule_id'])
        if not rule or not rule['enabled']:
            return

        # Check if the reply is from the correct bot
        if rule['bot_id'] != event.sender_id:
            return
            
        logger.info(f"Valid auto-click reply detected for rule {rule['id']}. Searching for button...")

        # Click the button
        if event.buttons:
            for row in event.buttons:
                for button in row:
                    if hasattr(button, 'text') and rule['button_text'] in button.text:
                        try:
                            await button.click()
                            logger.info(f"Auto-clicked button '{rule['button_text']}' in chat {event.chat_id} for rule {rule['id']}.")
                            # Mark as processed
                            await db.execute("UPDATE autoclick_tracked_messages SET status = 'processed' WHERE id = $1", tracked_msg['id'])
                            return
                        except Exception as e:
                            logger.error(f"Error auto-clicking button for rule {rule['id']}: {e}")
                            await db.execute("UPDATE autoclick_tracked_messages SET status = 'failed' WHERE id = $1", tracked_msg['id'])
                            
        # If we reach here, the button was not found
        logger.warning(f"Reply from bot {event.sender_id} received, but button '{rule['button_text']}' not found for rule {rule['id']}.")

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
                    logger.info(f"[MessageHandler] User {event.sender_id} authorized for rule {rule['id']}, tracking /pnl command")
                    
                    try:
                        # This command is from an authorized user, track it.
                        await db.execute("""
                            INSERT INTO pnl_tracked_messages (rule_id, original_message_id, chat_id, sender_id, status)
                            VALUES ($1, $2, $3, $4, 'tracking')
                            ON CONFLICT (original_message_id, chat_id, rule_id) DO NOTHING
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
                    success = await self._forward_pnl_reply(rule, event.message, tracked['id'])
                    if success:
                        logger.info(f"[MessageHandler] Successfully forwarded PNL reply {event.message.id} for tracking {tracked['id']}")
                    else:
                        logger.error(f"[MessageHandler] Failed to forward PNL reply {event.message.id} for tracking {tracked['id']}")
                    
        except Exception as e:
            logger.error(f"[MessageHandler] Error handling potential PNL reply: {e}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")

    async def _forward_pnl_reply(self, rule: dict, message, tracked_id: int) -> bool:
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
            if tracked_id:
                await db.execute(
                    """
                    UPDATE pnl_tracked_messages
                    SET status = 'forwarded',
                        reply_sender_id = $1,
                        last_reply_message_id = $2,
                        updated_at = NOW()
                    WHERE id = $3
                    """,
                    message.sender_id,
                    message.id,
                    tracked_id
                )
            return True
            
        except Exception as e:
            logger.error(f"[MessageHandler] Error forwarding PNL reply: {e}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
            return False

    # ===== COMMAND FORWARDING METHODS =====

    async def _get_cached_command_rules(self, group_id: int, seconds: int = 60) -> List[Dict[str, Any]]:
        """Get command forwarding rules for a group, with caching."""
        cache_key = f"cmd_fwd_rules_{group_id}"
        if self.is_fresh(cache_key, seconds=seconds):
            return self.cache[cache_key]

        rules = await self.cmd_fwd_model.get_enabled_rules_for_group(group_id)
        self.cache[cache_key] = rules
        self.cache_time[cache_key] = time.time()
        return rules

    async def _handle_custom_command(self, event):
        """Handle custom commands in monitored source groups with comprehensive debugging."""
        try:
            logger.debug(f"[MessageHandler] Custom command check: chat_id={event.chat_id}, "
                        f"sender_id={event.sender_id}, message_id={event.message.id}, "
                        f"text='{event.message.text[:100]}'")

            group = await self.group_model.get_by_chat_id(event.chat_id)
            if not group:
                logger.debug(f"[MessageHandler] No group found for chat {event.chat_id}, ignoring custom command")
                return

            rules = await self._get_cached_command_rules(group['id'])
            logger.debug(f"[MessageHandler] Found {len(rules)} enabled command rules for chat {event.chat_id}")

            if not rules:
                logger.debug(f"[MessageHandler] No command rules found for chat {event.chat_id}, ignoring command")
                return

            for rule in rules:
                logger.debug(f"[MessageHandler] Processing rule {rule['id']} for command '{rule['command_text']}'")

                # Check if message matches this rule's command exactly
                if event.message.text.strip() == rule['command_text']:
                    logger.debug(f"[MessageHandler] Message matches command '{rule['command_text']}' for rule {rule['id']}")

                    allowed_users = rule.get('allowed_command_user_ids', [])
                    logger.debug(f"[MessageHandler] Rule {rule['id']} allowed users: {allowed_users}")

                    if not allowed_users or event.sender_id in allowed_users:
                        logger.info(f"[MessageHandler] User {event.sender_id} authorized for rule {rule['id']}, tracking command '{rule['command_text']}'")

                        try:
                            # Track this command
                            tracked = await self.cmd_tracked_model.track_command(
                                rule['id'], event.message.id, event.chat_id,
                                event.sender_id, rule['command_text']
                            )

                            if tracked:
                                logger.info(f"[MessageHandler] Successfully tracking command: "
                                           f"message_id={event.message.id}, rule_id={rule['id']}, "
                                           f"chat_id={event.chat_id}, sender_id={event.sender_id}, "
                                           f"command='{rule['command_text']}'")
                        except Exception as db_err:
                            logger.error(f"[MessageHandler] Database error tracking command: {db_err}")
                            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
                    else:
                        logger.debug(f"[MessageHandler] User {event.sender_id} not authorized for rule {rule['id']} "
                                   f"(allowed: {allowed_users})")

        except Exception as e:
            logger.error(f"[MessageHandler] Error handling custom command: {e}")
            logger.error(f"[MessageHandler] Event details: chat_id={event.chat_id}, "
                        f"sender_id={event.sender_id}, message_id={event.message.id}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")

    async def _handle_potential_custom_reply(self, event):
        """Handle potential replies to custom commands in real-time."""
        try:
            if not event.message.reply_to_msg_id:
                return  # Not a reply

            logger.debug(f"[MessageHandler] Potential custom command reply: chat_id={event.chat_id}, "
                        f"sender_id={event.sender_id}, reply_to={event.message.reply_to_msg_id}")

            # Check if this is a reply to a tracked custom command
            tracked_messages = await self.cmd_tracked_model.get_tracked_messages_for_reply(
                event.message.reply_to_msg_id, event.chat_id
            )

            if not tracked_messages:
                return  # Not replying to a tracked custom command

            logger.debug(f"[MessageHandler] Found {len(tracked_messages)} tracked custom messages for reply")

            for tracked in tracked_messages:
                # Get the rule
                rule = await self.cmd_fwd_model.get_by_id(tracked['rule_id'])
                if not rule or not rule['enabled']:
                    continue

                # Only designated userbot should attempt forwarding
                if self.userbot_id != rule.get('forwarding_userbot_id'):
                    logger.debug(f"[MessageHandler] Userbot {self.userbot_id} not designated for rule {rule['id']} (need {rule.get('forwarding_userbot_id')})")
                    continue

                # Filter out automated messages
                if "🔎Fetching leader board..." in event.message.text:
                    logger.debug(f"[MessageHandler] Skipping fetching leader board message {event.message.id}")
                    continue

                allowed_reply_users = rule.get('allowed_reply_user_ids', [])

                if not allowed_reply_users or event.sender_id in allowed_reply_users:
                    logger.info(f"[MessageHandler] Valid custom command reply detected from user {event.sender_id}, forwarding immediately for rule {rule['id']}")

                    # Forward the message using the designated forwarding userbot
                    success = await self._forward_custom_reply(rule, event.message, tracked['id'])
                    if success:
                        logger.info(f"[MessageHandler] Successfully forwarded custom command reply {event.message.id} for tracking {tracked['id']}")
                    else:
                        logger.error(f"[MessageHandler] Failed to forward custom command reply {event.message.id} for tracking {tracked['id']}")

        except Exception as e:
            logger.error(f"[MessageHandler] Error handling potential custom reply: {e}")
            logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")

    async def _forward_custom_reply(self, rule: dict, message, tracked_id: int) -> bool:
        """Forward a custom command reply message to the destination channel."""
        try:
            # Check if this userbot is the designated forwarding userbot
            if self.userbot_id != rule.get('forwarding_userbot_id'):
                logger.debug(f"[MessageHandler] Userbot {self.userbot_id} not designated for forwarding (need {rule.get('forwarding_userbot_id')})")
                return False

            client = self.session_manager.get_client()
            if not client:
                logger.error("[MessageHandler] No client available for custom command forwarding")
                return False

            logger.debug(f"[MessageHandler] Forwarding custom command reply message {message.id} to channel {rule['destination_channel_id']}")

            # Resolve entity using same pattern as call_executor.py
            entity = await self._resolve_entity_safely(client, rule['destination_channel_id'])

            await client.forward_messages(
                entity=entity,
                messages=message
            )

            logger.info(f"[MessageHandler] Successfully forwarded custom command reply to channel {rule['destination_channel_id']}")
            # Don't mark as forwarded - keep tracking status for multiple replies
            return True

        except Exception as e:
            logger.error(f"[MessageHandler] Error forwarding custom command reply: {e}")
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
                            SET status = 'sent', sent_at = NOW(), message_id = $2
                            WHERE id = $1
                        """, call['id'], result['message_id'])
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

    async def _handle_curated_alpha(self, addresses: List[str], source_chat_id: int, event):
        """
        Processes tokens against Curated Alpha rules.
        """
        try:
            logger.debug(f"[CuratedAlpha] Processing event for source chat ID: {source_chat_id}")
            # Find all enabled rules that require this source chat
            rules = await self.curated_alpha_rule_model.db.fetch("""
                SELECT * FROM curated_alpha_rules
                WHERE $1 = ANY(required_source_chat_ids) AND enabled = true
            """, source_chat_id)

            if not rules:
                logger.debug(f"[CuratedAlpha] No active rules found for source_chat_id: {source_chat_id}")
                return # No rules care about this source

            logger.debug(f"[CuratedAlpha] Source {source_chat_id} is part of {len(rules)} rule(s).")

            source_record = await self.source_model.get_source_by_chat_id(source_chat_id)
            source_type_value = source_record.get('source_type') if source_record and source_record.get('source_type') else (
                'dm' if event.is_private else 'channel' if event.is_channel else 'group'
            )
            current_source_name = self.utils.get_chat_title(getattr(event, 'chat', None))

            for address in addresses:
                for rule in rules:
                    rule_id = rule['id']
                    logger.debug(f"[CuratedAlpha] Checking token {address[:8]} against rule {rule_id} ('{rule['name']}')")
                    logger.debug(f"[CuratedAlpha] Rule requirements: Mentions={rule.get('required_mentions', 'All')}, Sources={rule['required_source_chat_ids']}")
                    
                    # Check if this token has already been triggered for this rule
                    existing_state = await self.curated_alpha_token_state_model.db.fetchrow("""
                        SELECT * FROM curated_alpha_token_state
                        WHERE rule_id = $1 AND token_address = $2
                    """, rule_id, address)

                    if existing_state and existing_state['status'] in ('triggered', 'expired'):
                        logger.debug(f"[CuratedAlpha] Found existing state for token: {dict(existing_state)}")
                        logger.debug(f"[CuratedAlpha] Token {address[:8]} already '{existing_state['status']}' for rule {rule_id}. Skipping.")
                        continue

                    if existing_state:
                        logger.debug(f"[CuratedAlpha] Found existing 'tracking' state for token {address[:8]} in rule {rule_id}.")
                        # It's being tracked, let's update it
                        if source_chat_id in existing_state['seen_in_source_chat_ids']:
                            logger.debug(f"[CuratedAlpha] Token {address[:8]} already seen in this source for rule {rule_id}. Skipping.")
                            continue

                        # Check if time window has expired
                        from datetime import datetime, timezone
                        time_since_first_seen = (datetime.now(timezone.utc) - existing_state['first_seen_at']).total_seconds()
                        if time_since_first_seen > rule['time_window_seconds']:
                            await self.curated_alpha_token_state_model.update(existing_state['id'], {'status': 'expired'})
                            logger.info(f"[CuratedAlpha] Token {address[:8]}... expired for rule {rule_id}.")
                            continue

                        # Add the new source and get the updated list
                        updated_seen_sources = existing_state['seen_in_source_chat_ids'] + [source_chat_id]
                        await self.curated_alpha_token_state_model.update(existing_state['id'], {
                            'seen_in_source_chat_ids': updated_seen_sources
                        })
                        logger.debug(f"[CuratedAlpha] Updated token {address[:8]} state for rule {rule_id}. Seen in: {updated_seen_sources}")
                        
                        seen_sources_set = set(updated_seen_sources)
                        required_sources_set = set(rule['required_source_chat_ids'])

                    else:
                        # First time seeing this token for this rule
                        logger.debug(f"[CuratedAlpha] Creating new tracking state for token {address[:8]} in rule {rule_id}.")
                        await self.curated_alpha_token_state_model.create({
                            'rule_id': rule_id,
                            'token_address': address,
                            'seen_in_source_chat_ids': [source_chat_id]
                        })
                        seen_sources_set = {source_chat_id}
                        required_sources_set = set(rule['required_source_chat_ids'])

                    # Check if the condition is now met
                    required_sources_set = set(rule['required_source_chat_ids'])
                    seen_in_rule_sources = seen_sources_set.intersection(required_sources_set)
                    
                    required_mentions = rule.get('required_mentions')
                    # Default to all if not set, 0, or invalid
                    if not required_mentions or required_mentions <= 0:
                        required_mentions = len(required_sources_set)

                    logger.debug(f"[CuratedAlpha] Rule {rule_id} check: Seen {len(seen_in_rule_sources)}/{required_mentions} required sources.")

                    if len(seen_in_rule_sources) >= required_mentions:
                        logger.info(f"[CuratedAlpha] ✅ Condition MET for token {address[:8]}... on rule {rule_id}!")
                        
                        # Mark as triggered to prevent re-processing
                        state_id_to_update = existing_state['id'] if existing_state else \
                            (await self.curated_alpha_token_state_model.db.fetchrow(
                                "SELECT id FROM curated_alpha_token_state WHERE rule_id = $1 AND token_address = $2",
                                rule_id, address))['id']
                        await self.curated_alpha_token_state_model.update(state_id_to_update, {'status': 'triggered'})

                        source_info = f"Curated Alpha: Rule '{rule.get('name', rule_id)}'"

                        # Gather friendly names for all contributing sources
                        seen_source_details = [
                            {
                                'chat_id': source_chat_id,
                                'name': current_source_name,
                                'source_type': source_type_value,
                                'caller_name': self.utils.get_user_name(event.sender),
                                'caller_user_id': event.sender_id,
                            }
                        ]
                        try:
                            ordered_seen_sources = sorted(seen_in_rule_sources)
                        except TypeError:
                            ordered_seen_sources = list(seen_in_rule_sources)

                        for seen_chat_id in ordered_seen_sources:
                            try:
                                seen_chat_id_int = int(seen_chat_id)
                            except (TypeError, ValueError):
                                seen_chat_id_int = seen_chat_id

                            if seen_chat_id_int == source_chat_id:
                                continue

                            seen_source_record = await self.source_model.get_source_by_chat_id(seen_chat_id_int)
                            if seen_source_record:
                                display_name = (
                                    seen_source_record.get('display_name')
                                    or seen_source_record.get('name')
                                    or seen_source_record.get('title')
                                )
                                seen_source_type = seen_source_record.get('source_type')
                            else:
                                display_name = f"Chat {seen_chat_id_int}"
                                seen_source_type = 'group'

                            seen_source_details.append(
                                {
                                    'chat_id': seen_chat_id_int,
                                    'name': display_name,
                                    'source_type': seen_source_type,
                                }
                            )

                        # Look up target group ID for template support
                        target_group_id = None
                        try:
                            group_record = await self.db.fetchrow(
                                "SELECT id FROM groups WHERE tg_chat_id = $1",
                                rule['destination_chat_id']
                            )
                            if group_record:
                                target_group_id = group_record['id']
                        except Exception as group_lookup_error:
                            logger.debug(f"Could not find group for destination chat {rule['destination_chat_id']}: {group_lookup_error}")

                        # Get source object to pass its details
                        additional_info_dict = {
                            "message_text": self.utils.get_message_text(event.message) if hasattr(event, 'message') else "",
                            "target_group_id_fallback": target_group_id,
                            "caller_name": self.utils.get_user_name(event.sender),
                            "source_name": current_source_name,
                            "source_type": source_type_value,
                            "source_chat_id": source_chat_id,
                            "seen_sources": seen_source_details,
                            "caller_user_id": event.sender_id,
                        }
                        additional_info = json.dumps(additional_info_dict)

                        await self.call_queue_model.add_job(
                            curated_alpha_rule_id=rule_id,
                            token_address=address,
                            source_message_id=event.id,
                            source_chat_id=source_chat_id,
                            source_user_id=event.sender_id,
                            target_group_id=target_group_id,
                            target_chat_id=rule['destination_chat_id'],
                            forwarding_userbot_id=rule['forwarding_userbot_id'],
                            source_info=json.dumps(source_info),
                            additional_info=additional_info,
                            priority=10 # Higher priority for curated calls
                        )
                        logger.info(f"[CuratedAlpha] Queued call for {address[:8]}... to {rule['destination_chat_id']}")

        except Exception as e:
            logger.error(f"Error in _handle_curated_alpha: {e}", exc_info=True)
