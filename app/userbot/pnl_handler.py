"""
PNL Handler - Handles PNL command tracking and forwarding
"""

import logging
import time
import traceback
from typing import Dict, Any, List

from app.db import db

logger = logging.getLogger(__name__)


async def get_cached_pnl_rules(handler, group_id: int, seconds: int = 60) -> List[Dict[str, Any]]:
    """Get PNL forwarding rules for a group, with caching."""
    cache_key = f"pnl_rules_{group_id}"
    if handler.is_fresh(cache_key, seconds=seconds):
        return handler.cache[cache_key]

    rules = await handler.pnl_model.get_enabled_rules_for_group(group_id)
    handler.cache[cache_key] = rules
    handler.cache_time[cache_key] = time.time()
    return rules


async def handle_pnl_command(handler, event):
    """Handle /pnl commands in monitored source groups with comprehensive debugging."""
    try:
        logger.debug(f"[MessageHandler] PNL command received: chat_id={event.chat_id}, "
                    f"sender_id={event.sender_id}, message_id={event.message.id}, "
                    f"text='{event.message.text[:100]}'")

        group = await handler.group_model.get_by_chat_id(event.chat_id)
        if not group:
            logger.debug(f"[MessageHandler] No group found for chat {event.chat_id}, ignoring /pnl command")
            return

        rules = await get_cached_pnl_rules(handler, group['id'])
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


async def handle_potential_pnl_reply(handler, event):
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
            rule = await handler.pnl_model.get_by_id(tracked['rule_id'])
            if not rule or not rule['enabled']:
                continue

            # Only designated userbot should attempt forwarding
            if handler.userbot_id != rule.get('forwarding_userbot_id'):
                logger.debug(f"[MessageHandler] Userbot {handler.userbot_id} not designated for rule {rule['id']} (need {rule.get('forwarding_userbot_id')})")
                continue

            # Filter out flex generation messages
            if "Generating flex.." in event.message.text:
                logger.debug(f"[MessageHandler] Skipping flex generation message {event.message.id}")
                continue

            allowed_reply_users = rule.get('allowed_reply_user_ids', [])

            if not allowed_reply_users or event.sender_id in allowed_reply_users:
                logger.info(f"[MessageHandler] Valid PNL reply detected from user {event.sender_id}, forwarding immediately for rule {rule['id']}")

                # Forward the message using the designated forwarding userbot
                success = await forward_pnl_reply(handler, rule, event.message, tracked['id'])
                if success:
                    logger.info(f"[MessageHandler] Successfully forwarded PNL reply {event.message.id} for tracking {tracked['id']}")
                else:
                    logger.error(f"[MessageHandler] Failed to forward PNL reply {event.message.id} for tracking {tracked['id']}")

    except Exception as e:
        logger.error(f"[MessageHandler] Error handling potential PNL reply: {e}")
        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")


async def forward_pnl_reply(handler, rule: dict, message, tracked_id: int) -> bool:
    """Forward a PNL reply message to the destination channel."""
    try:
        # Check if this userbot is the designated forwarding userbot
        if handler.userbot_id != rule.get('forwarding_userbot_id'):
            logger.debug(f"[MessageHandler] Userbot {handler.userbot_id} not designated for forwarding (need {rule.get('forwarding_userbot_id')})")
            return False

        client = handler.session_manager.get_client()
        if not client:
            logger.error("[MessageHandler] No client available for PNL forwarding")
            return False

        logger.debug(f"[MessageHandler] Forwarding PNL reply message {message.id} to channel {rule['destination_channel_id']}")

        # Resolve entity using same pattern as call_executor.py
        entity = await handler._resolve_entity_safely(client, rule['destination_channel_id'])

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
