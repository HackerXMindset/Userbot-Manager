import logging
from telethon import events
from app.db import db
from app.models.notification import NotificationBlacklistModel
from app.models.event import EventModel

logger = logging.getLogger(__name__)

class NotificationHandler:
    def __init__(self, userbot_id: int, session_manager):
        self.userbot_id = userbot_id
        self.session_manager = session_manager
        self.blacklist_model = NotificationBlacklistModel(db)
        self.event_model = EventModel(db)

    async def handle_notification_event(self, event, event_type: str):
        if await self.blacklist_model.is_blacklisted(event.sender_id):
            logger.debug(f"Ignoring {event_type} from blacklisted user {event.sender_id}")
            return

        me = await self.session_manager.get_me()
        if not me:
            return
            
        # Ignore self-replies/mentions
        if event.sender_id == me.id:
            return

        chat = await event.get_chat()
        if hasattr(chat, 'title') and chat.title:
            chat_title = chat.title
        else:
            chat_title = f"{chat.first_name or ''} {chat.last_name or ''}".strip() or f"User {event.chat_id}"

        payload = {
            "event_type": event_type,
            "user_id": event.sender_id,
            "chat_id": event.chat_id,
            "chat_title": chat_title,
            "message_id": event.id,
            "message_text": event.text,
            "userbot_id": self.userbot_id,
            "userbot_username": me.username,
        }
        
        await self.event_model.create_event(
            kind=f"notification_{event_type}",
            src_chat_id=event.chat_id,
            src_msg_id=event.id,
            user_id=event.sender_id,
            payload=payload,
        )
        logger.info(f"Created notification event for {event_type} from {event.sender_id}")
