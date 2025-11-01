
"""
Message Handler - Handles message processing and event routing
"""

import logging
import time
from typing import Dict, Any, List, Optional
from telethon import events

from app.db import db
from app.dex import get_dex_service
from app.models import BotModel, GroupModel, ScheduleModel, PnlForwardingRuleModel, CommandForwardingRuleModel, CommandTrackedMessageModel, AutoButtonClickRuleModel, CuratedAlphaRuleModel, CuratedAlphaTokenStateModel
from app.models.source_chat import SourceChatModel
from app.models.call_queue import CallQueueModel
from app.models.monitored_source import MonitoredSourceModel
from .token_monitor import TokenMonitor
from .call_executor import CallExecutor
from .source_manager import SourceManager
from .utils import UserbotUtils
from .notification_handler import NotificationHandler

logger = logging.getLogger(__name__)

# Set detailed logging for message handler operations
logging.getLogger(__name__).setLevel(logging.DEBUG)


class MessageHandler:
    """Handles incoming messages and routes them appropriately"""
    
    def __init__(self, userbot_id: int, session_manager):
        self.userbot_id = userbot_id
        self.session_manager = session_manager
        self.db = db
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
        self.monitored_source_model = MonitoredSourceModel(db)

        # Initialize components
        self._album_guard: Dict[tuple, float] = {}
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

        @client.on(events.NewMessage())
        async def handle_all_messages(event):
            await self._process_event(event)

        @client.on(events.MessageEdited())
        async def handle_all_edited(event):
            await self._process_event(event, is_edit=True)

        logger.info(f"Setup event handlers for all incoming, outgoing and edited messages")

    async def _process_event(self, event, is_edit=False):
        direction = "outgoing" if event.out else "incoming"
        logger.debug(f"[MessageHandler] Processing {direction} event - Chat: {event.chat_id}, Userbot: {self.userbot_id}, Edit: {is_edit}, Sender: {event.sender_id}")

        if not is_edit and direction == "incoming":
            try:
                dex_service = get_dex_service()
                chart_fetcher = getattr(dex_service, "chart_fetcher", None)
                if chart_fetcher:
                    await chart_fetcher.handle_chart_bot_reply(event.message)
            except Exception as exc:
                logger.debug(f"[CHART_FETCH] Error handling potential chart reply: {exc}")

        if not is_edit and direction == "incoming":
            await self._handle_monitored_gain_alert(event)

        if direction == "incoming":
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
                    # Handle auto-reply to DMs after button clicks
                    await self._handle_dm_auto_reply(event)
                if is_mention:
                    await self.notification_handler.handle_notification_event(event, "mention")
                if is_reply_to_me:
                    await self.notification_handler.handle_notification_event(event, "reply")

        # Handle PNL forwarding logic
        if not is_edit:
            if event.text and event.text.startswith('/pnl'):
                await self._handle_pnl_command(event)
            if event.is_reply and direction == "incoming":
                await self._handle_potential_pnl_reply(event)

        # Handle Command forwarding logic
        if not is_edit:
            if event.text:
                await self._handle_custom_command(event)
            if event.is_reply and direction == "incoming":
                await self._handle_potential_custom_reply(event)

        # Handle source logic
        is_source = await self.source_manager.get_source_by_chat_id(event.chat_id)
        if is_source and direction == "incoming":
            logger.debug(f"[MessageHandler] Source message detected in chat {event.chat_id} by userbot {self.userbot_id}")
            await self._handle_source_message(event, is_edit=is_edit)
        elif is_source:
            logger.debug(f"[MessageHandler] Outgoing message in source chat {event.chat_id} by userbot {self.userbot_id}, ignoring for source logic")
        else:
            logger.debug(f"[MessageHandler] Not a source message - chat {event.chat_id} not monitored by userbot {self.userbot_id}")

        # Handle auto click
        if not is_edit and direction == "incoming":
            await self._handle_auto_click(event)

        # Handle dynamic click
        if not is_edit and direction == "incoming":
            await self._handle_dynamic_click(event)

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
        from app.userbot.source_handler import can_group_accept_calls

        return await can_group_accept_calls(self, tg_chat_id)


    async def _handle_source_message(self, event, is_edit: bool = False):
        """Handle messages from source chats - extract tokens and route to targets"""
        from app.userbot.source_handler import handle_source_message

        return await handle_source_message(self, event, is_edit=is_edit)


    async def _handle_auto_click(self, event):
        """Handle auto-click for tracked messages with button replies."""
        from app.userbot.auto_click_handler import handle_auto_click
        return await handle_auto_click(self, event)

    async def _handle_dynamic_click(self, event):
        """Handle dynamic button clicking for monitored users"""
        from app.userbot.auto_click_handler import handle_dynamic_click
        return await handle_dynamic_click(self, event)

    async def _handle_dm_auto_reply(self, event):
        """Handle incoming DMs and auto-reply if we're expecting a DM from this bot."""
        from app.userbot.auto_click_handler import handle_dm_auto_reply
        return await handle_dm_auto_reply(self, event)

    async def _get_cached_pnl_rules(self, group_id: int, seconds: int = 60) -> List[Dict[str, Any]]:
        """Get PNL forwarding rules for a group, with caching."""
        from app.userbot.pnl_handler import get_cached_pnl_rules
        return await get_cached_pnl_rules(self, group_id, seconds)

    async def _handle_pnl_command(self, event):
        """Handle /pnl commands in monitored source groups with comprehensive debugging."""
        from app.userbot.pnl_handler import handle_pnl_command
        return await handle_pnl_command(self, event)

    async def _handle_potential_pnl_reply(self, event):
        """Handle potential replies to /pnl commands in real-time."""
        from app.userbot.pnl_handler import handle_potential_pnl_reply
        return await handle_potential_pnl_reply(self, event)

    async def _forward_pnl_reply(self, rule: dict, message, tracked_id: int) -> bool:
        """Forward a PNL reply message to the destination channel."""
        from app.userbot.pnl_handler import forward_pnl_reply
        return await forward_pnl_reply(self, rule, message, tracked_id)

    # ===== COMMAND FORWARDING METHODS =====

    async def _get_cached_command_rules(self, group_id: int, seconds: int = 60) -> List[Dict[str, Any]]:
        """Get command forwarding rules for a group, with caching."""
        from app.userbot.command_handler import get_cached_command_rules
        return await get_cached_command_rules(self, group_id, seconds)

    async def _handle_custom_command(self, event):
        """Handle custom commands in monitored source groups with comprehensive debugging."""
        from app.userbot.command_handler import handle_custom_command
        return await handle_custom_command(self, event)

    async def _handle_monitored_gain_alert(self, event) -> None:
        """Handle gain alert monitoring for configured chats/people."""
        chat_id = event.chat_id
        sender_id = event.sender_id if hasattr(event, "sender_id") else None

        try:
            monitored = None

            if sender_id is not None:
                monitored = await self.monitored_source_model.is_monitored(chat_id, sender_id)

            if not monitored:
                monitored = await self.monitored_source_model.is_monitored(chat_id, None)

            if not monitored:
                return

            if monitored["chat_type"] == "group" and monitored["user_id"] != sender_id:
                logger.debug(
                    f"[MONITOR_DETECT] Skipping chat {chat_id} user {sender_id} – monitored entry expects {monitored['user_id']}"
                )
                return

            message = event.message
            text = self.utils.get_message_text(message)

            if not text:
                logger.debug(f"[MONITOR_DETECT] Chat {chat_id} message has no text/content, skipping")
                return

            addresses = self.utils.extract_token_addresses(text)
            if not addresses:
                logger.debug(f"[MONITOR_DETECT] Chat {chat_id} message from {sender_id} has no contract addresses")
                return

            logger.info(
                "[MONITOR_DETECT] Chat %s matched monitored %s entry %s; found %d address(es)",
                chat_id,
                monitored["chat_type"],
                monitored["id"],
                len(addresses),
            )

            # Persist the user ID exactly as configured on the monitored source so
            # channel/DM entries that track whole chats continue to store NULL and
            # keep downstream joins (e.g. dispatch routing) aligned with that schema.
            tracked_user_id = monitored.get("user_id")

            for address, blockchain in addresses:
                await self.token_monitor.process_monitored_token(
                    address=address,
                    blockchain=blockchain,
                    chat_id=chat_id,
                    message_id=message.id if message else None,
                    user_id=tracked_user_id,
                    chat_type=monitored["chat_type"],
                )

        except Exception as exc:
            logger.error(
                f"[MONITOR_DETECT] Error handling monitored source message in chat {chat_id}: {exc}",
                exc_info=True,
            )

    async def _handle_potential_custom_reply(self, event):
        """Handle potential replies to custom commands in real-time."""
        from app.userbot.command_handler import handle_potential_custom_reply
        return await handle_potential_custom_reply(self, event)

    async def _forward_custom_reply(self, rule: dict, message, tracked_id: int) -> bool:
        """Forward a custom command reply message to the destination channel."""
        from app.userbot.command_handler import forward_custom_reply
        return await forward_custom_reply(self, rule, message, tracked_id)

    async def _post_forward_timestamp(self, client, entity, destination_channel_id: int, timezone_name: str):
        """Post timestamp after forwarding a message in specified timezone."""
        from app.userbot.entity_utils import post_forward_timestamp
        return await post_forward_timestamp(self, client, entity, destination_channel_id, timezone_name)

    async def track_outgoing_command(self, chat_id: int, message_id: int, command_text: str):
        """Track an outgoing command sent by the scheduler."""
        from app.userbot.command_handler import track_outgoing_command
        return await track_outgoing_command(self, chat_id, message_id, command_text)
    async def _resolve_entity_safely(self, client, target_chat_id: int):
        """Safely resolve entity with fallback strategies"""
        from app.userbot.entity_utils import resolve_entity_safely
        return await resolve_entity_safely(self, client, target_chat_id)
    
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
                message=token_address,
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
                        message=call['address'],
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

    async def _handle_curated_alpha(self, tagged_addresses: List[tuple], source_chat_id: int, event):
        """
        Processes tokens against Curated Alpha rules.
        Args:
            tagged_addresses: List of (address, blockchain) tuples
        """
        from app.userbot.curated_alpha_handler import handle_curated_alpha

        return await handle_curated_alpha(self, tagged_addresses, source_chat_id, event)
