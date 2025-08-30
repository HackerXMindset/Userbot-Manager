"""
Userbot Manager - Manages multiple userbot workers using the modular architecture
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional

from app.db import db
from app.models import BotModel
from .worker import UserbotWorker

logger = logging.getLogger(__name__)


class UserbotManager:
    """Manager for all userbot workers using modular components"""
    
    def __init__(self):
        self.workers: Dict[int, UserbotWorker] = {}
        self.bot_model = BotModel(db)
        self._cleanup_task: Optional[asyncio.Task] = None
        self.running = False
    
    async def start_all_workers(self):
        """Start all configured userbot workers"""
        try:
            self.running = True
            
            # Get active userbots from database
            userbots = await self.bot_model.get_active_userbots()
            
            startup_tasks = []
            for userbot in userbots:
                if userbot.get('session_string'):
                    task = self.start_worker(userbot['id'], userbot['session_string'])
                    startup_tasks.append(task)
            
            # Start all workers concurrently
            if startup_tasks:
                await asyncio.gather(*startup_tasks, return_exceptions=True)
            
            # Start background cleanup task
            self._cleanup_task = asyncio.create_task(self._background_cleanup())
            
            logger.info(f"Started {len(self.workers)} userbot workers")
            
        except Exception as e:
            logger.error(f"Error starting userbot workers: {e}")
            raise
    
    async def start_worker(self, userbot_id: int, session_string: str):
        """Start a specific userbot worker"""
        try:
            if userbot_id in self.workers:
                logger.warning(f"Userbot {userbot_id} already running")
                return
            
            # Create and start worker
            worker = UserbotWorker(userbot_id, session_string)
            await worker.start()
            
            # Add to active workers
            self.workers[userbot_id] = worker
            
            logger.info(f"Started userbot worker {userbot_id}")
            
        except Exception as e:
            logger.error(f"Error starting userbot worker {userbot_id}: {e}")
            # Ensure failed worker is not in the dict
            if userbot_id in self.workers:
                del self.workers[userbot_id]
            raise
    
    async def stop_worker(self, userbot_id: int):
        """Stop a specific userbot worker"""
        try:
            if userbot_id in self.workers:
                await self.workers[userbot_id].stop()
                del self.workers[userbot_id]
                
                logger.info(f"Stopped userbot worker {userbot_id}")
            else:
                logger.warning(f"Userbot {userbot_id} not running")
            
        except Exception as e:
            logger.error(f"Error stopping userbot worker {userbot_id}: {e}")
    
    async def restart_worker(self, userbot_id: int):
        """Restart a specific userbot worker"""
        try:
            if userbot_id in self.workers:
                await self.workers[userbot_id].restart()
                logger.info(f"Restarted userbot worker {userbot_id}")
            else:
                # Try to get session and start fresh
                userbot = await self.bot_model.get_by_id(userbot_id)
                if userbot and userbot.get('session_string'):
                    await self.start_worker(userbot_id, userbot['session_string'])
                    logger.info(f"Started userbot worker {userbot_id} from stopped state")
                else:
                    logger.error(f"Cannot restart userbot {userbot_id} - no session data")
            
        except Exception as e:
            logger.error(f"Error restarting userbot worker {userbot_id}: {e}")
    
    async def stop_all_workers(self):
        """Stop all userbot workers"""
        try:
            self.running = False
            
            # Cancel cleanup task
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass
            
            # Stop all workers concurrently
            stop_tasks = []
            for userbot_id in list(self.workers.keys()):
                task = self.stop_worker(userbot_id)
                stop_tasks.append(task)
            
            if stop_tasks:
                await asyncio.gather(*stop_tasks, return_exceptions=True)
            
            logger.info("Stopped all userbot workers")
            
        except Exception as e:
            logger.error(f"Error stopping userbot workers: {e}")
    
    async def get_worker_status(self) -> Dict[str, Any]:
        """Get comprehensive status of all workers"""
        try:
            status = {
                'total_workers': len(self.workers),
                'manager_running': self.running,
                'workers': {}
            }
            
            # Get status from each worker concurrently
            worker_tasks = {}
            for userbot_id, worker in self.workers.items():
                worker_tasks[userbot_id] = worker.get_worker_info()
            
            if worker_tasks:
                results = await asyncio.gather(*worker_tasks.values(), return_exceptions=True)
                
                for userbot_id, result in zip(worker_tasks.keys(), results):
                    if isinstance(result, Exception):
                        status['workers'][userbot_id] = {
                            'error': str(result),
                            'userbot_id': userbot_id
                        }
                    else:
                        status['workers'][userbot_id] = result
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting worker status: {e}")
            return {'error': str(e)}
    
    async def health_check_all(self) -> Dict[str, Any]:
        """Health check all workers"""
        try:
            # Perform health checks concurrently
            health_tasks = {}
            for userbot_id, worker in self.workers.items():
                health_tasks[userbot_id] = worker.health_check()
            
            results = {}
            if health_tasks:
                health_results = await asyncio.gather(*health_tasks.values(), return_exceptions=True)
                
                for userbot_id, result in zip(health_tasks.keys(), health_results):
                    if isinstance(result, Exception):
                        results[userbot_id] = {
                            'healthy': False,
                            'error': str(result)
                        }
                    else:
                        results[userbot_id] = result
            
            # Calculate overall health
            healthy_count = sum(1 for r in results.values() if r.get('healthy', False))
            
            return {
                'total_workers': len(self.workers),
                'healthy_workers': healthy_count,
                'unhealthy_workers': len(self.workers) - healthy_count,
                'manager_running': self.running,
                'details': results
            }
            
        except Exception as e:
            logger.error(f"Error in health check: {e}")
            return {'error': str(e)}
    
    async def process_scheduled_calls(self) -> Dict[str, Any]:
        """Process scheduled calls across all workers"""
        try:
            # Process calls for each worker concurrently
            process_tasks = {}
            for userbot_id, worker in self.workers.items():
                process_tasks[userbot_id] = worker.process_scheduled_calls()
            
            results = {}
            total_processed = 0
            total_failed = 0
            
            if process_tasks:
                process_results = await asyncio.gather(*process_tasks.values(), return_exceptions=True)
                
                for userbot_id, result in zip(process_tasks.keys(), process_results):
                    if isinstance(result, Exception):
                        results[userbot_id] = {'error': str(result)}
                    else:
                        results[userbot_id] = result
                        if result.get('success'):
                            total_processed += result.get('processed', 0)
                            total_failed += result.get('failed', 0)
            
            return {
                'success': True,
                'total_processed': total_processed,
                'total_failed': total_failed,
                'worker_results': results
            }
            
        except Exception as e:
            logger.error(f"Error processing scheduled calls: {e}")
            return {'success': False, 'error': str(e)}
    
    async def cleanup_old_data(self, days_old: int = 30) -> Dict[str, Any]:
        """Clean up old data across all workers"""
        try:
            # Clean up data for each worker concurrently
            cleanup_tasks = {}
            for userbot_id, worker in self.workers.items():
                cleanup_tasks[userbot_id] = worker.cleanup_old_data(days_old)
            
            results = {}
            if cleanup_tasks:
                cleanup_results = await asyncio.gather(*cleanup_tasks.values(), return_exceptions=True)
                
                for userbot_id, result in zip(cleanup_tasks.keys(), cleanup_results):
                    if isinstance(result, Exception):
                        results[userbot_id] = {'error': str(result)}
                    else:
                        results[userbot_id] = result
            
            return {
                'success': True,
                'days_old': days_old,
                'worker_results': results
            }
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _background_cleanup(self):
        """Background task for periodic cleanup"""
        try:
            while self.running:
                try:
                    # Wait 1 hour between cleanups
                    await asyncio.sleep(3600)
                    
                    if not self.running:
                        break
                    
                    logger.info("Starting background cleanup")
                    
                    # Clean up old data (keep 7 days)
                    cleanup_result = await self.cleanup_old_data(days_old=7)
                    
                    if cleanup_result.get('success'):
                        logger.info("Background cleanup completed")
                    else:
                        logger.error(f"Background cleanup failed: {cleanup_result.get('error')}")
                    
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Error in background cleanup: {e}")
                    
        except asyncio.CancelledError:
            logger.info("Background cleanup task cancelled")
    
    def get_worker(self, userbot_id: int) -> Optional[UserbotWorker]:
        """Get a specific worker instance"""
        return self.workers.get(userbot_id)
    
    def get_all_workers(self) -> Dict[int, UserbotWorker]:
        """Get all worker instances"""
        return self.workers.copy()
    
    async def sync_workers_with_database(self):
        """Sync running workers with database configuration"""
        try:
            # Get active userbots from database
            db_userbots = await self.bot_model.get_active_userbots()
            db_userbot_ids = {u['id'] for u in db_userbots if u.get('session_string')}
            
            # Get currently running workers
            running_ids = set(self.workers.keys())
            
            # Start missing workers
            to_start = db_userbot_ids - running_ids
            for userbot_id in to_start:
                userbot = next(u for u in db_userbots if u['id'] == userbot_id)
                await self.start_worker(userbot_id, userbot['session_string'])
            
            # Stop extra workers
            to_stop = running_ids - db_userbot_ids
            for userbot_id in to_stop:
                await self.stop_worker(userbot_id)
            
            logger.info(f"Synced workers: started {len(to_start)}, stopped {len(to_stop)}")
            
        except Exception as e:
            logger.error(f"Error syncing workers with database: {e}")