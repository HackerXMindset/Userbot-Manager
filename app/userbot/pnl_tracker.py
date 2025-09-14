"""
PNL Tracker - A robust, polling-based system for tracking and forwarding PNL replies.
"""

import asyncio
import logging
import traceback
from typing import Dict, Any, List, Optional
from telethon.errors import MessageIdInvalidError
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

from app.db import db
from app.models import PnlForwardingRuleModel

logger = logging.getLogger(__name__)

# Set detailed logging for PNL tracker operations
logging.getLogger(__name__).setLevel(logging.DEBUG)

class PnlTracker:
    """Actively polls and processes PNL forwarding requests from the database."""

    def __init__(self, userbot_id: int, session_manager):
        self.userbot_id = userbot_id
        self.session_manager = session_manager
        self.pnl_model = PnlForwardingRuleModel(db)
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.running:
            return
        self.running = True
        self._task = asyncio.create_task(self._polling_loop())
        logger.info(f"[PnlTracker] Started for userbot {self.userbot_id}")

    async def stop(self):
        if not self.running:
            return
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"[PnlTracker] Stopped for userbot {self.userbot_id}")

    async def _polling_loop(self):
        # Polling disabled - MessageHandler now handles real-time forwarding
        logger.info(f"[PnlTracker] Polling loop disabled - using real-time forwarding via MessageHandler")
        while self.running:
            try:
                # Keep the tracker alive but don't poll - MessageHandler handles forwarding
                await asyncio.sleep(30)  # Just keep process alive
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PnlTracker] Error in polling loop: {e}")
                await asyncio.sleep(15) # Wait longer on error

    async def _process_tracked_messages(self):
        """Fetch and process all active PNL tracking records with debugging."""
        try:
            logger.debug(f"[PnlTracker] Processing tracked messages for userbot {self.userbot_id}")
            client = self.session_manager.get_client()
            if not client:
                logger.warning(f"[PnlTracker] No client available for userbot {self.userbot_id}")
                return

            tracked_messages = await db.fetch("""
                SELECT * FROM pnl_tracked_messages
                WHERE status = 'tracking'
                AND created_at > NOW() - INTERVAL '3 minutes' -- Only process recent requests
                ORDER BY created_at ASC
            """)

            logger.debug(f"[PnlTracker] Found {len(tracked_messages)} tracked messages to process")

            for tracked in tracked_messages:
                try:
                    logger.debug(f"[PnlTracker] Processing tracked message {tracked['id']}: "
                               f"chat={tracked['chat_id']}, message={tracked['original_message_id']}, "
                               f"rule={tracked['rule_id']}")
                    await self._check_for_valid_reply(client, tracked)
                except Exception as e:
                    logger.error(f"[PnlTracker] Failed to process tracked message {tracked['id']}: {e}")
                    logger.error(f"[PnlTracker] Tracked message details: {tracked}")
                    logger.error(f"[PnlTracker] Full traceback: {traceback.format_exc()}")
                    
        except Exception as e:
            logger.error(f"[PnlTracker] Error in _process_tracked_messages: {e}")
            logger.error(f"[PnlTracker] Full traceback: {traceback.format_exc()}")


    async def _check_for_valid_reply(self, client, tracked: Dict[str, Any]):
        """Check if the original /pnl message has a valid reply with debugging."""
        try:
            logger.debug(f"[PnlTracker] Checking for reply to tracked message {tracked['id']}")
            rule = await self.pnl_model.get_by_id(tracked['rule_id'])
            
            if not rule:
                logger.warning(f"[PnlTracker] Rule {tracked['rule_id']} not found for tracked message {tracked['id']}")
                await self._update_status(tracked['id'], 'expired')
                return
                
            if not rule['enabled']:
                logger.debug(f"[PnlTracker] Rule {tracked['rule_id']} is disabled, expiring tracked message {tracked['id']}")
                await self._update_status(tracked['id'], 'expired')
                return

            logger.debug(f"[PnlTracker] Rule {rule['id']}: allowed_reply_users={rule.get('allowed_reply_user_ids', [])}")

            try:
                original_message = await client.get_messages(tracked['chat_id'], ids=tracked['original_message_id'])
            except MessageIdInvalidError:
                logger.warning(f"[PnlTracker] Original message {tracked['original_message_id']} not found, expiring.")
                await self._update_status(tracked['id'], 'expired')
                return
                
            if not original_message:
                logger.debug(f"[PnlTracker] Original message {tracked['original_message_id']} is None, skipping.")
                return

            if not original_message.replies:
                logger.debug(f"[PnlTracker] Original message {tracked['original_message_id']} has no replies, skipping.")
                return

            allowed_reply_users = rule.get('allowed_reply_user_ids', [])
            logger.debug(f"[PnlTracker] Checking replies from allowed users: {allowed_reply_users}")

            replies = await client.get_messages(tracked['chat_id'], reply_to=original_message.id)
            if not replies:
                logger.debug(f"[PnlTracker] No replies found for message {original_message.id}")
                return

            for reply in replies:
                logger.debug(f"[PnlTracker] Found reply from user {reply.sender_id}")
                
                if not allowed_reply_users or reply.sender_id in allowed_reply_users:
                    logger.info(f"[PnlTracker] Valid reply found for PNL {tracked['id']} from user {reply.sender_id}. Forwarding.")
                    success = await self._forward_message(rule, reply)
                    if success:
                        await self._update_status(tracked['id'], 'forwarded')
                    else:
                        logger.error(f"[PnlTracker] Failed to forward reply for tracked message {tracked['id']}")
                    return
                else:
                    logger.debug(f"[PnlTracker] Reply from user {reply.sender_id} not in allowed list {allowed_reply_users}")

        except Exception as e:
            logger.error(f"[PnlTracker] Error in _check_for_valid_reply for {tracked['id']}: {e}")
            logger.error(f"[PnlTracker] Full traceback: {traceback.format_exc()}")

    

    async def _forward_message(self, rule: Dict[str, Any], message) -> bool:
        """Forwards a given message using the correct userbot with debugging."""
        try:
            logger.info(f"[PnlTracker] Attempting to forward message {message.id} using rule {rule['id']}")
            forwarding_userbot_id = rule.get('forwarding_userbot_id')
            
            if not forwarding_userbot_id:
                logger.error(f"[PnlTracker] No forwarding userbot specified in rule {rule['id']}")
                return False

            logger.debug(f"[PnlTracker] Rule {rule['id']} requires userbot {forwarding_userbot_id}, "
                        f"current userbot: {self.userbot_id}")

            # Only allow designated userbot to forward
            if self.userbot_id != forwarding_userbot_id:
                logger.debug(f"[PnlTracker] Userbot {self.userbot_id} not designated for forwarding (need {forwarding_userbot_id})")
                return False

            logger.debug(f"[PnlTracker] Using current userbot {self.userbot_id} for forwarding")
            fwd_client = self.session_manager.get_client()

            if not fwd_client:
                logger.error(f"[PnlTracker] No client available for forwarding")
                return False

            logger.debug(f"[PnlTracker] Forwarding message {message.id} from chat {message.chat_id} "
                        f"to destination {rule['destination_channel_id']}")

            # Resolve entity safely 
            entity = await self._resolve_entity_safely(fwd_client, rule['destination_channel_id'])

            await fwd_client.forward_messages(
                entity=entity,
                messages=message
            )
            
            logger.info(f"[PnlTracker] Successfully forwarded message {message.id} to channel {rule['destination_channel_id']}")
            return True
            
        except Exception as e:
            logger.error(f"[PnlTracker] Error in _forward_message for rule {rule['id']}: {e}")
            logger.error(f"[PnlTracker] Message details: id={message.id}, chat={message.chat_id}, "
                        f"sender={message.sender_id}")
            logger.error(f"[PnlTracker] Rule details: {rule}")
            logger.error(f"[PnlTracker] Full traceback: {traceback.format_exc()}")
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

    async def _update_status(self, tracked_id: int, status: str):
        await db.execute("UPDATE pnl_tracked_messages SET status = $1, updated_at = NOW() WHERE id = $2", status, tracked_id)
