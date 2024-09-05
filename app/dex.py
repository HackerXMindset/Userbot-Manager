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

# Singleton instance for global access
_dex_service_instance = None

def get_dex_service():
    """Get the singleton DexScreener service instance"""
    global _dex_service_instance
    if _dex_service_instance is None:
        _dex_service_instance = DexScreenerService()
    return _dex_service_instance

class DexScreenerService:
    """DexScreener integration for token price monitoring"""
    
    BASE_URL = "https://api.dexscreener.com/tokens/v1/solana"
    
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
        """Process a batch of tokens using batch API calls"""
        # Group tokens into chunks of 30 for batch API calls
        batch_size = 30
        for i in range(0, len(tokens), batch_size):
            batch = tokens[i:i + batch_size]
            try:
                # Get addresses for this batch
                addresses = [token['address'] for token in batch]
                
                # Fetch data for all tokens in this batch with single API call
                batch_data = await self._fetch_batch_token_data(addresses)
                
                if batch_data:
                    # Process each token with its corresponding data
                    for token in batch:
                        token_address = token['address']
                        # Find the data for this specific token in the batch response
                        token_pairs = [pair for pair in batch_data 
                                     if pair.get('baseToken', {}).get('address') == token_address]
                        if token_pairs:
                            await self._update_token_from_data(token, token_pairs)
                        
                # Rate limiting: 0.2s delay between batches (5 req/sec = 300 req/min)
                if i + batch_size < len(tokens):
                    await asyncio.sleep(0.2)
                    
            except Exception as e:
                logger.error(f"Error processing batch of {len(batch)} tokens: {e}")
                # Fallback to individual processing for this batch
                for token in batch:
                    try:
                        token_data = await self._fetch_token_data(token['address'])
                        if token_data:
                            await self._update_token_from_data(token, token_data)
                    except Exception as e:
                        logger.error(f"Error processing token {token['address'][:8]}...: {e}")
    
    async def _fetch_token_data(self, token_address: str, retries: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Fetch token data from DexScreener API"""
        if not self.session:
            logger.error(f"[DEXSCREENER] HTTP session not initialized for token {token_address}")
            return None
        
        try:
            url = f"{self.BASE_URL}/{token_address}"
            logger.info(f"[DEXSCREENER] Requesting: {url}")
            
            async with self.session.get(url) as response:
                # Get response body first for logging
                response_text = await response.text()
                logger.debug(f"[DEXSCREENER] Response status: {response.status}, Content-Length: {len(response_text)}")
                
                if response.status == 200:
                    try:
                        data = await response.json(content_type=None)  # Allow any content type
                        logger.debug(f"[DEXSCREENER] Raw response type: {type(data)}")
                        
                        # API documentation says it always returns an array
                        if isinstance(data, list):
                            if len(data) == 0:
                                logger.info(f"[DEXSCREENER] No trading pairs found for token {token_address}")
                                return []
                            else:
                                logger.info(f"[DEXSCREENER] Found {len(data)} trading pairs for token {token_address}")
                                # Log first pair details for debugging
                                first_pair = data[0]
                                logger.debug(f"[DEXSCREENER] First pair marketCap: {first_pair.get('marketCap', 'N/A')}, dexId: {first_pair.get('dexId', 'N/A')}")
                                return data
                        else:
                            logger.error(f"[DEXSCREENER] Unexpected response format for {token_address}. Expected list, got {type(data)}")
                            logger.error(f"[DEXSCREENER] Response content: {response_text[:1000]}...")
                            return None
                            
                    except Exception as json_error:
                        logger.error(f"[DEXSCREENER] JSON parsing failed for {token_address}: {json_error}")
                        logger.error(f"[DEXSCREENER] Raw response: {response_text[:1000]}...")
                        return None
                        
                elif response.status == 404:
                    logger.info(f"[DEXSCREENER] Token {token_address} not found (404) - likely new or unlisted token")
                    return None
                    
                elif response.status == 429:  # Rate limited
                    logger.warning(f"[DEXSCREENER] Rate limited (429) for {token_address}, retry {retries + 1}/{settings.dex_max_retries}")
                    if retries < settings.dex_max_retries:
                        wait_time = 2 ** retries
                        logger.info(f"[DEXSCREENER] Waiting {wait_time}s before retry...")
                        await asyncio.sleep(wait_time)
                        return await self._fetch_token_data(token_address, retries + 1)
                    else:
                        logger.error(f"[DEXSCREENER] Max retries ({settings.dex_max_retries}) exceeded for {token_address}")
                        return None
                        
                elif response.status == 400:
                    logger.error(f"[DEXSCREENER] Bad request (400) for token {token_address} - invalid token address?")
                    logger.error(f"[DEXSCREENER] Response: {response_text[:500]}...")
                    return None
                    
                elif response.status >= 500:
                    logger.error(f"[DEXSCREENER] Server error ({response.status}) for token {token_address}")
                    logger.error(f"[DEXSCREENER] Response: {response_text[:500]}...")
                    return None
                    
                else:
                    logger.error(f"[DEXSCREENER] Unexpected status {response.status} for token {token_address}")
                    logger.error(f"[DEXSCREENER] Response: {response_text[:500]}...")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error(f"[DEXSCREENER] Timeout ({settings.dex_timeout}s) fetching data for token {token_address}")
        except aiohttp.ClientError as e:
            logger.error(f"[DEXSCREENER] HTTP client error for token {token_address}: {type(e).__name__}: {e}")
        except Exception as e:
            logger.error(f"[DEXSCREENER] Unexpected error fetching token {token_address}: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"[DEXSCREENER] Traceback: {traceback.format_exc()}")
        
        return None
    
    async def _fetch_batch_token_data(self, addresses: List[str], retries: int = 0) -> Optional[List[Dict[str, Any]]]:
        """Fetch token data for multiple addresses using batch API"""
        if not self.session or not addresses:
            return None
        
        try:
            # Limit to 30 addresses per batch (API limit)
            if len(addresses) > 30:
                addresses = addresses[:30]
                logger.warning(f"Batch size limited to 30 tokens (was {len(addresses)})")
            
            # Build batch URL with comma-separated addresses
            addresses_str = ",".join(addresses)
            url = f"{self.BASE_URL}/{addresses_str}"
            
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # API returns array of pairs for batch requests
                    if isinstance(data, list):
                        return data
                    else:
                        logger.warning(f"Unexpected batch response format: {type(data)}")
                        return None
                elif response.status == 429:  # Rate limited
                    if retries < settings.dex_max_retries:
                        await asyncio.sleep(2 ** retries)  # Exponential backoff
                        return await self._fetch_batch_token_data(addresses, retries + 1)
                else:
                    logger.warning(f"DexScreener batch API returned {response.status} for {len(addresses)} tokens")
                    
        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching batch data for {len(addresses)} tokens")
        except Exception as e:
            logger.error(f"Error fetching batch token data: {e}")
        
        return None
    
    async def _update_token_from_data(self, token: Dict[str, Any], api_data: Dict[str, Any]):
        """Update token with data from API"""
        try:
            # New API returns direct array of pairs instead of object with pairs property
            pairs = api_data if isinstance(api_data, list) else api_data.get('pairs', [])
            if not pairs:
                return
            
            # Just use first pair since liquidity isn't needed
            best_pair = pairs[0]
            
            # Extract market cap
            market_cap = best_pair.get('marketCap')
            if not market_cap:
                return
            
            new_mc = Decimal(str(market_cap))
            
            # Update token in database
            await self.token_model.update_market_cap(token['id'], new_mc)
            
            # Stop monitoring tokens below $8K market cap
            if new_mc < 8000:
                await self.token_model.set_status(token['id'], 'stopped')
                logger.info(f"Stopped monitoring {token['address'][:8]}... (MC below $8K: ${new_mc:,.0f})")
            else:
                logger.info(f"Updated {token['address'][:8]}... MC: ${new_mc:,.0f}")
            
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
            
            # Extract initial market cap from new API format
            pairs = token_data if isinstance(token_data, list) else token_data.get('pairs', [])
            if not pairs:
                return {
                    'success': False,
                    'error': 'No trading pairs found for token'
                }
            
            # Just use first pair since liquidity isn't needed
            best_pair = pairs[0]
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
