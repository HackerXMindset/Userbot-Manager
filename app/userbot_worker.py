import asyncio
import logging
from typing import Dict, Any, Optional, List

# Import modular components
from app.userbot import UserbotWorker as ModularUserbotWorker, UserbotManager as ModularUserbotManager

logger = logging.getLogger(__name__)

# Backward compatibility aliases - redirect to modular implementations

class UserbotWorker:
    """Backward compatibility wrapper for the modular UserbotWorker"""
    
    def __init__(self, userbot_id: int, session_string: str):
        # Create modular worker instance
        self._modular_worker = ModularUserbotWorker(userbot_id, session_string)
        
        # Expose common attributes for backward compatibility
        self.userbot_id = userbot_id
        self.session_string = session_string
        self.running = False
        
        # Legacy attribute aliases
        self.sent_message_ids = set()  # Maintained for compatibility
        self.userbot_username = None
        self.userbot_user_id = None
    
    async def start(self):
        """Start the userbot worker"""
        try:
            await self._modular_worker.start()
            self.running = self._modular_worker.running
            
            # Update legacy attributes for compatibility
            user_info = self._modular_worker.session_manager.get_user_info()
            self.userbot_user_id = user_info.get('user_id')
            self.userbot_username = user_info.get('username')
            
        except Exception as e:
            self.running = False
            raise
    
    async def stop(self):
        """Stop the userbot worker"""
        try:
            await self._modular_worker.stop()
            self.running = self._modular_worker.running
        except Exception as e:
            logger.error(f"Error stopping userbot: {e}")
            raise
    
    # Legacy method - now handled by modular message handler
    async def _setup_event_handlers(self, groups: List[Dict[str, Any]]):
        """Legacy method - event handlers are now managed by modular components"""
        logger.debug("Event handlers are managed by modular message handler")
    
    # Legacy method - now handled by modular message handler
    async def _handle_source_message(self, event, is_edit: bool = False):
        """Legacy method - source message handling is now managed by modular components"""
        logger.debug("Source message handling is managed by modular message handler")
    
    # Legacy method - now handled by modular call executor
    async def _forward_tokens_to_targets(self, group_id: int, addresses: List[str], source_event):
        """Legacy method - token forwarding is now managed by modular components"""
        logger.debug("Token forwarding is managed by modular call executor")
    
    # Legacy method - now handled by modular utils
    def _extract_solana_addresses(self, text: str) -> List[str]:
        """Legacy method - address extraction is now managed by modular utils"""
        components = self._modular_worker.get_components()
        return components['message_handler'].utils.extract_solana_addresses(text)
    # Legacy method - now handled by modular utils
    def _get_message_text(self, message) -> str:
        """Legacy method - message text extraction is now managed by modular utils"""
        components = self._modular_worker.get_components()
        return components['message_handler'].utils.get_message_text(message)
    # Legacy method - now handled by modular utils  
    def _get_user_name(self, sender) -> str:
        """Legacy method - user name extraction is now managed by modular utils"""
        components = self._modular_worker.get_components()
        return components['message_handler'].utils.get_user_name(sender)
    async def send_call_message(self, target_chat_id: int, token_address: str, 
                               additional_info: str = "", source_info: str = "") -> Dict[str, Any]:
        """Send a call message to a target chat - delegates to modular worker"""
        try:
            result = await self._modular_worker.send_call_message(
                target_chat_id, token_address, additional_info, source_info
            )
            
            # Update legacy tracking for backward compatibility
            if result.get('success') and result.get('message_id'):
                self.sent_message_ids.add((target_chat_id, result['message_id']))
            
            return result
        except Exception as e:
            logger.error(f"Error sending call message: {e}")
            return {'success': False, 'error': str(e)}
    async def refresh_sources(self):
        """Refresh source monitoring - delegates to modular worker"""
        try:
            return await self._modular_worker.refresh_sources()
        except Exception as e:
            logger.error(f"Error refreshing sources: {e}")
            raise
    
    async def get_worker_info(self) -> Dict[str, Any]:
        """Get worker information - delegates to modular worker"""
        try:
            return await self._modular_worker.get_worker_info()
        except Exception as e:
            logger.error(f"Error getting worker info: {e}")
            return {'userbot_id': self.userbot_id, 'error': str(e)}
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check - delegates to modular worker"""
        try:
            return await self._modular_worker.health_check()
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {'healthy': False, 'error': str(e)}

class UserbotManager:
    """Backward compatibility wrapper for the modular UserbotManager"""
    
    def __init__(self):
        # Create modular manager instance
        self._modular_manager = ModularUserbotManager()
        
        # Maintain legacy attributes for backward compatibility  
        self.workers: Dict[int, UserbotWorker] = {}
    
    async def start_all_workers(self):
        """Start all configured userbot workers - delegates to modular manager"""
        try:
            await self._modular_manager.start_all_workers()
            
            # Update legacy workers dict for backward compatibility
            modular_workers = self._modular_manager.get_all_workers()
            self.workers = {uid: UserbotWorker(uid, w.session_string) for uid, w in modular_workers.items()}
            
        except Exception as e:
            logger.error(f"Error starting userbot workers: {e}")
            raise
    async def start_worker(self, userbot_id: int, session_string: str):
        """Start a specific userbot worker - delegates to modular manager"""
        try:
            await self._modular_manager.start_worker(userbot_id, session_string)
            
            # Update legacy workers dict for backward compatibility
            if userbot_id not in self.workers:
                wrapper = UserbotWorker(userbot_id, session_string)
                wrapper.running = True
                self.workers[userbot_id] = wrapper
            
        except Exception as e:
            logger.error(f"Error starting userbot worker {userbot_id}: {e}")
            raise
    async def stop_worker(self, userbot_id: int):
        """Stop a specific userbot worker - delegates to modular manager"""
        try:
            await self._modular_manager.stop_worker(userbot_id)
            
            # Update legacy workers dict for backward compatibility
            if userbot_id in self.workers:
                del self.workers[userbot_id]
            
        except Exception as e:
            logger.error(f"Error stopping userbot worker {userbot_id}: {e}")
    async def stop_all_workers(self):
        """Stop all userbot workers - delegates to modular manager"""
        try:
            await self._modular_manager.stop_all_workers()
            
            # Clear legacy workers dict
            self.workers.clear()
            
        except Exception as e:
            logger.error(f"Error stopping userbot workers: {e}")
    async def get_worker_status(self) -> Dict[str, Any]:
        """Get status of all workers - delegates to modular manager"""
        try:
            return await self._modular_manager.get_worker_status()
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            return {'error': str(e)}
    async def health_check_all(self) -> Dict[str, Any]:
        """Health check all workers - delegates to modular manager"""
        try:
            return await self._modular_manager.health_check_all()
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {'error': str(e)}
