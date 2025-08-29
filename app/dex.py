import asyncio
import aiohttp
import logging
from typing import Dict, Any, Optional, List
from decimal import Decimal
from datetime import datetime

from app.config import settings
from app.db import db
from app.models import TokenModel

logger = logging.getLogger(__name__)

class DexScreenerService:
    """DexScreener integration for token price monitoring"""
    
    BASE_URL = "https://api.dexscreener.com/latest/dex"
    
    def __init__(self):
        self.token_model = TokenModel(db)
        self.session: Optional[aiohttp.ClientSession] = None
        self.running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self):
        """Start the DexScreener monitoring service"""
        if self.running:
            return
        
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=settings.dex_timeout)
        )
        
        self.running = True
        self._task = asyncio.create_task(self._monitoring_loop())
        logger.info("DexScreener service started")
    
    async def stop(self):
        """Stop the DexScreener monitoring service"""
        if not self.running:
            return
        
        self.running = False
        
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        if self.session:
            await self.session.close()
            self.session = None
        
        logger.info("DexScreener service stopped")
    
    async def _monitoring_loop(self):
        """Main monitoring loop"""
        while self.running:
            try:
                await self._update_token_prices()
                await asyncio.sleep(settings.dex_poll_secs)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DexScreener monitoring error: {e}")
                await asyncio.sleep(30)
    
    async def _update_token_prices(self):
        """Update prices for all active tokens"""
        try:
            active_tokens = await self.token_model.get_active_tokens()
            
            if not active_tokens:
                return
            
            # Batch process tokens to avoid rate limits
            batch_size = 10
            for i in range(0, len(active_tokens), batch_size):
                batch = active_tokens[i:i + batch_size]
                await self._process_token_batch(batch)
                
                # Small delay between batches
                if i + batch_size < len(active_tokens):
                    await asyncio.sleep(1)
                    
        except Exception as e:
            logger.error(f"Error updating token prices: {e}")
    
    async def _process_token_batch(self, tokens: List[Dict[str, Any]]):
        """Process a batch of tokens"""
        for token in tokens:
            try:
                token_data = await self._fetch_token_data(token['address'])
                if token_data:
                    await self._update_token_from_data(token, token_data)
            except Exception as e:
                logger.error(f"Error processing token {token['address'][:8]}...: {e}")
    
    async def _fetch_token_data(self, token_address: str, retries: int = 0) -> Optional[Dict[str, Any]]:
        """Fetch token data from DexScreener API"""
        if not self.session:
            return None
        
        try:
            url = f"{self.BASE_URL}/tokens/{token_address}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:  # Rate limited
                    if retries < settings.dex_max_retries:
                        await asyncio.sleep(2 ** retries)  # Exponential backoff
                        return await self._fetch_token_data(token_address, retries + 1)
                else:
                    logger.warning(f"DexScreener API returned {response.status} for {token_address[:8]}...")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching data for {token_address[:8]}...")
        except Exception as e:
            logger.error(f"Error fetching token data: {e}")
        
        return None
    
    async def _update_token_from_data(self, token: Dict[str, Any], api_data: Dict[str, Any]):
        """Update token with data from API"""
        try:
            pairs = api_data.get('pairs', [])
            if not pairs:
                return
            
            # Find the best pair (highest liquidity)
            best_pair = None
            highest_liquidity = 0
            
            for pair in pairs:
                liquidity = float(pair.get('liquidity', {}).get('usd', 0))
                if liquidity > highest_liquidity:
                    highest_liquidity = liquidity
                    best_pair = pair
            
            if not best_pair:
                return
            
            # Extract market cap
            market_cap = best_pair.get('marketCap')
            if not market_cap:
                return
            
            new_mc = Decimal(str(market_cap))
            
            # Update token in database
            await self.token_model.update_market_cap(token['id'], new_mc)
            
            logger.debug(f"Updated {token['address'][:8]}... MC: ${new_mc:,.0f}")
            
        except Exception as e:
            logger.error(f"Error updating token from API data: {e}")
    
    async def add_token(self, token_address: str) -> Dict[str, Any]:
        """Add a new token for monitoring"""
        try:
            # Check if token already exists
            existing = await self.token_model.get_by_address(token_address)
            if existing:
                return {
                    'success': False,
                    'error': 'Token already being tracked',
                    'token': dict(existing)
                }
            
            # Fetch initial data
            token_data = await self._fetch_token_data(token_address)
            if not token_data:
                return {
                    'success': False,
                    'error': 'Could not fetch token data from DexScreener'
                }
            
            # Extract initial market cap
            pairs = token_data.get('pairs', [])
            if not pairs:
                return {
                    'success': False,
                    'error': 'No trading pairs found for token'
                }
            
            best_pair = max(pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
            market_cap = best_pair.get('marketCap')
            
            if not market_cap:
                return {
                    'success': False,
                    'error': 'Could not determine market cap'
                }
            
            initial_mc = Decimal(str(market_cap))
            
            # Create token record
            token = await self.token_model.create_or_update(token_address, initial_mc)
            
            logger.info(f"Added token {token_address[:8]}... with initial MC ${initial_mc:,.0f}")
            
            return {
                'success': True,
                'token': dict(token),
                'initial_mc': float(initial_mc)
            }
            
        except Exception as e:
            logger.error(f"Error adding token: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def remove_token(self, token_address: str) -> Dict[str, Any]:
        """Stop monitoring a token"""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    'success': False,
                    'error': 'Token not found'
                }
            
            await self.token_model.set_status(token['id'], 'stopped')
            
            logger.info(f"Stopped tracking token {token_address[:8]}...")
            
            return {
                'success': True,
                'token': dict(token)
            }
            
        except Exception as e:
            logger.error(f"Error removing token: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """Get current token information"""
        try:
            # Get from database
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    'success': False,
                    'error': 'Token not found in database'
                }
            
            # Get fresh data from API
            api_data = await self._fetch_token_data(token_address)
            
            result = {
                'success': True,
                'token': dict(token),
                'api_data': api_data
            }
            
            if token['first_seen_mc'] and token['first_seen_mc'] > 0:
                current_multiplier = token['last_mc'] / token['first_seen_mc']
                result['multiplier'] = float(current_multiplier)
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting token info: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    async def get_service_stats(self) -> Dict[str, Any]:
        """Get service statistics"""
        try:
            token_stats = await self.token_model.get_token_stats()
            
            return {
                'running': self.running,
                'poll_interval': settings.dex_poll_secs,
                'timeout': settings.dex_timeout,
                'max_retries': settings.dex_max_retries,
                'tokens': token_stats
            }
            
        except Exception as e:
            logger.error(f"Error getting service stats: {e}")
            return {'error': str(e)}
