"""
Entity Utils - Telegram entity resolution and timestamp utilities
"""

import logging
import traceback
from datetime import datetime, timezone, timedelta
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

logger = logging.getLogger(__name__)


async def resolve_entity_safely(handler, client, target_chat_id: int):
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


async def post_forward_timestamp(handler, client, entity, destination_channel_id: int, timezone_name: str):
    """Post timestamp after forwarding a message in specified timezone."""
    try:
        # Timezone offsets mapping
        timezone_offsets = {
            'IST': timedelta(hours=5, minutes=30),
            'UTC': timedelta(hours=0),
            'GMT': timedelta(hours=0),
            'EST': timedelta(hours=-5),
            'PST': timedelta(hours=-8),
            'CST': timedelta(hours=-6),
            'JST': timedelta(hours=9),
            'AEST': timedelta(hours=10),
            'CET': timedelta(hours=1)
        }

        offset = timezone_offsets.get(timezone_name, timedelta(hours=5, minutes=30))  # Default to IST
        tz = timezone(offset)
        local_time = datetime.now(tz)

        timestamp_text = f"Forwarded at: {local_time.strftime('%d/%m/%Y %H:%M:%S')} {timezone_name}"

        await client.send_message(
            entity=entity,
            message=timestamp_text
        )

        logger.info(f"[MessageHandler] Posted {timezone_name} timestamp to channel {destination_channel_id}")

    except Exception as e:
        logger.error(f"[MessageHandler] Error posting timestamp: {e}")
        logger.error(f"[MessageHandler] Full traceback: {traceback.format_exc()}")
