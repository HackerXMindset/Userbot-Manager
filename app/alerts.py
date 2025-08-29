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
            
            # Get gain thresholds from settings
            gain_multipliers = await db.fetchval("""
                SELECT value FROM settings WHERE key = 'gain_multipliers'
            """)
            
            if not gain_multipliers:
                gain_multipliers = [5, 10, 15, 20, 50]
            
            # Check gain alerts
            for threshold in sorted(gain_multipliers):
                threshold_decimal = Decimal(str(threshold))
                
                # If current multiplier exceeds threshold and we haven't fired this alert yet
                if (current_multiplier >= threshold_decimal and 
                    last_hit_multiplier < threshold_decimal):
                    
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
            
            # TODO: Send notification to channels
            await self._send_gain_notification(token, threshold, current_multiplier, alert['id'])
            
            logger.info(f"Triggered {threshold}x gain alert for token {token['address'][:8]}...")
            
        except Exception as e:
            logger.error(f"Error triggering gain alert: {e}")
    
    async def _check_drop_alert(self, token: Dict[str, Any], current_multiplier: Decimal):
        """Check for drop alert (stop loss)"""
        try:
            # Get drop threshold from settings
            drop_percentage = await db.fetchval("""
                SELECT value FROM settings WHERE key = 'drop_percentage'
            """)
            
            if not drop_percentage:
                drop_percentage = 0.70
            
            drop_threshold = Decimal(str(drop_percentage))
            
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
            
            # TODO: Send stop notification
            await self._send_drop_notification(token, current_multiplier, drop_percentage, alert['id'])
            
            logger.info(f"Triggered drop alert for token {token['address'][:8]}... - stopping tracking")
            
        except Exception as e:
            logger.error(f"Error triggering drop alert: {e}")
    
    async def _send_gain_notification(self, token: Dict[str, Any], threshold: Decimal, current_multiplier: Decimal, alert_id: int):
        """Send gain notification to channels"""
        try:
            # Get notification channel from settings
            notif_channel = await db.fetchval(
                "SELECT value FROM settings WHERE key = 'default_notif_channel_id'"
            )
            
            if not notif_channel:
                logger.warning("No notification channel configured")
                return
            
            # Format message
            message = (
                f"🚀 <b>GAIN ALERT</b>\n\n"
                f"Token: <code>{token['address']}</code>\n"
                f"Threshold: {threshold}x\n"
                f"Current: {current_multiplier:.2f}x\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # TODO: Send via bot to notification channel
            logger.info(f"Would send gain notification: {message}")
            
        except Exception as e:
            logger.error(f"Error sending gain notification: {e}")
    
    async def _send_drop_notification(self, token: Dict[str, Any], current_multiplier: Decimal, drop_percentage: Decimal, alert_id: int):
        """Send drop notification to channels"""
        try:
            # Get notification channel from settings
            notif_channel = await db.fetchval(
                "SELECT value FROM settings WHERE key = 'default_notif_channel_id'"
            )
            
            if not notif_channel:
                logger.warning("No notification channel configured")
                return
            
            # Format message
            message = (
                f"📉 <b>DROP ALERT</b>\n\n"
                f"Token: <code>{token['address']}</code>\n"
                f"Current: {current_multiplier:.2f}x\n"
                f"Drop: {drop_percentage*100:.1f}% from peak\n"
                f"Status: STOPPED\n"
                f"Time: {datetime.now().strftime('%H:%M:%S')}"
            )
            
            # TODO: Send via bot to notification channel
            logger.info(f"Would send drop notification: {message}")
            
        except Exception as e:
            logger.error(f"Error sending drop notification: {e}")
    
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