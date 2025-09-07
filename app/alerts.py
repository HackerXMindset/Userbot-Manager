import logging
from typing import Dict, Any
from app.db import db

logger = logging.getLogger(__name__)

class AlertSystem:
    """Alert system - now handled by DexScreener monitoring"""
    
    def __init__(self):
        self.running = False
        logger.info("AlertSystem initialized - alerts handled by DexScreener service")
    
    async def start(self):
        """Start method for compatibility"""
        self.running = True
        logger.info("AlertSystem started - alerts integrated with DexScreener monitoring")
    
    async def stop(self):
        """Stop method for compatibility"""
        self.running = False
        logger.info("AlertSystem stopped")
    
    async def get_alert_statistics(self):
        """Returns real alert statistics from database"""
        try:
            stats = await db.fetchrow("""
                SELECT 
                    COUNT(*) FILTER (WHERE status = 'queued') as active_alerts,
                    COUNT(*) FILTER (WHERE created_at > CURRENT_DATE) as alerts_today,
                    COUNT(DISTINCT token_id) as tokens_with_alerts
                FROM calls
                WHERE reason LIKE '%alert%'
            """)
            
            return {
                'running': self.running,
                'active_tokens': stats['tokens_with_alerts'] if stats else 0,
                'gain_alerts': stats['alerts_today'] if stats else 0,
                'drop_alerts': 0,
                'alerts_today': stats['alerts_today'] if stats else 0,
                'tokens_with_alerts': stats['tokens_with_alerts'] if stats else 0,
                'status': 'enabled' if self.running else 'disabled'
            }
        except Exception as e:
            logger.error(f"Error getting alert statistics: {e}")
            return {
                'running': False,
                'active_tokens': 0,
                'gain_alerts': 0,
                'drop_alerts': 0,
                'alerts_today': 0,
                'tokens_with_alerts': 0,
                'status': 'error'
            }