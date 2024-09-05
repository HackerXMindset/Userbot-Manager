import asyncio
import logging
from typing import List, Dict, Any, Optional
from decimal import Decimal
from datetime import datetime

from app.config import settings
from app.db import db
from app.models import TokenModel, AlertModel

logger = logging.getLogger(__name__)

class AlertSystem:
    """Alert processing system for token price monitoring"""
    
    def __init__(self):
        self.token_model = TokenModel(db)
        self.alert_model = AlertModel(db)
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the alert system"""
        if self.running:
            return
        
        self.running = True
        self._task = asyncio.create_task(self._alert_loop())
        logger.info("Alert system started")
    
    async def stop(self):
        """Stop the alert system"""
        if not self.running:
            return
        
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        logger.info("Alert system stopped")
    
    async def _alert_loop(self):
        """Main alert processing loop"""
        while self.running:
            try:
                await self._process_alerts()
                await asyncio.sleep(settings.dex_poll_secs)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Alert system error: {e}")
                await asyncio.sleep(30)
    
    async def _process_alerts(self):
        """Process alerts for all active tokens"""
        try:
            tokens = await self.token_model.get_tokens_for_alert_check()
            
            for token in tokens:
                await self._check_token_alerts(token)
                
        except Exception as e:
            logger.error(f"Error processing alerts: {e}")
    
    async def _check_token_alerts(self, token: Dict[str, Any]):
        """Check alerts for a single token"""
        try:
            if not token['first_seen_mc'] or token['first_seen_mc'] <= 0:
                return
            
            current_multiplier = token['last_mc'] / token['first_seen_mc']
            last_hit_multiplier = token['last_hit_multiplier'] or Decimal('1.0')
            
            # Get gain thresholds from settings (group-specific or global)
            group_specific_key = f"group_{token.get('source_group_id')}_gains" if token.get('source_group_id') else None
            
            gain_multipliers_raw = None
            if group_specific_key:
                gain_multipliers_raw = await db.fetchval("""
                    SELECT value FROM settings WHERE key = $1
                """, group_specific_key)
            
            if not gain_multipliers_raw:
                gain_multipliers_raw = await db.fetchval("""
                    SELECT value FROM settings WHERE key = 'gain_multipliers'
                """)
            
            # Parse gain multipliers
            import json
            if gain_multipliers_raw:
                try:
                    if isinstance(gain_multipliers_raw, str):
                        gain_multipliers = json.loads(gain_multipliers_raw)
                    elif isinstance(gain_multipliers_raw, list):
                        gain_multipliers = gain_multipliers_raw
                    else:
                        gain_multipliers = [5, 10, 15]
                except (json.JSONDecodeError, TypeError):
                    gain_multipliers = [5, 10, 15]
            else:
                gain_multipliers = [5, 10, 15]
            
            # Check gain alerts - fire ALL thresholds that haven't been triggered yet
            for threshold in sorted(gain_multipliers):
                threshold_decimal = Decimal(str(threshold))
                
                # Check if current multiplier exceeds this threshold
                if current_multiplier >= threshold_decimal:
                    # Check if this specific threshold has already fired
                    already_fired = await self.alert_model.has_alert_fired(
                        token['id'], 'gain', threshold_decimal
                    )
                    
                    if not already_fired:
                        await self._trigger_gain_alert(token, threshold_decimal, current_multiplier)
            
            # Check drop alert
            await self._check_drop_alert(token, current_multiplier)
            
            # Update last checked time
            await self.token_model.update_market_cap(token['id'], token['last_mc'])
            
        except Exception as e:
            logger.error(f"Error checking alerts for token {token['id']}: {e}")
    
    async def _trigger_gain_alert(self, token: Dict[str, Any], threshold: Decimal, current_multiplier: Decimal):
        """Trigger a gain alert"""
        try:
            # Verify token still exists before proceeding
            token_exists = await self.token_model.get_by_address(token['address'])
            if not token_exists:
                logger.warning(f"Token {token['address'][:8]}... no longer exists, skipping alert")
                return
            
            # Check if this alert has already fired
            already_fired = await self.alert_model.has_alert_fired(
                token['id'], 'gain', threshold
            )
            
            if already_fired:
                return
            
            # Create alert record
            alert = await self.alert_model.create_alert(
                token_id=token['id'],
                alert_type='gain',
                multiplier=current_multiplier,
                threshold=threshold
            )
            
            # Update token's last hit multiplier
            await self.token_model.update_hit_multiplier(token['id'], threshold)
            
            # Send /pnl command to source group
            await self._send_pnl_command(token, threshold, current_multiplier)
            
            logger.info(f"Triggered {threshold}x gain alert for token {token['address'][:8]}...")
            
        except Exception as e:
            logger.error(f"Error triggering gain alert for token {token['address'][:8] if 'address' in token else token['id']}: {e}")
    
    async def _check_drop_alert(self, token: Dict[str, Any], current_multiplier: Decimal):
        """Check for drop alert (stop loss)"""
        try:
            # Get drop threshold from settings (group-specific or global)
            group_specific_key = f"group_{token.get('source_group_id')}_drop" if token.get('source_group_id') else None
            
            drop_percentage = None
            if group_specific_key:
                drop_percentage = await db.fetchval("""
                    SELECT value FROM settings WHERE key = $1
                """, group_specific_key)
            
            if not drop_percentage:
                drop_percentage = await db.fetchval("""
                    SELECT value FROM settings WHERE key = 'drop_percentage'
                """)
            
            if not drop_percentage:
                drop_percentage = 0.70
            
            try:
                drop_threshold = Decimal(str(float(drop_percentage)))
            except (ValueError, TypeError):
                drop_threshold = Decimal('0.70')
            
            # Check if token has dropped below threshold from its peak
            peak_multiplier = token['last_hit_multiplier'] or Decimal('1.0')
            
            if peak_multiplier > Decimal('1.0'):  # Only check if token has gained
                drop_from_peak = 1 - (current_multiplier / peak_multiplier)
                
                if drop_from_peak >= drop_threshold:
                    await self._trigger_drop_alert(token, current_multiplier, drop_from_peak)
            
        except Exception as e:
            logger.error(f"Error checking drop alert: {e}")
    
    async def _trigger_drop_alert(self, token: Dict[str, Any], current_multiplier: Decimal, drop_percentage: Decimal):
        """Trigger a drop alert and stop tracking"""
        try:
            # Create alert record
            alert = await self.alert_model.create_alert(
                token_id=token['id'],
                alert_type='drop',
                multiplier=current_multiplier,
                threshold=drop_percentage
            )
            
            # Stop tracking this token
            await self.token_model.set_status(token['id'], 'stopped')
            
            logger.info(f"Triggered drop alert for token {token['address'][:8]}... - stopping tracking")
            
        except Exception as e:
            logger.error(f"Error triggering drop alert: {e}")
    
    async def _send_pnl_command(self, token: Dict[str, Any], threshold: Decimal, current_multiplier: Decimal):
        """Send /pnl command to destination groups where token was forwarded"""
        try:
            # Get all destination groups where this token was sent
            destination_groups = await db.fetch("""
                SELECT DISTINCT c.group_id, g.tg_chat_id, g.title
                FROM calls c
                JOIN groups g ON g.id = c.group_id
                WHERE c.token_id = $1 AND c.status IN ('sent', 'queued')
                ORDER BY c.created_at DESC
            """, token['id'])
            
            if not destination_groups:
                logger.warning(f"No destination groups found for token {token['address'][:8]}...")
                return
            
            # Send /pnl command to each destination group with 20-second delay between groups
            for i, group in enumerate(destination_groups):
                try:
                    # Add 20-second delay between groups (skip for first group)
                    if i > 0:
                        logger.info(f"Waiting 20 seconds before sending to next group...")
                        await asyncio.sleep(20)
                    
                    # Get userbot assigned to this group
                    userbot_info = await db.fetchrow("""
                        SELECT b.id, b.session_name
                        FROM userbot_assignments ua
                        JOIN bots b ON b.id = ua.userbot_id  
                        WHERE ua.group_id = $1 AND b.status = 'active'
                        LIMIT 1
                    """, group['group_id'])
                    
                    if not userbot_info:
                        logger.warning(f"No active userbot found for destination group {group['group_id']}")
                        continue
                    
                    # Create command message
                    pnl_command = f"/pnl {token['address']}"
                    
                    # Send command via event system to the userbot
                    from app.events import EventRouter
                    event_router = EventRouter()
                    
                    await event_router.emit_event('send_message', {
                        'userbot_id': userbot_info['id'],
                        'target_chat_id': group['tg_chat_id'],
                        'message': pnl_command,
                        'reason': f'Gain alert: {threshold}x ({current_multiplier:.2f}x)'
                    })
                    
                    group_name = group['title'] or f"Chat {group['tg_chat_id']}"
                    logger.info(f"Sent /pnl command for token {token['address'][:8]}... to destination group {group_name} ({threshold}x alert)")
                    
                except Exception as group_error:
                    logger.error(f"Error sending /pnl to group {group['group_id']}: {group_error}")
                    continue
            
        except Exception as e:
            logger.error(f"Error sending /pnl command: {e}")
    
    async def manual_alert_check(self, token_address: str) -> Dict[str, Any]:
        """Manually check alerts for a specific token"""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {'error': 'Token not found'}
            
            await self._check_token_alerts(dict(token))
            
            return {
                'success': True,
                'token': token_address,
                'checked_at': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Error in manual alert check: {e}")
            return {'error': str(e)}
    
    async def get_alert_statistics(self) -> Dict[str, Any]:
        """Get alert system statistics"""
        try:
            stats = await self.alert_model.get_alert_stats()
            
            # Add system info
            active_tokens = await db.fetchval(
                "SELECT COUNT(*) FROM tokens_tracked WHERE status = 'active'"
            )
            
            stats['system'] = {
                'active_tokens': active_tokens,
                'running': self.running
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"Error getting alert statistics: {e}")
            return {}
    
    async def update_settings(self, gain_multipliers: List[int] = None, drop_percentage: float = None):
        """Update alert settings"""
        try:
            if gain_multipliers is not None:
                await db.execute("""
                    INSERT INTO settings (key, value) VALUES ('gain_multipliers', $1)
                    ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
                """, gain_multipliers)
            
            if drop_percentage is not None:
                await db.execute("""
                    INSERT INTO settings (key, value) VALUES ('drop_percentage', $1)
                    ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()
                """, drop_percentage)
                
            logger.info("Alert settings updated")
            
        except Exception as e:
            logger.error(f"Error updating alert settings: {e}")
            raise