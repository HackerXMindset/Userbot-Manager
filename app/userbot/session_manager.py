"""
Session Manager - Handles Telegram client session management
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.sessions import StringSession

from app.config import settings

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages Telegram client sessions and connections"""
    
    def __init__(self, userbot_id: int, session_string: str):
        self.userbot_id = userbot_id
        self.session_string = session_string
        self.client: Optional[TelegramClient] = None
        self.connected = False
        
        # User info cache
        self.userbot_username: Optional[str] = None
        self.userbot_user_id: Optional[int] = None
    
    async def initialize_client(self) -> bool:
        """Initialize and connect the Telegram client"""
        try:
            self.client = TelegramClient(
                StringSession(self.session_string),
                settings.api_id,
                settings.api_hash
            )
            
            await self.client.start()
            self.connected = True
            
            # Cache user info
            me = await self.client.get_me()
            self.userbot_user_id = me.id
            self.userbot_username = me.username
            
            logger.info(f"Session initialized: ID={self.userbot_user_id}, Username=@{self.userbot_username}")
            return True
            
        except Exception as e:
            logger.error(f"Error initializing client for userbot {self.userbot_id}: {e}")
            self.connected = False
            return False
    
    async def disconnect_client(self):
        """Disconnect the Telegram client"""
        try:
            if self.client:
                await self.client.disconnect()
                self.client = None
                self.connected = False
                logger.info(f"Session disconnected for userbot {self.userbot_id}")
        except Exception as e:
            logger.error(f"Error disconnecting client: {e}")
    
    def is_connected(self) -> bool:
        """Check if client is connected"""
        return self.connected and self.client and self.client.is_connected()
    
    def get_client(self) -> Optional[TelegramClient]:
        """Get the Telegram client instance"""
        return self.client if self.is_connected() else None
    
    def get_user_info(self) -> Dict[str, Any]:
        """Get cached user information"""
        return {
            'user_id': self.userbot_user_id,
            'username': self.userbot_username,
            'connected': self.is_connected()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the session"""
        try:
            if not self.client:
                return {'healthy': False, 'error': 'Client not initialized'}
            
            if not self.client.is_connected():
                return {'healthy': False, 'error': 'Client not connected'}
            
            # Try to get self info to verify connection
            me = await self.client.get_me()
            
            return {
                'healthy': True,
                'user_id': me.id,
                'connected': True
            }
            
        except Exception as e:
            logger.error(f"Health check failed for userbot {self.userbot_id}: {e}")
            return {
                'healthy': False,
                'error': str(e)
            }
    
    async def get_me(self):
        """Get current user info from Telegram"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        return await self.client.get_me()