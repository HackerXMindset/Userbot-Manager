"""
Command Handler - Handles custom command tracking and forwarding
"""

import logging
import time
import traceback
from typing import Dict, Any, List

from app.db import db
from telethon.errors import MessageIdInvalidError

logger = logging.getLogger(__name__)


async def get_cached_command_rules(handler, group_id: int, seconds: int = 60) -> List[Dict[str, Any]]:
    """Get command forwarding rules for a group, with caching."""
    cache_key = f"cmd_fwd_rules_{group_id}"
    if handler.is_fresh(cache_key, seconds=seconds):
        return handler.cache[cache_key]

    rules = await handler.cmd_fwd_model.get_enabled_rules_for_group(group_id)
    handler.cache[cache_key] = rules
    handler.cache_time[cache_key] = time.time()
    return rules


async def handle_custom_command(handler, event):
    """Handle custom commands in monitored source groups with comprehensive debugging."""
    try:
        logger.debug(f"[MessageHandler] Custom command check: chat_id={event.chat_id}, "
                    f"sender_id={event.sender_id}, message_id={event.message.id}, "
                    f"text='{event.message.text[:100]}'")

        group = await handler.group_model.get_by_chat_id(event.chat_id)
        if not group:
            logger.debug(f"[MessageHandler] No group found for chat {event.chat_id}, ignoring custom command")
            return

        rules = await get_cached_command_rules(handler, group['id'])
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
                        tracked = await handler.cmd_tracked_model.track_command(
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


async def handle_potential_custom_reply(handler, event):
    """Handle potential replies to custom commands in real-time."""
    try:
        if not event.message.reply_to_msg_id:
            return  # Not a reply

        logger.debug(f"[MessageHandler] Potential custom command reply: chat_id={event.chat_id}, "
                    f"sender_id={event.sender_id}, reply_to={event.message.reply_to_msg_id}")

        # Check if this is a reply to a tracked custom command
        tracked_messages = await handler.cmd_tracked_model.get_tracked_messages_for_reply(
            event.message.reply_to_msg_id, event.chat_id
        )

        if not tracked_messages:
            return  # Not replying to a tracked custom command

        logger.debug(f"[MessageHandler] Found {len(tracked_messages)} tracked custom messages for reply")

        for tracked in tracked_messages:
            # Get the rule
            rule = await handler.cmd_fwd_model.get_by_id(tracked['rule_id'])
            if not rule or not rule['enabled']:
                continue

            # Only designated userbot should attempt forwarding
            if handler.userbot_id != rule.get('forwarding_userbot_id'):
                logger.debug(f"[MessageHandler] Userbot {handler.userbot_id} not designated for rule {rule['id']} (need {rule.get('forwarding_userbot_id')})")
                continue

            # Filter out automated messages
            if "Fetching leader board..." in event.message.text:
                logger.debug(f"[MessageHandler] Skipping fetching leader board message {event.message.id}")
                continue

            allowed_reply_users = rule.get('allowed_reply_user_ids', [])

            if not allowed_reply_users or event.sender_id in allowed_reply_users:
                logger.info(f"[MessageHandler] Valid custom command reply detected from user {event.sender_id}, forwarding immediately for rule {rule['id']}")

                # Forward the message using the designated forwarding userbot
                success = await forward_custom_reply(handler, rule, event.message, tracked['id'])
                if success:
                    logger.info(f"[MessageHandler] Successfully forwarded custom command reply {event.message.id} for tracking {tracked['id']}")
                else:
                    logger.error(f"[MessageHandler] Failed to forward custom command reply {event.message.id} for tracking {tracked['id']}")

    except Exception as e:
        logger.error(f"[MessageHandler] Error handling potential custom reply: {e}")
        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")


async def forward_custom_reply(handler, rule: dict, message, tracked_id: int) -> bool:
    """Forward a custom command reply message to the destination channel."""
    try:
        # Check if this userbot is the designated forwarding userbot
        if handler.userbot_id != rule.get('forwarding_userbot_id'):
            logger.debug(f"[MessageHandler] Userbot {handler.userbot_id} not designated for forwarding (need {rule.get('forwarding_userbot_id')})")
            return False

        client = handler.session_manager.get_client()
        if not client:
            logger.error("[MessageHandler] No client available for custom command forwarding")
            return False

        logger.debug(f"[MessageHandler] Forwarding custom command reply message {message.id} to channel {rule['destination_channel_id']}")

        # Check if message text is excluded (blacklisted)
        excluded_texts = rule.get('excluded_message_texts', []) or []
        if message.text and excluded_texts and message.text in excluded_texts:
            logger.debug(f"[CMD_FWD] Message excluded by blacklist for rule {rule['id']}: \"{message.text[:50]}\"")
            return False

        # Resolve entity using same pattern as call_executor.py
        entity = await handler._resolve_entity_safely(client, rule['destination_channel_id'])

        try:
            await client.forward_messages(
                entity=entity,
                messages=message
            )
        except MessageIdInvalidError:
            logger.warning(f"[MessageHandler] Could not forward message {message.id}: message ID is invalid or message was deleted.")
            return False

        logger.info(f"[MessageHandler] Successfully forwarded custom command reply to channel {rule['destination_channel_id']}")

        # Post timestamp if enabled
        if rule.get('post_timestamp', False):
            timezone = rule.get('timestamp_timezone', 'IST')
            await handler._post_forward_timestamp(client, entity, rule['destination_channel_id'], timezone)

        # Don't mark as forwarded - keep tracking status for multiple replies
        return True

    except Exception as e:
        logger.error(f"[MessageHandler] Error forwarding custom command reply: {e}")
        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
        return False


async def track_outgoing_command(handler, chat_id: int, message_id: int, command_text: str):
    """Track an outgoing command sent by the scheduler."""
    try:
        logger.info(f"[MessageHandler] Tracking outgoing command '{command_text}' in chat {chat_id}")
        group = await handler.group_model.get_by_chat_id(chat_id)
        if not group:
            logger.warning(f"[MessageHandler] No group found for chat {chat_id}, cannot track outgoing command")
            return

        rules = await get_cached_command_rules(handler, group['id'])
        if not rules:
            logger.warning(f"[MessageHandler] No command rules found for chat {chat_id}, cannot track outgoing command")
            return

        for rule in rules:
            if rule['command_text'] == command_text:
                me = await handler.session_manager.get_me()
                if me:
                    await handler.cmd_tracked_model.track_command(
                        rule['id'], message_id, chat_id,
                        me.id, command_text
                    )
                    logger.info(f"[MessageHandler] Successfully tracked outgoing command '{command_text}' in chat {chat_id}")
                else:
                    logger.error("[MessageHandler] Could not get userbot's own user ID, cannot track outgoing command")
                break
    except Exception as e:
        logger.error(f"[MessageHandler] Error tracking outgoing command: {e}")
        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
