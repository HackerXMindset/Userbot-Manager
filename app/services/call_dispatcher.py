"""
Call Dispatcher Service - Processes job queue and delegates to forwarding bots
"""

import asyncio
import logging
import time
import json
from typing import Dict, Any, Optional, List, Set
from datetime import datetime, timedelta

from app.db import db
from app.models import BotModel
from app.models.call_queue import CallQueueModel
from app.models.template import TemplateAssignmentModel
from app.models.token_call_history import TokenCallHistoryModel
from app.models.source_chat import SourceChatModel
from app.models.group import GroupModel
from app.models.curated_alpha import CuratedAlphaTokenStateModel
from app.userbot.call_executor import CallExecutor
from app.services.placeholder_service import PlaceholderService
from app.services.call_history_service import CallHistoryService

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
        self.call_history_service = CallHistoryService()
        self.source_chat_model = SourceChatModel(db)
        self.group_model = GroupModel(db)
        self.curated_alpha_state_model = CuratedAlphaTokenStateModel(db)
        self._source_cache: Dict[int, Dict[str, Any]] = {}

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

            additional_info = self._parse_additional_info(job.get('additional_info'))
            caller_user_id = job.get('source_user_id')
            caller_name = additional_info.get('caller_name') or self._safe_decode_source_info(job.get('source_info'))
            source_details = await self._collect_source_details(job, additional_info)
            for entry in source_details:
                entry['caller_name'] = caller_name
                entry['caller_user_id'] = caller_user_id

            placeholders = {}
            if template_record:
                logger.info(f"Found custom template '{template_record['name']}' for group {target_group_id}")
                job_context = dict(job)
                job_context['current_call_sources'] = source_details
                job_context['current_caller_name'] = caller_name
                job_context['current_caller_id'] = caller_user_id
                
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
                    placeholders = locals().get('placeholders', {})
                    market_cap_cents = self._parse_market_cap_to_cents(placeholders.get('market_cap'))
                    await self._log_call_to_history(
                        job,
                        placeholders,
                        source_details,
                        caller_name,
                        caller_user_id,
                        market_cap_cents,
                    )
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

    async def _log_call_to_history(
        self,
        job,
        placeholders: Dict[str, Any],
        source_details: List[Dict[str, Any]],
        caller_name: Optional[str],
        caller_user_id: Optional[int],
        market_cap_cents: Optional[int],
    ):
        """Log successful call to call history table with rich data."""
        try:
            if not source_details:
                logger.debug("No source details provided for call history logging")
                return

            for source in source_details:
                if 'market_cap_cents' not in source and market_cap_cents is not None:
                    source['market_cap_cents'] = market_cap_cents
                chat_id = source.get('chat_id')
                if chat_id is None:
                    continue

                source_name = source.get('name') or f"Chat {chat_id}"
                source_type = source.get('type') or 'group'
                entry_caller_name = source.get('caller_name') or caller_name
                entry_caller_id = source.get('caller_user_id') or caller_user_id

                call_data = {
                    'token_address': job['token_address'],
                    'caller_user_id': entry_caller_id,
                    'caller_name': entry_caller_name,
                    'source_chat_id': chat_id,
                    'source_name': source_name,
                    'source_type': source_type,
                    'target_chat_id': job.get('target_chat_id'),
                    'forwarding_userbot_id': job.get('forwarding_userbot_id'),
                    'routing_rule_id': job.get('routing_rule_id'),
                    'curated_alpha_rule_id': job.get('curated_alpha_rule_id'),
                    'market_cap_cents': market_cap_cents,
                    'call_job_id': job.get('id'),
                }

                await self.call_history_service.log_call(call_data)

        except Exception as e:
            logger.error(f"Error logging call to history: {e}")

    def _parse_additional_info(self, raw_info: Optional[Any]) -> Dict[str, Any]:
        if not raw_info:
            return {}
        if isinstance(raw_info, dict):
            return raw_info
        if isinstance(raw_info, str):
            try:
                return json.loads(raw_info)
            except json.JSONDecodeError:
                logger.debug("Additional info is not valid JSON; returning empty dict")
                return {}
        return {}

    async def _collect_source_details(self, job, additional_info: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidate_ids: List[int] = []
        preloaded: Dict[int, Dict[str, Any]] = {}

        seen_sources_info = additional_info.get('seen_sources') or []
        for entry in seen_sources_info:
            cid = entry.get('chat_id')
            if cid is None:
                continue
            try:
                cid_int = int(cid)
            except (TypeError, ValueError):
                logger.debug(f"Unable to parse seen source chat id: {cid}")
                continue

            candidate_ids.append(cid_int)
            preloaded[cid_int] = {
                'chat_id': cid_int,
                'name': entry.get('name'),
                'type': entry.get('source_type'),
                'caller_name': entry.get('caller_name'),
                'caller_user_id': entry.get('caller_user_id'),
            }

        primary_raw = additional_info.get('source_chat_id') or job.get('source_chat_id')
        primary_id = None
        if primary_raw is not None:
            try:
                primary_id = int(primary_raw)
                candidate_ids.append(primary_id)
                preloaded.setdefault(primary_id, {'chat_id': primary_id})
                if additional_info.get('source_name'):
                    preloaded[primary_id]['name'] = additional_info['source_name']
                if additional_info.get('source_type'):
                    preloaded[primary_id]['type'] = additional_info['source_type']
                if additional_info.get('caller_name'):
                    preloaded[primary_id]['caller_name'] = additional_info['caller_name']
                if additional_info.get('caller_user_id'):
                    preloaded[primary_id]['caller_user_id'] = additional_info.get('caller_user_id')
            except (TypeError, ValueError):
                logger.debug(f"Unable to parse primary source chat id: {primary_raw}")

        if job.get('curated_alpha_rule_id'):
            try:
                state_record = await self.curated_alpha_state_model.db.fetchrow(
                    """
                    SELECT seen_in_source_chat_ids
                    FROM curated_alpha_token_state
                    WHERE rule_id = $1 AND token_address = $2
                    """,
                    job['curated_alpha_rule_id'],
                    job['token_address'],
                )
                if state_record and state_record.get('seen_in_source_chat_ids'):
                    for chat_id in state_record['seen_in_source_chat_ids']:
                        try:
                            cid_int = int(chat_id)
                            candidate_ids.append(cid_int)
                            preloaded.setdefault(cid_int, {'chat_id': cid_int})
                        except (TypeError, ValueError):
                            logger.debug(f"Unable to parse curated source chat id: {chat_id}")
            except Exception as state_error:
                logger.debug(f"Unable to fetch curated alpha state: {state_error}")

        ordered_ids: List[int] = []
        seen_ids: Set[int] = set()
        for cid in candidate_ids:
            if cid not in seen_ids:
                seen_ids.add(cid)
                ordered_ids.append(cid)

        sources: List[Dict[str, Any]] = []
        for cid in ordered_ids:
            preload = preloaded.get(cid, {})
            name = preload.get('name')
            source_type = preload.get('type')

            if name is None or source_type is None:
                resolved_name, resolved_type = await self._resolve_source_details(cid)
                if name is None:
                    name = resolved_name
                if source_type is None:
                    source_type = resolved_type

            sources.append(
                {
                    'chat_id': cid,
                    'name': name or f"Chat {cid}",
                    'type': source_type or 'group',
                    'caller_name': preload.get('caller_name'),
                    'caller_user_id': preload.get('caller_user_id'),
                }
            )

        return sources

    def _parse_market_cap_to_cents(self, mc_str: Optional[str]) -> Optional[int]:
        if not mc_str or mc_str == 'N/A':
            return None
        try:
            value = mc_str.replace('$', '').replace(',', '').strip()
            multiplier = 1
            if value.endswith('K'):
                multiplier = 1_000
                value = value[:-1]
            elif value.endswith('M'):
                multiplier = 1_000_000
                value = value[:-1]
            elif value.endswith('B'):
                multiplier = 1_000_000_000
                value = value[:-1]
            numeric = float(value) * multiplier
            return int(numeric * 100)
        except (ValueError, TypeError):
            logger.debug(f"Could not parse market cap string: {mc_str}")
            return None

    async def _resolve_source_details(self, source_chat_id: Optional[int]) -> (Optional[str], Optional[str]):
        if not source_chat_id:
            return None, None

        if source_chat_id in self._source_cache:
            cached = self._source_cache[source_chat_id]
            return cached.get('name'), cached.get('type')

        record = await self.source_chat_model.get_source_by_chat_id(source_chat_id)
        name = None
        source_type = None

        if record:
            name = record.get('display_name') or record.get('name') or record.get('title')
            source_type = record.get('source_type')

        if not name:
            group_record = await self.group_model.get_by_chat_id(source_chat_id)
            if group_record:
                name = group_record.get('display_name') or group_record.get('title')

        if not name:
            name = f"Chat {source_chat_id}"

        if not source_type:
            source_type = 'group'

        self._source_cache[source_chat_id] = {'name': name, 'type': source_type}
        return name, source_type

    def _safe_decode_source_info(self, source_info: Optional[str]) -> Optional[str]:
        if not source_info:
            return None

        if isinstance(source_info, str):
            stripped = source_info.strip()
            try:
                decoded = json.loads(stripped)
                if isinstance(decoded, str):
                    return decoded
                if isinstance(decoded, dict):
                    return decoded.get('name') or decoded.get('title')
            except json.JSONDecodeError:
                return stripped
        return source_info

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
