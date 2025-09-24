"""
Call Dispatcher Service - Processes job queue and delegates to forwarding bots
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta

from app.db import db
from app.models import BotModel
from app.models.call_queue import CallQueueModel
from app.models.template import TemplateAssignmentModel
from app.models.token_call_history import TokenCallHistoryModel
from app.userbot.call_executor import CallExecutor
from app.services.placeholder_service import PlaceholderService

logger = logging.getLogger(__name__)

class CallDispatcher:
    """Async service that processes call queue jobs and delegates to forwarding userbots"""

    def __init__(self, userbot_manager, management_bot, polling_interval: int = 2, batch_size: int = 10):
        self.userbot_manager = userbot_manager
        self.management_bot = management_bot
        self.polling_interval = polling_interval
        self.batch_size = batch_size
        self.running = False
        self._task: Optional[asyncio.Task] = None

        # Models
        self.bot_model = BotModel(db)
        self.call_queue_model = CallQueueModel(db)
        self.assignment_model = TemplateAssignmentModel(db)
        self.call_history_model = TokenCallHistoryModel(db)

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
        job_id = job['id']
        try:
            forwarding_userbot_id = job['forwarding_userbot_id']
            token_address = job['token_address']
            target_chat_id = job['target_chat_id']
            # --- NEW SIMPLIFIED TEMPLATE LOGIC ---
            message_content = token_address
            use_mgmt_bot = False
            template_record = None
            target_group_id = None

            try:
                # At the moment of dispatch, find the group_id from the target_chat_id.
                group_record = await db.fetchrow("SELECT id FROM groups WHERE tg_chat_id = $1", target_chat_id)
                if group_record:
                    target_group_id = group_record['id']
                    logger.debug(f"Dispatcher found group_id {target_group_id} for chat {target_chat_id}")
                    template_record = await self.assignment_model.get_template_for_group(target_group_id)
            except Exception as e:
                logger.error(f"Error looking up template for chat {target_chat_id}: {e}")
            # --- END NEW LOGIC ---

            placeholders = {}
            if template_record:
                logger.info(f"Found custom template '{template_record['name']}' for group {target_group_id}")
                job_context = dict(job)
                
                placeholder_service = PlaceholderService(token_address, job_context)
                placeholders = await placeholder_service.get_all_placeholders()
                message_content = placeholder_service.format_template(template_record['template_text'], placeholders)
                use_mgmt_bot = template_record.get('use_management_bot', False)
            
            logger.debug(f"Final message content for job {job_id}:\n{message_content}")

            success = False
            error_msg = "Unknown error"

            if use_mgmt_bot:
                logger.info(f"Sending job {job_id} via Management Bot.")
                try:
                    await self.management_bot.bot.send_message(
                        chat_id=target_chat_id,
                        text=message_content,
                        disable_web_page_preview=True
                    )
                    success = True
                except Exception as e:
                    error_msg = f"Mgmt bot send failed: {e}"
                    logger.error(f"[DISPATCHER] ❌ {error_msg}")
            else:
                logger.info(f"Sending job {job_id} via Userbot {forwarding_userbot_id}.")
                executor = await self._get_executor(forwarding_userbot_id)
                if executor:
                    result = await executor.send_call_message(
                        target_chat_id=target_chat_id,
                        message=message_content,
                        token_address=token_address
                    )
                    success = result.get('success', False)
                    if not success:
                        error_msg = result.get('error', 'Userbot execution failed')
                else:
                    error_msg = f"Userbot {forwarding_userbot_id} not available"
                    logger.error(f"[DISPATCHER] ❌ Job {job_id}: {error_msg}")

            # Update job status
            if success:
                # Log successful call to history
                try:
                    # Pass placeholders to get rich data for logging
                    placeholders = locals().get('placeholders', {})
                    await self._log_call_to_history(job, placeholders)
                except Exception as history_error:
                    logger.warning(f"Failed to log call history for job {job_id}: {history_error}")

                await self.call_queue_model.mark_completed(job_id)
                logger.info(f"[DISPATCHER] ✅ Job {job_id} completed.")
            else:
                await self.call_queue_model.mark_failed(job_id, error_msg)
                logger.warning(f"[DISPATCHER] ❌ Job {job_id} failed: {error_msg}")
            
            return success

        except Exception as e:
            await self.call_queue_model.mark_failed(job_id, f"Processing error: {str(e)}")
            logger.error(f"Critical error processing job {job_id}: {e}", exc_info=True)
            return False

    async def _log_call_to_history(self, job, placeholders: Dict[str, Any]):
        """Log successful call to call history table with rich data."""
        from telethon.tl.types import PeerChannel, PeerChat, PeerUser
        try:
            # --- Get Market Cap from placeholders ---
            market_cap_cents = None
            mc_str = placeholders.get('market_cap', 'N/A')
            if mc_str and mc_str != 'N/A':
                try:
                    # Helper to parse formatted market cap string like '$12.34K'
                    mc_clean = mc_str.replace('$', '').replace(',', '')
                    if mc_clean.endswith('K'):
                        mc_val = float(mc_clean[:-1]) * 1000
                    elif mc_clean.endswith('M'):
                        mc_val = float(mc_clean[:-1]) * 1000000
                    elif mc_clean.endswith('B'):
                        mc_val = float(mc_clean[:-1]) * 1000000000
                    else:
                        mc_val = float(mc_clean)
                    market_cap_cents = int(mc_val * 100)
                except (ValueError, TypeError):
                    logger.debug(f"Could not parse market cap string: {mc_str}")

            # Get caller and source information from the job's additional_info
            additional_info = {}
            if job.get('additional_info'):
                try:
                    if isinstance(job['additional_info'], str):
                        additional_info = json.loads(job['additional_info'])
                    elif isinstance(job['additional_info'], dict):
                        additional_info = job['additional_info']
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Could not parse additional_info for job {job.get('id')}")

            # Log to call history
            await self.call_history_service.log_call({
                'token_address': job['token_address'],
                'source_chat_id': job.get('source_chat_id'),
                'target_chat_id': job.get('target_chat_id'),
                'market_cap_cents': market_cap_cents,
                'caller_name': additional_info.get('caller_name'),
                'source_name': additional_info.get('source_name'),
                'source_type': additional_info.get('source_type')
            })

        except Exception as e:
            logger.error(f"Error logging call to history: {e}")

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

            # Get caller and source information from the job's additional_info
            additional_info = {}
            if job.get('additional_info'):
                try:
                    if isinstance(job['additional_info'], str):
                        additional_info = json.loads(job['additional_info'])
                    elif isinstance(job['additional_info'], dict):
                        additional_info = job['additional_info']
                except (json.JSONDecodeError, TypeError):
                    logger.warning(f"Could not parse additional_info for job {job.get('id')}")

            caller_user_id = job.get('source_user_id')
            caller_name = additional_info.get('caller_name', 'Unknown')
            source_chat_id = job.get('source_chat_id')
            source_name = additional_info.get('source_name', job.get('source_info', 'Unknown'))
            source_type = additional_info.get('source_type', 'channel')

            # Log to call history
            from app.models.token_call_history import TokenCallHistoryModel
            history_model = TokenCallHistoryModel(self.call_queue_model.db)

            await history_model.log_call(
                token_address=job['token_address'],
                caller_user_id=caller_user_id,
                caller_name=caller_name,
                source_chat_id=source_chat_id,
                source_name=source_name,
                source_type=source_type,
                target_chat_id=job['target_chat_id'],
                forwarding_userbot_id=job['forwarding_userbot_id'],
                routing_rule_id=job.get('routing_rule_id'),
                curated_alpha_rule_id=job.get('curated_alpha_rule_id'),
                market_cap_at_call=market_cap_cents,
                call_job_id=job.get('id')
            )
        except Exception as e:
            logger.error(f"Error logging call to history: {e}")

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
