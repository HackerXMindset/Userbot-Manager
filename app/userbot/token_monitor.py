"""
Token Monitor - Handles token detection and tracking from source messages
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from app.db import db
from .utils import UserbotUtils

logger = logging.getLogger(__name__)


class TokenMonitor:
    """Monitors and processes token addresses from messages"""
    
    def __init__(self, userbot_id: int):
        self.userbot_id = userbot_id
        self.utils = UserbotUtils()
    
    async def process_source_message(self, event, source_chat_id: int, target_groups: List[Dict[str, Any]] = None) -> List[str]:
        """Process a message from a source chat and extract tokens"""
        try:
            message = event.message
            text = self.utils.get_message_text(message)
            
            # Extract Solana addresses
            addresses = self.utils.extract_solana_addresses(text)
            
            if addresses:
                logger.info(f"Found {len(addresses)} token(s) in source {source_chat_id}: {[addr[:8] + '...' for addr in addresses]}")
                
                # Process each token
                for address in addresses:
                    await self._process_token_address(address, event, target_groups or [])
            
            return addresses
            
        except Exception as e:
            logger.error(f"Error processing source message: {e}")
            return []
    
    async def _process_token_address(self, address: str, event, target_groups: List[Dict[str, Any]]):
        """Process a single token address"""
        try:
            # Add token to tracking system with target groups
            await self._add_token_to_tracking(address, target_groups)
            
            # Log token detection
            source_title = self.utils.get_chat_title(event.chat)
            user_name = self.utils.get_user_name(event.sender)
            
            logger.info(f"Token {address[:8]}... detected from {source_title} by {user_name}")
            
        except Exception as e:
            logger.error(f"Error processing token address {address}: {e}")
    
    async def _add_token_to_tracking(self, address: str, target_groups: List[Dict[str, Any]]) -> Optional[int]:
        """Add token to tracking database"""
        try:
            # Add to DexScreener service for tracking - this sets initial market cap
            from app.dex import get_dex_service
            dex_service = get_dex_service()
            result = await dex_service.add_token(address)
            
            if not result['success']:
                logger.error(f"Failed to add token {address[:8]}... to DexScreener: {result.get('error', 'Unknown error')}")
                return None
            
            # Use first target group as primary source group for alerts
            source_group_id = target_groups[0]['id'] if target_groups else None
            
            # Update the existing record with source group info (DexScreener already created it)
            token_record = await db.fetchrow("""
                UPDATE tokens_tracked 
                SET source_group_id = COALESCE(source_group_id, $2),
                    last_checked_at = NOW()
                WHERE address = $1
                RETURNING id
            """, address, source_group_id)
            
            if token_record:
                logger.debug(f"Token {address[:8]}... updated in tracking (ID: {token_record['id']}, Group: {source_group_id})")
                return token_record['id']
            else:
                logger.error(f"Token {address[:8]}... not found after DexScreener add")
                return None
            
        except Exception as e:
            logger.error(f"Error adding token to tracking: {e}")
            return None
    
    async def get_token_by_address(self, address: str) -> Optional[Dict[str, Any]]:
        """Get token record by address"""
        try:
            return await db.fetchrow("""
                SELECT * FROM tokens_tracked WHERE address = $1
            """, address)
        except Exception as e:
            logger.error(f"Error getting token by address: {e}")
            return None
    
    async def update_token_stats(self, address: str, stats: Dict[str, Any]):
        """Update token statistics"""
        try:
            await db.execute("""
                UPDATE tokens_tracked 
                SET 
                    last_price = $2,
                    market_cap = $3,
                    volume_24h = $4,
                    last_checked_at = NOW()
                WHERE address = $1
            """, address, 
                stats.get('price'),
                stats.get('market_cap'), 
                stats.get('volume_24h')
            )
            
            logger.debug(f"Updated stats for token {address[:8]}...")
            
        except Exception as e:
            logger.error(f"Error updating token stats: {e}")
    
    async def get_recent_tokens(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recently detected tokens"""
        try:
            return await db.fetch("""
                SELECT * FROM tokens_tracked 
                ORDER BY created_at DESC 
                LIMIT $1
            """, limit)
        except Exception as e:
            logger.error(f"Error getting recent tokens: {e}")
            return []
    
    async def get_token_stats(self) -> Dict[str, Any]:
        """Get token monitoring statistics"""
        try:
            stats = await db.fetchrow("""
                SELECT 
                    COUNT(*) as total_tokens,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 day') as today_tokens,
                    COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '1 hour') as hour_tokens,
                    COUNT(*) FILTER (WHERE status = 'active') as active_tokens
                FROM tokens_tracked
            """)
            
            return dict(stats) if stats else {}
            
        except Exception as e:
            logger.error(f"Error getting token stats: {e}")
            return {}
    
    async def cleanup_old_tokens(self, days_old: int = 30):
        """Clean up old token records"""
        try:
            deleted_count = await db.fetchval("""
                DELETE FROM tokens_tracked
                WHERE created_at < NOW() - INTERVAL $1
                AND status != 'active'
                RETURNING COUNT(*)
            """, f"{days_old} days")
            
            if deleted_count:
                logger.info(f"Cleaned up {deleted_count} old token records")
            
            return deleted_count
            
        except Exception as e:
            logger.error(f"Error cleaning up old tokens: {e}")
            return 0