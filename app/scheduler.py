import asyncio
import logging
from datetime import datetime, time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from app.config import settings
from app.db import db
from app.models import GroupModel, ScheduleModel

logger = logging.getLogger(__name__)

@dataclass
class ScheduledCall:
    """Represents a scheduled call"""
    group_id: int
    userbot_id: int
    target_id: int
    token_id: int
    scheduled_at: datetime

class Scheduler:
    """Job scheduling engine for managing calls"""
    
    def __init__(self):
        self.group_model = GroupModel(db)
        self.schedule_model = ScheduleModel(db)
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the scheduler"""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        logger.info("Scheduler started")
    
    async def stop(self):
        """Stop the scheduler"""
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Scheduler stopped")
    
    async def _scheduler_loop(self):
        """Main scheduler loop"""
        while self.running:
            try:
                await self._process_schedules()
                await asyncio.sleep(60)  # Check every minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
                await asyncio.sleep(30)  # Wait before retrying
    
    async def _process_schedules(self):
        """Process active schedules and create calls"""
        try:
            now = settings.get_local_time()
            current_day = now.weekday() + 1  # Monday = 1
            current_time = now.time()
            
            # Get currently active schedules
            active_schedules = await self.schedule_model.get_active_schedules(
                current_day, current_time
            )
            
            for schedule in active_schedules:
                await self._process_schedule(schedule, now)
                
        except Exception as e:
            logger.error(f"Error processing schedules: {e}")
    
    async def _process_schedule(self, schedule: Dict[str, Any], now: datetime):
        """Process a single schedule"""
        try:
            group_id = schedule['group_id']
            
            # Check daily quota
            if schedule['daily_cap'] and schedule['daily_cap'] > 0:
                calls_today = await db.fetchval("""
                    SELECT COUNT(*) FROM calls 
                    WHERE group_id = $1 
                    AND sent_at > CURRENT_DATE 
                    AND status = 'sent'
                """, group_id)
                
                if calls_today >= schedule['daily_cap']:
                    logger.debug(f"Daily quota reached for group {group_id}")
                    return
            
            
            # Check window quota
            if schedule['max_calls_in_window'] and schedule['max_calls_in_window'] > 0:
                window_calls = await db.fetchval("""
                    SELECT COUNT(*) FROM calls 
                    WHERE group_id = $1 
                    AND sent_at::TIME > $2::TIME 
                    AND sent_at::TIME < $3::TIME
                    AND DATE(sent_at) = CURRENT_DATE
                    AND status = 'sent'
                """, group_id, schedule['start_time'], schedule['end_time'])
                
                if window_calls >= schedule['max_calls_in_window']:
                    logger.debug(f"Window quota reached for group {group_id}")
                    return
            
            # Get available tokens to call
            available_tokens = await self._get_available_tokens(group_id)
            
            if available_tokens:
                await self._schedule_call(schedule, available_tokens[0], now)
                
        except Exception as e:
            logger.error(f"Error processing schedule {schedule.get('id')}: {e}")
    
    async def _get_available_tokens(self, group_id: int) -> List[Dict[str, Any]]:
        """Get tokens available for calling in this group"""
        try:
            # Get tokens that:
            # 1. Are active
            # 2. Haven't been called in this group recently
            # 3. Have gain potential or alerts to trigger
            tokens = await db.fetch("""
                SELECT t.* 
                FROM tokens_tracked t
                WHERE t.status = 'active'
                AND t.id NOT IN (
                    SELECT token_id FROM calls 
                    WHERE group_id = $1 
                    AND created_at > NOW() - INTERVAL '1 hour'
                    AND status IN ('sent', 'queued')
                )
                AND (
                    -- Has untriggered gain alerts
                    (t.last_mc / t.first_seen_mc) > t.last_hit_multiplier
                    OR 
                    -- New token (never called)
                    t.id NOT IN (SELECT DISTINCT token_id FROM calls WHERE token_id IS NOT NULL)
                )
                ORDER BY (t.last_mc / t.first_seen_mc) DESC
                LIMIT 5
            """, group_id)
            
            return list(tokens)
            
        except Exception as e:
            logger.error(f"Error getting available tokens: {e}")
            return []
    
    async def _schedule_call(self, schedule: Dict[str, Any], token: Dict[str, Any], now: datetime):
        """Schedule a call for a token"""
        try:
            # Get targets for this group
            targets = await db.fetch("""
                SELECT * FROM targets 
                WHERE group_id = $1
                ORDER BY created_at
            """, schedule['group_id'])
            
            if not targets:
                logger.warning(f"No targets configured for group {schedule['group_id']}")
                return
            
            # Create call record
            call_id = await db.fetchval("""
                INSERT INTO calls (
                    group_id, token_id, target_id, userbot_id,
                    scheduled_at, status, reason
                ) VALUES ($1, $2, $3, $4, $5, 'queued', $6)
                RETURNING id
            """, 
                schedule['group_id'],
                token['id'],
                targets[0]['id'],  # Use first target for now
                schedule['userbot_id'],
                now,
                f"Scheduled call for {token['address'][:8]}..."
            )
            
            logger.info(f"Scheduled call {call_id} for token {token['address'][:8]}... in group {schedule['group_id']}")
            
        except Exception as e:
            logger.error(f"Error scheduling call: {e}")
    
    async def get_pending_calls(self) -> List[Dict[str, Any]]:
        """Get calls that are queued and ready to send"""
        try:
            calls = await db.fetch("""
                SELECT c.*, t.address, ta.dest_chat_id, b.session_string
                FROM calls c
                JOIN tokens_tracked t ON t.id = c.token_id
                JOIN targets ta ON ta.id = c.target_id
                LEFT JOIN bots b ON b.id = c.userbot_id
                WHERE c.status = 'queued'
                AND c.scheduled_at <= NOW()
                ORDER BY c.scheduled_at
                LIMIT 10
            """)
            
            return list(calls)
            
        except Exception as e:
            logger.error(f"Error getting pending calls: {e}")
            return []
    
    async def mark_call_sent(self, call_id: int, success: bool = True):
        """Mark a call as sent or failed"""
        try:
            status = 'sent' if success else 'failed'
            await db.execute("""
                UPDATE calls 
                SET status = $1, sent_at = NOW()
                WHERE id = $2
            """, status, call_id)
            
        except Exception as e:
            logger.error(f"Error updating call status: {e}")
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get scheduler statistics"""
        try:
            stats = await db.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'queued') as queued_calls,
                    COUNT(*) FILTER (WHERE status = 'sent' AND sent_at > CURRENT_DATE) as sent_today,
                    COUNT(*) FILTER (WHERE status = 'failed' AND created_at > CURRENT_DATE) as failed_today,
                    COUNT(DISTINCT group_id) FILTER (WHERE created_at > CURRENT_DATE) as active_groups
                FROM calls
            """)
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting scheduler statistics: {e}")
            return {}