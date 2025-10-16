"""
Chart Fetcher - Fetches token chart images by posting CA to random groups and capturing bot replies
"""

import asyncio
import logging
import random
from typing import Optional, Tuple, Dict
from io import BytesIO

from telethon.tl.custom import Message as TelethonMessage
from telethon.errors import FloodWaitError, ChatWriteForbiddenError

logger = logging.getLogger(__name__)


class ChartFetcher:
    """
    Fetches chart images for tokens by posting contract addresses to random groups
    and waiting for chart bot replies.
    """

    def __init__(self, db_pool, userbot_manager):
        """
        Initialize ChartFetcher.

        Args:
            db_pool: Database connection pool
            userbot_manager: UserbotManager instance with active workers
        """
        self.db = db_pool
        self.userbot_manager = userbot_manager

        # Track pending chart requests: {message_id: (Future[bytes], chart_bot_id)}
        self._pending_requests: Dict[int, Tuple[asyncio.Future, int]] = {}

        logger.info("[CHART_FETCH] ChartFetcher initialized")

    async def fetch_chart_for_token(
        self,
        contract_address: str,
        chart_bot_id: int,
        timeout: int = 60
    ) -> Optional[bytes]:
        """
        Post CA to random group, wait for chart bot reply with photo.

        Args:
            contract_address: Token contract address to fetch chart for
            chart_bot_id: Telegram user ID of the chart bot that will reply
            timeout: Maximum seconds to wait for reply (default: 60)

        Returns:
            Photo bytes if successful, None on timeout/error

        Flow:
            1. Pick random chart request group
            2. Pick random available userbot
            3. Post raw CA text to group via Telethon
            4. Store (message_id → Future) in _pending_requests
            5. Wait for chart bot to reply (max 60s)
            6. Download photo bytes from reply
            7. Return bytes or None
        """
        try:
            # Step 1: Get random chart request group
            group_chat_id = await self._get_random_chart_group()
            if not group_chat_id:
                logger.warning("[CHART_FETCH] No chart request groups configured")
                return None

            # Step 2 & 3: Post CA using random userbot
            result = await self._post_ca_with_random_userbot(group_chat_id, contract_address)
            if not result:
                logger.warning(f"[CHART_FETCH] Failed to post CA {contract_address} to group {group_chat_id}")
                return None

            chat_id, message_id = result

            # Step 4: Create Future and register pending request with chart_bot_id
            future = asyncio.Future()
            self._pending_requests[message_id] = (future, chart_bot_id)

            logger.info(
                f"[CHART_FETCH] Posted CA {contract_address} to group {chat_id}, "
                f"message_id={message_id}, waiting for chart bot {chart_bot_id} to reply..."
            )

            try:
                # Step 5: Wait for reply with timeout
                photo_bytes = await asyncio.wait_for(future, timeout=timeout)
                logger.info(
                    f"[CHART_FETCH] ✅ Chart fetched successfully for {contract_address}, "
                    f"size={len(photo_bytes)} bytes"
                )
                return photo_bytes

            except asyncio.TimeoutError:
                logger.warning(
                    f"[CHART_FETCH] ⏱️ Timeout waiting for chart bot {chart_bot_id} "
                    f"to reply to message {message_id} (waited {timeout}s)"
                )
                return None

            finally:
                # Cleanup pending request
                self._pending_requests.pop(message_id, None)

        except Exception as e:
            logger.error(f"[CHART_FETCH] Error fetching chart for {contract_address}: {e}")
            return None

    async def _get_random_chart_group(self) -> Optional[int]:
        """
        Pick random group from chart_request_groups table.

        Returns:
            chat_id (negative integer) or None if no groups configured
        """
        try:
            result = await self.db.fetch(
                "SELECT chat_id FROM chart_request_groups ORDER BY RANDOM() LIMIT 1"
            )

            if not result:
                return None

            chat_id = result[0]['chat_id']
            logger.debug(f"[CHART_FETCH] Selected random chart group: {chat_id}")
            return chat_id

        except Exception as e:
            logger.error(f"[CHART_FETCH] Error getting random chart group: {e}")
            return None

    async def _post_ca_with_random_userbot(
        self,
        chat_id: int,
        contract_address: str
    ) -> Optional[Tuple[int, int]]:
        """
        Post raw CA using random available userbot via Telethon.

        Args:
            chat_id: Target chat ID (negative for groups)
            contract_address: Contract address to post

        Returns:
            (chat_id, message_id) tuple if successful, None on error
        """
        try:
            # Get all available workers
            all_workers = self.userbot_manager.get_all_workers()

            if not all_workers:
                logger.warning("[CHART_FETCH] No userbots available")
                return None

            # Pick random worker
            worker = random.choice(list(all_workers.values()))
            userbot_id = worker.userbot_id

            # Get Telethon client
            client = worker.session_manager.get_client()
            if not client:
                logger.warning(f"[CHART_FETCH] Userbot {userbot_id} client not connected")
                return None

            # Send message with just the CA
            logger.debug(
                f"[CHART_FETCH] Posting CA '{contract_address}' to group {chat_id} "
                f"via userbot {userbot_id}"
            )

            sent_message = await client.send_message(
                chat_id,
                contract_address,
                link_preview=False
            )

            logger.info(
                f"[CHART_FETCH] Posted CA to group {chat_id}, "
                f"message_id={sent_message.id}, userbot={userbot_id}"
            )

            return (chat_id, sent_message.id)

        except FloodWaitError as e:
            logger.error(f"[CHART_FETCH] FloodWait error: must wait {e.seconds} seconds")
            return None

        except ChatWriteForbiddenError:
            logger.error(f"[CHART_FETCH] Bot cannot write to group {chat_id}")
            return None

        except Exception as e:
            logger.error(f"[CHART_FETCH] Error posting CA to group {chat_id}: {e}")
            return None

    async def handle_chart_bot_reply(self, message: TelethonMessage):
        """
        Called by userbot message handler when chart bot replies.

        Flow:
            1. Check if message.reply_to_msg_id exists in _pending_requests
            2. Validate sender matches expected chart_bot_id from stored tuple
            3. If yes, download first photo as bytes via message.download_media(file=bytes)
            4. Resolve the Future with photo bytes
            5. Clean up _pending_requests entry

        Args:
            message: Telethon message object from chart bot
        """
        try:
            # Check if this is a reply we're waiting for
            reply_to_msg_id = message.reply_to_msg_id
            if not reply_to_msg_id:
                return

            pending = self._pending_requests.get(reply_to_msg_id)
            if not pending:
                # Not a reply to our chart request
                return

            future, expected_chart_bot_id = pending

            # Validate this is from the expected chart bot
            if message.sender_id != expected_chart_bot_id:
                logger.debug(
                    f"[CHART_FETCH] Ignoring reply from bot {message.sender_id}, "
                    f"expected {expected_chart_bot_id}"
                )
                return

            # Remove entry upfront so duplicate replies don't attempt to resolve again
            self._pending_requests.pop(reply_to_msg_id, None)

            # Check if future is already resolved (shouldn't happen, but safety check)
            if future.done():
                logger.warning(
                    f"[CHART_FETCH] Future for message {reply_to_msg_id} already resolved"
                )
                return

            # Check if message has photo
            if not message.photo:
                logger.warning(
                    f"[CHART_FETCH] Chart bot {expected_chart_bot_id} replied to {reply_to_msg_id} "
                    f"but message has no photo"
                )
                future.set_result(None)
                return

            # Download photo to bytes
            logger.debug(
                f"[CHART_FETCH] Downloading photo from chart bot reply "
                f"(reply_to={reply_to_msg_id})"
            )

            # Download to BytesIO (in-memory)
            photo_bytes_io = BytesIO()
            await message.download_media(file=photo_bytes_io)
            photo_bytes = photo_bytes_io.getvalue()

            logger.info(
                f"[CHART_FETCH] Downloaded chart photo for message {reply_to_msg_id}, "
                f"size={len(photo_bytes)} bytes"
            )

            # Resolve the Future
            future.set_result(photo_bytes)

        except Exception as e:
            logger.error(
                f"[CHART_FETCH] Error handling chart bot reply "
                f"(reply_to={message.reply_to_msg_id if message else 'unknown'}): {e}"
            )

            # Resolve with None on error
            if message:
                future_entry = self._pending_requests.pop(message.reply_to_msg_id, None)
                if future_entry:
                    future, _ = future_entry
                    if not future.done():
                        future.set_result(None)
