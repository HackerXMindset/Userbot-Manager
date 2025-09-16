#!/usr/bin/env python3
"""
Main application runner for the Telegram Bot Management System
"""

import asyncio
import signal
import sys
import os
import logging
from pathlib import Path
from typing import Optional, List

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import settings
from app.db import db
from app.logging_conf import setup_logging
from app.management_bot import ManagementBot
from app.scheduler import Scheduler
from app.events import EventRouter
from app.dex import get_dex_service
from app.userbot.manager import UserbotManager
from app.services.call_dispatcher import CallDispatcher

logger = logging.getLogger(__name__)

class SystemManager:
    """Main system manager that orchestrates all components"""
    
    def __init__(self):
        self.components = {}
        self.running = False
        self.shutdown_event = asyncio.Event()
    
    async def initialize(self):
        """Initialize all system components"""
        logger.info("Initializing Telegram Bot Management System...")
        
        try:
            # Initialize database connection
            logger.info("Connecting to database...")
            await db.connect()
            logger.info("Database connected successfully")
            
            # Initialize core services
            logger.info("Initializing core services...")
            
            # Event router (must be first)
            self.components['event_router'] = EventRouter()
            
            # DexScreener service
            self.components['dex_service'] = get_dex_service()
            
            
            # Scheduler
            self.components['scheduler'] = Scheduler()
            
            # Userbot manager
            self.components['userbot_manager'] = UserbotManager()

            # Management bot
            self.components['management_bot'] = ManagementBot()

            # Call dispatcher (requires userbot manager and management bot)
            self.components['call_dispatcher'] = CallDispatcher(
                self.components['userbot_manager'], 
                self.components['management_bot']
            )

            # Pass userbot_manager to dex_service
            self.components['dex_service'].set_userbot_manager(self.components['userbot_manager'])
            self.components['event_router'].set_management_bot(self.components['management_bot'])
            self.components['management_bot'].set_system_manager(self)
            
            logger.info("All components initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize system: {e}")
            raise
    
    async def start(self):
        """Start all system components"""
        if self.running:
            logger.warning("System is already running")
            return
        
        logger.info("Starting system components...")
        
        try:
            # Start services in order
            start_order = [
                'event_router',
                'dex_service',
                'scheduler',
                'userbot_manager',
                'call_dispatcher'
            ]
            
            for component_name in start_order:
                component = self.components.get(component_name)
                if component and hasattr(component, 'start'):
                    logger.info(f"Starting {component_name}...")
                    await component.start()
                    logger.info(f"{component_name} started")
            
            # Start userbot workers
            logger.info("Starting userbot workers...")
            await self.components['userbot_manager'].start_all_workers()
            
            self.running = True
            logger.info("All system components started successfully")
            
            # Start management bot (blocking)
            logger.info("Starting management bot...")
            management_bot_task = asyncio.create_task(
                self.components['management_bot'].run(self.shutdown_event)
            )
            
            # Wait for shutdown signal or management bot to stop
            await management_bot_task
            
        except Exception as e:
            logger.error(f"Error starting system: {e}")
            raise
    
    async def stop(self):
        """Stop all system components gracefully"""
        if not self.running:
            return
        
        logger.info("Shutting down system components...")
        
        try:
            # Stop components in reverse order
            stop_order = [
                'userbot_manager',
                'scheduler',
                'dex_service',
                'event_router'
            ]
            
            for component_name in stop_order:
                component = self.components.get(component_name)
                if component and hasattr(component, 'stop'):
                    try:
                        logger.info(f"Stopping {component_name}...")
                        await component.stop()
                        logger.info(f"{component_name} stopped")
                    except Exception as e:
                        logger.error(f"Error stopping {component_name}: {e}")
            
            # Close database connection
            logger.info("Closing database connection...")
            await db.disconnect()
            
            self.running = False
            logger.info("System shutdown complete")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
    
    def signal_shutdown(self):
        """Signal shutdown from signal handler"""
        logger.info("Shutdown signal received")
        self.shutdown_event.set()
    
    async def get_system_status(self) -> dict:
        """Get overall system status"""
        status = {
            'running': self.running,
            'components': {}
        }
        
        for name, component in self.components.items():
            try:
                if hasattr(component, 'running'):
                    status['components'][name] = {
                        'running': component.running,
                        'status': 'healthy' if component.running else 'stopped'
                    }
                else:
                    status['components'][name] = {
                        'status': 'unknown'
                    }
            except Exception as e:
                status['components'][name] = {
                    'status': 'error',
                    'error': str(e)
                }
        
        return status

async def main():
    """Main entry point"""
    
    # Setup logging
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_file = os.getenv('LOG_FILE')
    
    setup_logging(log_level=log_level, log_file=log_file)
    
    logger.info("="*60)
    logger.info("Telegram Bot Management System")
    logger.info("="*60)
    
    # Validate configuration
    try:
        logger.info("Validating configuration...")
        
        # Check required settings
        required_settings = [
            'admin_telegram_ids_list',
            'mgmt_bot_token', 
            'api_id',
            'api_hash',
            'supabase_pooler_url'
        ]
        
        missing = []
        for setting in required_settings:
            if not getattr(settings, setting, None):
                missing.append(setting.upper())
        
        if missing:
            logger.error(f"Missing required settings: {', '.join(missing)}")
            logger.error("Please check your .env file")
            return 1
        
        logger.info("Configuration validated successfully")
        
    except Exception as e:
        logger.error(f"Configuration error: {e}")
        return 1
    
    # Initialize system manager
    system_manager = SystemManager()
    
    # Setup signal handlers
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        system_manager.signal_shutdown()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize and start system
        await system_manager.initialize()
        await system_manager.start()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"System error: {e}", exc_info=True)
        return 1
    finally:
        # Ensure clean shutdown
        await system_manager.stop()
    
    logger.info("System exited successfully")
    return 0

def run_system():
    """Run the system with proper error handling"""
    try:
        if sys.platform == 'win32':
            # Windows-specific event loop policy
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        return asyncio.run(main())
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
        return 0
    except Exception as e:
        print(f"Fatal error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run_system())