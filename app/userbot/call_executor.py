"""
Call Executor - Handles sending call messages to target chats
"""

import logging
from io import BytesIO
from typing import Dict, Any, List, Optional
from datetime import datetime
from telethon.errors import RPCError, FloodWaitError
from telethon.tl.types import PeerChat, PeerUser

from app.db import db
from .utils import MessageTracker, RateLimiter

logger = logging.getLogger(__name__)


class CallExecutor:
    """Executes token calls to target chats"""
    
    def __init__(self, userbot_id: int, session_manager):
        self.userbot_id = userbot_id
        self.session_manager = session_manager
        self.message_tracker = MessageTracker()
        self.rate_limiter = RateLimiter(max_calls=30, time_window=60)  # 30 calls per minute
    
    async def _resolve_entity_safely(self, client, target_chat_id: int):
        """Safely resolve entity with fallback strategies"""
        from app.userbot.entity_utils import resolve_entity_safely as shared_resolver

        try:
            return await shared_resolver(None, client, target_chat_id)
        except Exception as resolve_error:
            logger.debug(f"[CallExecutor] Shared resolver failed for {target_chat_id}: {resolve_error}")
            # As a final fallback, preserve legacy behaviour of returning raw IDs for users
            if target_chat_id >= 0:
                return PeerUser(target_chat_id)
            return target_chat_id
    
    async def send_call_message(
        self,
        target_chat_id: int,
        message: str,
        token_address: str,
        reply_to_message_id: Optional[int] = None,
        photo_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Send a call message to a target chat"""
        try:
            client = self.session_manager.get_client()
            if not client:
                return {'success': False, 'error': 'Client not initialized'}
            
            # Check rate limits
            if not self.rate_limiter.can_make_call():
                logger.warning(f"Rate limit exceeded for userbot {self.userbot_id}")
                return {'success': False, 'error': 'Rate limit exceeded'}
            
            # Pre-resolve entity to avoid entity resolution errors
            resolved_entity = await self._resolve_entity_safely(client, target_chat_id)
            
            # Send message with resolved entity
            try:
                if photo_bytes:
                    # Build a fresh BytesIO buffer per send to avoid closed streams on retries
                    file_obj = BytesIO(photo_bytes)
                    file_obj.name = "chart.jpg"
                    sent_message = await client.send_file(
                        resolved_entity,
                        file=file_obj,
                        caption=message,
                        parse_mode='md',
                        reply_to=reply_to_message_id,
                    )
                else:
                    sent_message = await client.send_message(
                        resolved_entity,
                        message,
                        parse_mode='md',
                        link_preview=False,
                        reply_to=reply_to_message_id
                    )
            except Exception as e:
                # If reply fails (MessageIdInvalidError), retry without reply
                if reply_to_message_id and "message_id_invalid" in str(e).lower():
                    logger.warning(f"Reply to message {reply_to_message_id} failed, sending standalone message")
                    if photo_bytes:
                        file_obj = BytesIO(photo_bytes)
                        file_obj.name = "chart.jpg"
                        sent_message = await client.send_file(
                            resolved_entity,
                            file=file_obj,
                            caption=message,
                            parse_mode='md',
                        )
                    else:
                        sent_message = await client.send_message(
                            resolved_entity,
                            message,
                            parse_mode='md',
                            link_preview=False
                        )
                    # Note: first_message_id cleanup handled in call_dispatcher.py:278-288
                else:
                    raise e
            
            # Record the call for rate limiting
            self.rate_limiter.record_call()
            
            # Track sent message for reply detection
            self.message_tracker.track_message(target_chat_id, sent_message.id)
            
            # Arm auto-click tracking if applicable
            await self._arm_auto_click_tracking(target_chat_id, sent_message.id)
            
            logger.info(f"Sent call for {token_address[:8]}... to chat {target_chat_id}")
            
            return {
                'success': True,
                'message_id': sent_message.id,
                'chat_id': target_chat_id,
                'sent_at': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error sending call message: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def _arm_auto_click_tracking(self, target_chat_id: int, message_id: int):
        """Check for auto-click rules and create tracking records if they exist."""
        try:
            rules = await db.fetch(
                "SELECT id FROM auto_button_click_rules WHERE target_chat_id = $1 AND enabled = true",
                target_chat_id
            )
            if not rules:
                return

            logger.info(f"Found {len(rules)} auto-click rule(s) for chat {target_chat_id}. Arming tracking for message {message_id}.")
            for rule in rules:
                await db.execute(
                    """
                    INSERT INTO autoclick_tracked_messages (rule_id, original_message_id, chat_id, status, userbot_id)
                    VALUES ($1, $2, $3, 'tracking', $4)
                    ON CONFLICT (original_message_id, chat_id, rule_id) DO NOTHING
                    """,
                    rule['id'], message_id, target_chat_id, self.userbot_id
                )
        except Exception as e:
            logger.error(f"Error arming auto-click tracking for message {message_id}: {e}")
    
    async def forward_tokens_to_targets(self, group_id: int, addresses: List[str], 
                                       source_event) -> Dict[str, Any]:
        """Forward token addresses from source to group's target chats"""
        try:
            # Get group's targets
            targets = await self._get_group_targets(group_id)
            
            if not targets:
                logger.debug(f"No targets configured for group {group_id}")
                return {'success': True, 'sent_count': 0, 'targets_count': 0}
            
            # Get group info for call logging
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                logger.error(f"Group {group_id} not found")
                return {'success': False, 'error': f'Group {group_id} not found'}
            
            successful_sends = 0
            failed_sends = 0
            
            for address in addresses:
                logger.info(f"Token {address[:8]}... forwarding to {len(targets)} targets")
                
                # Send to each target chat
                for target in targets:
                    try:
                        # Get source info for the message
                        from .utils import UserbotUtils
                        utils = UserbotUtils()
                        source_title = utils.get_chat_title(source_event.chat)
                        user_name = utils.get_user_name(source_event.sender)
                        source_info = f"{source_title} ({user_name})"
                        
                        # Create formatted call message
                        call_result = await self.send_call_message(
                            target_chat_id=target['dest_chat_id'],
                            message=address,
                            token_address=address
                        )
                        
                        if call_result['success']:
                            # Log successful call
                            await self._log_successful_call(
                                group_id, address, target['dest_chat_id'], 
                                call_result['message_id']
                            )
                            successful_sends += 1
                            logger.info(f"Successfully sent {address[:8]}... to target {target['dest_chat_id']}")
                        else:
                            logger.error(f"Failed to send to target {target['dest_chat_id']}: {call_result.get('error')}")
                            failed_sends += 1
                            
                    except Exception as target_error:
                        logger.error(f"Error sending to target {target['dest_chat_id']}: {target_error}")
                        failed_sends += 1
            
            return {
                'success': True,
                'sent_count': successful_sends,
                'failed_count': failed_sends,
                'targets_count': len(targets),
                'addresses_count': len(addresses)
            }
                
        except Exception as e:
            logger.error(f"Error forwarding tokens to targets: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _get_group_targets(self, group_id: int) -> List[Dict[str, Any]]:
        """Get all targets for a group"""
        try:
            targets = await db.fetch("""
                SELECT * FROM targets WHERE group_id = $1
            """, group_id)
            return [dict(target) for target in targets]
        except Exception as e:
            logger.error(f"Error getting group targets: {e}")
            return []
    
    async def _log_successful_call(self, group_id: int, token_address: str,
                                  target_chat_id: int, message_id: int):
        """Log a successful call to the database"""
        try:
            # Get or create token record first
            token_record = await db.fetchrow("""
                INSERT INTO tokens_tracked (address, source_group_id)
                VALUES ($1, $2)
                ON CONFLICT (address) DO UPDATE SET
                    last_checked_at = NOW(),
                    source_group_id = COALESCE(tokens_tracked.source_group_id, $2)
                RETURNING id, source_group_id
            """, token_address, group_id)

            # Get target record
            target_record = await db.fetchrow("""
                SELECT id, group_id FROM targets WHERE group_id = $1 AND dest_chat_id = $2
            """, group_id, target_chat_id)

            if not target_record:
                logger.warning(f"No target record found for group {group_id} and chat {target_chat_id}")
                return

            # Log to OLD calls table (legacy)
            await db.execute("""
                INSERT INTO calls (group_id, token_id, target_id, userbot_id,
                                 scheduled_at, sent_at, status, message_id)
                VALUES ($1, $2, $3, $4, NOW(), NOW(), 'sent', $5)
            """, target_record['group_id'], token_record['id'],
                target_record['id'], self.userbot_id, message_id)

            # ALSO log to NEW token_call_history table for inspector
            # Get source chat info from group
            group_record = await db.fetchrow("""
                SELECT tg_chat_id, display_name, title FROM groups WHERE id = $1
            """, group_id)

            source_chat_id = group_record['tg_chat_id'] if group_record else group_id
            source_name = (group_record.get('display_name') or group_record.get('title')) if group_record else f"Group {group_id}"

            await db.execute("""
                INSERT INTO token_call_history (
                    token_address,
                    caller_user_id,
                    caller_name,
                    source_chat_id,
                    source_name,
                    source_type,
                    target_chat_id,
                    forwarding_userbot_id,
                    routing_rule_id,
                    curated_alpha_rule_id,
                    market_cap_at_call,
                    call_job_id,
                    forwarded_message_id,
                    called_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW())
            """,
                token_address,           # token_address
                None,                    # caller_user_id (unknown in legacy path)
                None,                    # caller_name (unknown in legacy path)
                source_chat_id,          # source_chat_id
                source_name,             # source_name
                'group',                 # source_type (assume group for legacy)
                target_chat_id,          # target_chat_id
                self.userbot_id,         # forwarding_userbot_id
                None,                    # routing_rule_id (unknown in legacy path)
                None,                    # curated_alpha_rule_id (unknown in legacy path)
                None,                    # market_cap_at_call (unknown in legacy path)
                None,                    # call_job_id (not from queue)
                message_id               # forwarded_message_id
            )

            logger.debug(f"Logged legacy call to both tables: {token_address[:8]}... → {target_chat_id}")

        except Exception as e:
            logger.error(f"Error logging successful call: {e}")
    
    def is_tracked_message(self, chat_id: int, message_id: int) -> bool:
        """Check if a message is being tracked"""
        return self.message_tracker.is_tracked_message(chat_id, message_id)
    
    def get_executor_stats(self) -> Dict[str, Any]:
        """Get call executor statistics"""
        return {
            'userbot_id': self.userbot_id,
            'message_tracker': self.message_tracker.get_stats(),
            'rate_limiter': self.rate_limiter.get_stats()
        }
    
    async def get_call_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent call history for this userbot"""
        try:
            calls = await db.fetch("""
                SELECT c.*, t.address as token_address, ta.dest_chat_id
                FROM calls c
                LEFT JOIN tokens_tracked t ON t.id = c.token_id
                LEFT JOIN targets ta ON ta.id = c.target_id
                WHERE c.userbot_id = $1
                ORDER BY c.sent_at DESC
                LIMIT $2
            """, self.userbot_id, limit)
            
            return [dict(call) for call in calls]
            
        except Exception as e:
            logger.error(f"Error getting call history: {e}")
            return []
    
    async def get_call_stats(self) -> Dict[str, Any]:
        """Get call statistics for this userbot"""
        try:
            stats = await db.fetchrow("""
                SELECT 
                    COUNT(*) as total_calls,
                    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '1 day') as today_calls,
                    COUNT(*) FILTER (WHERE sent_at > NOW() - INTERVAL '1 hour') as hour_calls,
                    COUNT(*) FILTER (WHERE status = 'sent') as successful_calls,
                    COUNT(*) FILTER (WHERE status = 'failed') as failed_calls
                FROM calls
                WHERE userbot_id = $1
            """, self.userbot_id)
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting call stats: {e}")
            return {}
