"""
Userbot Worker - Main orchestrator for userbot operations using modular components
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List

from app.db import db
from app.models import BotModel, GroupModel
from .session_manager import SessionManager
from .message_handler import MessageHandler
from .event_processor import EventProcessor
from .pnl_tracker import PnlTracker

logger = logging.getLogger(__name__)


class UserbotWorker:
    """Main userbot worker that orchestrates all components"""
    
    def __init__(self, userbot_id: int, session_string: str):
        self.userbot_id = userbot_id
        self.session_string = session_string
        self.running = False
        
        # Models
        self.bot_model = BotModel(db)
        self.group_model = GroupModel(db)
        
        # Core components
        self.session_manager = SessionManager(userbot_id, session_string)
        self.message_handler = MessageHandler(userbot_id, self.session_manager)
        self.event_processor = EventProcessor(userbot_id)
        self.pnl_tracker = PnlTracker(userbot_id, self.session_manager)
    
    async def start(self):
        """Start the userbot worker"""
        if self.running:
            logger.warning(f"Userbot {self.userbot_id} already running")
            return
        
        try:
            # Initialize session
            if not await self.session_manager.initialize_client():
                raise RuntimeError("Failed to initialize Telegram client")
            
            # Get user info
            user_info = self.session_manager.get_user_info()
            logger.info(f"Userbot initialized: ID={user_info['user_id']}, Username=@{user_info['username']}")
            
            # Get assigned groups
            assigned_groups = await self.bot_model.get_assigned_groups(self.userbot_id)
            
            # Setup message handlers
            await self.message_handler.setup_event_handlers(assigned_groups)
            
            # Start PNL tracker
            await self.pnl_tracker.start()
            
            # Update bot status
            await self.bot_model.set_status(self.userbot_id, 'active')
            
            self.running = True
            
            # Create system event
            await self.event_processor.create_system_event(
                'userbot_started',
                {
                    'user_id': user_info['user_id'],
                    'username': user_info['username'],
                    'assigned_groups': len(assigned_groups)
                }
            )
            
            logger.info(f"Userbot {self.userbot_id} started monitoring {len(assigned_groups)} groups")
            
        except Exception as e:
            logger.error(f"Error starting userbot {self.userbot_id}: {e}")
            await self.bot_model.set_status(self.userbot_id, 'error')
            
            # Create error event
            await self.event_processor.create_system_event(
                'connection_error',
                {'error': str(e)},
                user_id=None
            )
            
            raise

    def invalidate_cache(self):
        """Invalidates the message handler's cache."""
        self.message_handler.invalidate_cache()
    
    async def stop(self):
        """Stop the userbot worker"""
        if not self.running:
            return
        
        try:
            self.running = False
            
            # Stop PNL tracker
            await self.pnl_tracker.stop()
            
            # Disconnect session
            await self.session_manager.disconnect_client()
            
            # Update bot status
            await self.bot_model.set_status(self.userbot_id, 'inactive')
            
            # Create system event
            await self.event_processor.create_system_event(
                'userbot_stopped',
                {'clean_shutdown': True}
            )
            
            logger.info(f"Userbot {self.userbot_id} stopped")
            
        except Exception as e:
            logger.error(f"Error stopping userbot {self.userbot_id}: {e}")
    
    async def send_call_message(self, target_chat_id: int, token_address: str, 
                               additional_info: str = "", source_info: str = "") -> Dict[str, Any]:
        """Send a call message (backward compatibility)"""
        try:
            return await self.message_handler.send_manual_call(
                target_chat_id, token_address, source_info
            )
        except Exception as e:
            logger.error(f"Error sending call message: {e}")
            return {'success': False, 'error': str(e)}
    
    async def process_scheduled_calls(self) -> Dict[str, Any]:
        """Process scheduled calls"""
        try:
            return await self.message_handler.process_scheduled_calls()
        except Exception as e:
            logger.error(f"Error processing scheduled calls: {e}")
            return {'success': False, 'error': str(e)}
    
    async def get_worker_info(self) -> Dict[str, Any]:
        """Get comprehensive worker information"""
        try:
            # Get basic info
            user_info = self.session_manager.get_user_info()
            assigned_groups = await self.bot_model.get_assigned_groups(self.userbot_id)
            
            # Get component statistics
            message_stats = await self.message_handler.get_message_stats()
            event_stats = await self.event_processor.get_event_stats()
            
            return {
                'userbot_id': self.userbot_id,
                'running': self.running,
                'user_info': user_info,
                'assigned_groups': len(assigned_groups),
                'groups': [{
                    'id': g['id'],
                    'title': g['title'],
                    'chat_id': g['tg_chat_id']
                } for g in assigned_groups],
                'statistics': {
                    'messages': message_stats,
                    'events': event_stats
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting worker info: {e}")
            return {
                'userbot_id': self.userbot_id,
                'running': self.running,
                'error': str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform comprehensive health check"""
        try:
            # Check session health
            session_health = await self.session_manager.health_check()
            
            if not session_health['healthy']:
                return session_health
            
            # Check component health
            components = self.message_handler.get_components()
            component_stats = {}
            
            for name, component in components.items():
                if hasattr(component, 'get_stats'):
                    try:
                        component_stats[name] = await component.get_stats()
                    except:
                        component_stats[name] = {'status': 'unknown'}
            
            return {
                'healthy': True,
                'userbot_id': self.userbot_id,
                'session': session_health,
                'running': self.running,
                'components': component_stats
            }
            
        except Exception as e:
            logger.error(f"Health check failed for userbot {self.userbot_id}: {e}")
            return {
                'healthy': False,
                'userbot_id': self.userbot_id,
                'error': str(e)
            }
    
    async def cleanup_old_data(self, days_old: int = 30) -> Dict[str, Any]:
        """Clean up old data across all components"""
        try:
            # Clean up message handler data
            message_cleanup = await self.message_handler.cleanup_old_data(days_old)
            
            # Clean up events
            events_cleaned = await self.event_processor.cleanup_old_events(days_old // 4)  # Keep events for shorter time
            
            return {
                'success': True,
                'message_cleanup': message_cleanup,
                'events_cleaned': events_cleaned,
                'days_old': days_old
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return {'success': False, 'error': str(e)}
    
    def get_components(self) -> Dict[str, Any]:
        """Get access to internal components for advanced usage"""
        return {
            'session_manager': self.session_manager,
            'message_handler': self.message_handler,
            'event_processor': self.event_processor,
            'models': {
                'bot_model': self.bot_model,
                'group_model': self.group_model
            }
        }
    
    async def restart(self):
        """Restart the userbot worker"""
        try:
            logger.info(f"Restarting userbot {self.userbot_id}")
            
            # Stop and start
            await self.stop()
            await asyncio.sleep(2)  # Brief pause
            await self.start()
            
            logger.info(f"Userbot {self.userbot_id} restarted successfully")
            
        except Exception as e:
            logger.error(f"Error restarting userbot {self.userbot_id}: {e}")
            raise
    
    async def refresh_sources(self):
        """Refresh source monitoring by re-setting up event handlers"""
        if not self.running:
            logger.warning(f"Cannot refresh sources - userbot {self.userbot_id} not running")
            return
        
        try:
            logger.info(f"Refreshing sources for userbot {self.userbot_id}")
            
            # Get current assigned groups
            assigned_groups = await self.bot_model.get_assigned_groups(self.userbot_id)
            
            # Re-setup event handlers with fresh source data
            await self.message_handler.setup_event_handlers(assigned_groups)
            
            logger.info(f"Successfully refreshed sources for userbot {self.userbot_id}")
            
        except Exception as e:
            logger.error(f"Error refreshing sources for userbot {self.userbot_id}: {e}")
            raise