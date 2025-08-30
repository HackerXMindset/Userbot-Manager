import asyncio
import logging
from typing import Dict, Any, Optional
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import settings
from app.models import NotificationModel
from app.db import db

logger = logging.getLogger(__name__)

class NotificationSender:
    """Service for sending notifications through the management bot"""
    
    def __init__(self):
        self.bot = Bot(token=settings.mgmt_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.notification_model = NotificationModel(db)
    
    async def send_notification(self, event: Dict[str, Any]) -> bool:
        """Send a notification for an event"""
        try:
            # Get notification channel
            channel_id = await self.notification_model.get_notification_channel()
            
            if not channel_id:
                logger.debug("No notification channel configured - skipping notification")
                return False
            
            # Format message based on event type
            message = self._format_event_message(event)
            
            if not message:
                logger.debug(f"No message formatted for event type {event.get('kind')}")
                return False
            
            # Send the message
            try:
                await self.bot.send_message(chat_id=channel_id, text=message)
                logger.debug(f"Sent notification for {event.get('kind')} event to channel {channel_id}")
                return True
            except Exception as send_error:
                if "chat not found" in str(send_error).lower():
                    logger.warning(f"Notification channel {channel_id} not found or bot has no access. Please reconfigure the channel.")
                elif "forbidden" in str(send_error).lower():
                    logger.warning(f"Bot doesn't have permission to send messages to channel {channel_id}")
                else:
                    logger.error(f"Error sending message to channel {channel_id}: {send_error}")
                return False
            
        except Exception as e:
            logger.error(f"Error in notification sender: {e}")
            return False
    
    def _format_event_message(self, event: Dict[str, Any]) -> Optional[str]:
        """Format event into a notification message"""
        try:
            event_kind = event.get('kind')
            payload = event.get('payload', {})
            
            if isinstance(payload, str):
                import json
                payload = json.loads(payload)
            
            if event_kind == 'reply':
                return self._format_reply_message(event, payload)
            elif event_kind == 'mention':
                return self._format_mention_message(event, payload)
            elif event_kind == 'dm':
                return self._format_dm_message(event, payload)
            elif event_kind == 'test':
                return self._format_test_message(event, payload)
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error formatting event message: {e}")
            return None
    
    def _format_reply_message(self, event: Dict[str, Any], payload: Dict[str, Any]) -> str:
        """Format reply event message"""
        message = f"💬 <b>REPLY DETECTED</b>\n\n"
        message += f"Chat: {payload.get('chat_title', 'Unknown')}\n"
        message += f"User: {payload.get('user_name', 'Unknown')}\n"
        message += f"User ID: <code>{event.get('user_id', 'Unknown')}</code>\n"
        
        reply_to_text = payload.get('reply_to_text', '')
        if reply_to_text:
            truncated_reply = reply_to_text[:100] + "..." if len(reply_to_text) > 100 else reply_to_text
            message += f"Reply to: {truncated_reply}\n"
        
        message_text = payload.get('message_text', '')
        if message_text:
            truncated_text = message_text[:200] + "..." if len(message_text) > 200 else message_text
            message += f"\nMessage: {truncated_text}\n"
        
        if event.get('created_at'):
            message += f"\nTime: {event['created_at'].strftime('%H:%M:%S')}"
        
        return message
    
    def _format_mention_message(self, event: Dict[str, Any], payload: Dict[str, Any]) -> str:
        """Format mention event message"""
        message = f"📢 <b>MENTION DETECTED</b>\n\n"
        message += f"Chat: {payload.get('chat_title', 'Unknown')}\n"
        message += f"User: {payload.get('user_name', 'Unknown')}\n"
        message += f"User ID: <code>{event.get('user_id', 'Unknown')}</code>\n"
        
        message_text = payload.get('message_text', '')
        if message_text:
            truncated_text = message_text[:200] + "..." if len(message_text) > 200 else message_text
            message += f"\nMessage: {truncated_text}\n"
        
        if event.get('created_at'):
            message += f"\nTime: {event['created_at'].strftime('%H:%M:%S')}"
        
        return message
    
    def _format_dm_message(self, event: Dict[str, Any], payload: Dict[str, Any]) -> str:
        """Format DM event message"""
        message = f"💌 <b>DIRECT MESSAGE</b>\n\n"
        message += f"From: {payload.get('user_name', 'Unknown')}\n"
        message += f"User ID: <code>{event.get('user_id', 'Unknown')}</code>\n"
        
        message_text = payload.get('message_text', '')
        if message_text:
            truncated_text = message_text[:300] + "..." if len(message_text) > 300 else message_text
            message += f"\nMessage: {truncated_text}\n"
        
        if event.get('created_at'):
            message += f"\nTime: {event['created_at'].strftime('%H:%M:%S')}"
        
        return message
    
    def _format_test_message(self, event: Dict[str, Any], payload: Dict[str, Any]) -> str:
        """Format test notification message"""
        message = f"🧪 <b>TEST NOTIFICATION</b>\n\n"
        message += f"From: {payload.get('user_name', 'Test User')}\n"
        message += f"Chat: {payload.get('chat_title', 'Management Bot')}\n"
        message += f"Message: {payload.get('message_text', 'Test notification message')}\n"
        message += f"\nIf you see this, notifications are working correctly! ✅"
        
        return message
    
    async def test_channel_access(self, channel_id: int) -> Dict[str, Any]:
        """Test if bot can send messages to a channel"""
        try:
            # Try to send a test message
            test_message = "🧪 <b>Channel Access Test</b>\n\nThis is a test message to verify the bot can send notifications to this channel."
            await self.bot.send_message(chat_id=channel_id, text=test_message)
            
            return {
                'success': True,
                'message': 'Channel access verified successfully'
            }
        except Exception as e:
            error_msg = str(e).lower()
            if "chat not found" in error_msg:
                return {
                    'success': False,
                    'error': 'Channel not found. Please check the channel ID.'
                }
            elif "forbidden" in error_msg:
                return {
                    'success': False,
                    'error': 'Bot has no permission to send messages to this channel. Please add the bot as an admin.'
                }
            else:
                return {
                    'success': False,
                    'error': f'Error: {str(e)}'
                }
    
    async def close(self):
        """Close the bot session"""
        try:
            await self.bot.session.close()
        except Exception as e:
            logger.error(f"Error closing notification sender: {e}")

# Global notification sender instance
notification_sender = NotificationSender()