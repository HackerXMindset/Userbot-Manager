"""
Session Manager - Handles Telegram client session management
"""

import asyncio
import logging
from typing import Optional, Dict, Any
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    AuthKeyError, AuthKeyDuplicatedError, AuthKeyUnregisteredError,
    SessionPasswordNeededError, PhoneCodeExpiredError, PhoneCodeInvalidError,
    FloodWaitError, UnauthorizedError
)

from app.config import settings

logger = logging.getLogger(__name__)

# Set detailed logging for session manager operations
logging.getLogger(__name__).setLevel(logging.DEBUG)


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
        logger.debug(f"[SessionManager] Starting client initialization for userbot {self.userbot_id}")
        logger.debug(f"[SessionManager] Session string length: {len(self.session_string) if self.session_string else 0}")
        logger.debug(f"[SessionManager] API ID: {settings.api_id}, API Hash: {settings.api_hash[:8]}...")

        try:
            logger.debug(f"[SessionManager] Creating TelegramClient with StringSession...")
            self.client = TelegramClient(
                StringSession(self.session_string),
                settings.api_id,
                settings.api_hash
            )

            logger.debug(f"[SessionManager] Starting client connection...")
            await self.client.start()
            self.connected = True
            logger.debug(f"[SessionManager] Client connected successfully")

            # Cache user info
            logger.debug(f"[SessionManager] Fetching user info...")
            me = await self.client.get_me()
            self.userbot_user_id = me.id
            self.userbot_username = me.username

            logger.info(f"[SessionManager] ✅ Session initialized successfully: ID={self.userbot_user_id}, Username=@{self.userbot_username}")
            logger.debug(f"[SessionManager] User details: first_name={me.first_name}, last_name={me.last_name}, phone={me.phone}")
            return True

        except AuthKeyError as e:
            logger.error(f"[SessionManager] ❌ Auth key error for userbot {self.userbot_id}: {e}")
            logger.error(f"[SessionManager] This usually means the session is corrupted or invalid")
            self.connected = False
            return False
        except AuthKeyUnregisteredError as e:
            logger.error(f"[SessionManager] ❌ Auth key unregistered for userbot {self.userbot_id}: {e}")
            logger.error(f"[SessionManager] This means the session was revoked or logged out")
            self.connected = False
            return False
        except UnauthorizedError as e:
            logger.error(f"[SessionManager] ❌ Unauthorized error for userbot {self.userbot_id}: {e}")
            logger.error(f"[SessionManager] This means the session is no longer valid")
            self.connected = False
            return False
        except FloodWaitError as e:
            logger.error(f"[SessionManager] ❌ Flood wait error for userbot {self.userbot_id}: wait {e.seconds} seconds")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"[SessionManager] ❌ Unexpected error initializing client for userbot {self.userbot_id}: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[SessionManager] Full traceback: {traceback.format_exc()}")
            self.connected = False
            return False
    
    async def disconnect_client(self):
        """Disconnect the Telegram client"""
        logger.debug(f"[SessionManager] Disconnecting client for userbot {self.userbot_id}...")
        try:
            if self.client:
                logger.debug(f"[SessionManager] Client exists, calling disconnect...")
                await self.client.disconnect()
                self.client = None
                self.connected = False
                logger.info(f"[SessionManager] ✅ Session disconnected for userbot {self.userbot_id}")
            else:
                logger.debug(f"[SessionManager] No client to disconnect for userbot {self.userbot_id}")
        except Exception as e:
            logger.error(f"[SessionManager] ❌ Error disconnecting client for userbot {self.userbot_id}: {e}")
            import traceback
            logger.error(f"[SessionManager] Full traceback: {traceback.format_exc()}")
    
    def is_connected(self) -> bool:
        """Check if client is connected"""
        connected = self.connected and self.client and self.client.is_connected()
        logger.debug(f"[SessionManager] Connection check for userbot {self.userbot_id}: connected={connected} (self.connected={self.connected}, client_exists={self.client is not None}, client_connected={self.client.is_connected() if self.client else False})")
        return connected
    
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
        logger.debug(f"[SessionManager] Starting health check for userbot {self.userbot_id}")
        try:
            if not self.client:
                logger.debug(f"[SessionManager] Health check failed: Client not initialized")
                return {'healthy': False, 'error': 'Client not initialized'}

            if not self.client.is_connected():
                logger.debug(f"[SessionManager] Health check failed: Client not connected")
                return {'healthy': False, 'error': 'Client not connected'}

            # Try to get self info to verify connection
            logger.debug(f"[SessionManager] Fetching user info for health check...")
            me = await self.client.get_me()

            result = {
                'healthy': True,
                'user_id': me.id,
                'username': me.username,
                'connected': True
            }
            logger.debug(f"[SessionManager] ✅ Health check passed for userbot {self.userbot_id}: {result}")
            return result

        except AuthKeyError as e:
            logger.error(f"[SessionManager] ❌ Health check failed - Auth key error for userbot {self.userbot_id}: {e}")
            return {'healthy': False, 'error': f'Auth key error: {e}'}
        except UnauthorizedError as e:
            logger.error(f"[SessionManager] ❌ Health check failed - Unauthorized for userbot {self.userbot_id}: {e}")
            return {'healthy': False, 'error': f'Unauthorized: {e}'}
        except Exception as e:
            logger.error(f"[SessionManager] ❌ Health check failed for userbot {self.userbot_id}: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[SessionManager] Full traceback: {traceback.format_exc()}")
            return {
                'healthy': False,
                'error': f'{type(e).__name__}: {str(e)}'
            }
    
    async def get_me(self):
        """Get current user info from Telegram"""
        if not self.client:
            raise RuntimeError("Client not initialized")
        return await self.client.get_me()