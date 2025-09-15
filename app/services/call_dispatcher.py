"""
Call Dispatcher Service - Processes job queue and delegates to forwarding bots
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.db import db
from app.models import BotModel
from app.models.call_queue import CallQueueModel
from app.userbot.call_executor import CallExecutor

logger = logging.getLogger(__name__)

class CallDispatcher:
    """Async service that processes call queue jobs and delegates to forwarding userbots"""

    def __init__(self, userbot_manager, polling_interval: int = 2, batch_size: int = 10):
        self.userbot_manager = userbot_manager
        self.polling_interval = polling_interval
        self.batch_size = batch_size
        self.running = False
        self._task: Optional[asyncio.Task] = None

        # Models
        self.bot_model = BotModel(db)
        self.call_queue_model = CallQueueModel(db)

        # Cache for userbot executors
        self.executors: Dict[int, CallExecutor] = {}
        self.executor_cache_time = {}

    async def start(self):
        """Start the call dispatcher service"""
        if self.running:
            logger.warning("Call dispatcher is already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._dispatcher_loop())
        logger.info("Call dispatcher started")

    async def stop(self):
        """Stop the call dispatcher service"""
        if not self.running:
            return

        logger.info("Stopping call dispatcher...")
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                logger.info("Call dispatcher task cancelled")

        # Clean up executor cache
        self.executors.clear()
        self.executor_cache_time.clear()
        logger.info("Call dispatcher stopped")

    async def _dispatcher_loop(self):
        """Main dispatcher loop - polls queue and processes jobs"""
        logger.info(f"Call dispatcher loop started (polling every {self.polling_interval}s, batch size: {self.batch_size})")

        while self.running:
            try:
                # Get pending jobs from queue
                jobs = await self.call_queue_model.get_pending_jobs(limit=self.batch_size)

                if jobs:
                    logger.info(f"[DISPATCHER] Processing batch of {len(jobs)} pending jobs")
                    processed = 0
                    failed = 0

                    for job in jobs:
                        try:
                            success = await self._process_job(job)
                            if success:
                                processed += 1
                            else:
                                failed += 1
                        except Exception as job_error:
                            failed += 1
                            logger.error(f"Error processing job {job['id']}: {job_error}")

                    if processed > 0 or failed > 0:
                        logger.info(f"Batch complete: {processed} processed, {failed} failed")

                # Reset stuck jobs periodically
                await self._reset_stuck_jobs()

                # Clean up old completed jobs
                await self._cleanup_old_jobs()

            except Exception as e:
                logger.error(f"Error in dispatcher loop: {e}")

            # Wait before next poll
            await asyncio.sleep(self.polling_interval)

    async def _process_job(self, job) -> bool:
        """Process a single job from the queue"""
        try:
            job_id = job['id']
            forwarding_userbot_id = job['forwarding_userbot_id']
            token_address = job['token_address']
            target_chat_id = job['target_chat_id']

            logger.info(f"[DISPATCHER] Processing job {job_id}: {token_address[:8]}... → {target_chat_id} via userbot {forwarding_userbot_id}")

            # Mark job as processing
            await self.call_queue_model.mark_processing(job_id)
            logger.debug(f"[DISPATCHER] Job {job_id} marked as processing")

            # Get or create call executor for this userbot
            executor = await self._get_executor(forwarding_userbot_id)
            if not executor:
                logger.error(f"[DISPATCHER] ❌ Job {job_id}: Forwarding userbot {forwarding_userbot_id} not available")
                await self.call_queue_model.mark_failed(job_id, "Forwarding userbot not available")
                return False

            logger.debug(f"[DISPATCHER] Got executor for userbot {forwarding_userbot_id}, executing call...")

            # Execute the call
            result = await executor.send_call_message(
                target_chat_id=target_chat_id,
                token_address=token_address,
                additional_info=job.get('additional_info', ''),
                source_info=job.get('source_info', '')
            )

            # Update job status based on result
            if result['success']:
                await self.call_queue_model.mark_completed(job_id)
                logger.info(f"[DISPATCHER] ✅ Job {job_id} completed: {token_address[:8]}... sent to {target_chat_id}")
                return True
            else:
                error_msg = result.get('error', 'Unknown error')
                await self.call_queue_model.mark_failed(job_id, error_msg)
                logger.warning(f"[DISPATCHER] ❌ Job {job_id} failed: {error_msg}")
                return False

        except Exception as e:
            # Mark job as failed
            await self.call_queue_model.mark_failed(job['id'], f"Processing error: {str(e)}")
            logger.error(f"Error processing job {job['id']}: {e}")
            return False

    async def _get_executor(self, userbot_id: int) -> Optional[CallExecutor]:
        """Get or create a call executor for the specified userbot"""
        try:
            # Check cache first (refresh every 5 minutes)
            if userbot_id in self.executors:
                if time.time() - self.executor_cache_time.get(userbot_id, 0) < 300:
                    return self.executors[userbot_id]
                else:
                    # Cache expired, remove and recreate
                    del self.executors[userbot_id]
                    if userbot_id in self.executor_cache_time:
                        del self.executor_cache_time[userbot_id]

            # Get worker from userbot manager
            worker = self.userbot_manager.get_worker(userbot_id)
            if not worker:
                logger.warning(f"Worker not found for userbot {userbot_id}")
                return None

            if not worker.running:
                logger.warning(f"Worker {userbot_id} is not running")
                return None

            # Get session manager from worker
            session_manager = worker.session_manager
            if not session_manager:
                logger.warning(f"Session manager not available for userbot {userbot_id}")
                return None

            # Create and cache executor
            executor = CallExecutor(userbot_id, session_manager)
            self.executors[userbot_id] = executor
            self.executor_cache_time[userbot_id] = time.time()

            logger.debug(f"Created call executor for userbot {userbot_id}")
            return executor

        except Exception as e:
            logger.error(f"Error getting executor for userbot {userbot_id}: {e}")
            return None

    async def _reset_stuck_jobs(self):
        """Reset jobs that have been in 'processing' state too long"""
        try:
            # Reset jobs processing for more than 5 minutes
            reset_count = await self.call_queue_model.reset_stuck_jobs(minutes_old=5)
            if reset_count > 0:
                logger.info(f"Reset {reset_count} stuck jobs")
        except Exception as e:
            logger.error(f"Error resetting stuck jobs: {e}")

    async def _cleanup_old_jobs(self):
        """Clean up old completed/failed jobs"""
        try:
            # Clean up jobs older than 24 hours (1 day)
            cleanup_count = await self.call_queue_model.cleanup_old_jobs(days_old=1)
            if cleanup_count > 0:
                logger.debug(f"Cleaned up {cleanup_count} old jobs")
        except Exception as e:
            logger.error(f"Error cleaning up old jobs: {e}")

    async def get_stats(self) -> Dict[str, Any]:
        """Get dispatcher statistics"""
        try:
            stats = await self.call_queue_model.get_job_stats()
            stats['running'] = self.running
            stats['active_executors'] = len(self.executors)
            return stats
        except Exception as e:
            logger.error(f"Error getting dispatcher stats: {e}")
            return {'error': str(e)}