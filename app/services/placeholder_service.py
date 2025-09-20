import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone

from app.db import db
from app.models.token import TokenModel
from app.dex import get_dex_service
from app.services.call_history_service import CallHistoryService

logger = logging.getLogger(__name__)

def format_market_cap(value: float) -> str:
    if value is None:
        return "N/A"
    try:
        value = float(value)
        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.2f}B"
        if value >= 1_000_000:
            return f"${value / 1_000_000:.2f}M"
        if value >= 1_000:
            return f"${value / 1_000:.2f}K"
        return f"${value:,.2f}"
    except (ValueError, TypeError):
        return "Invalid"

def format_time_diff(start_dt: Optional[datetime]) -> str:
    if not start_dt:
        return "N/A"
    if not start_dt.tzinfo:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    
    diff = datetime.now(timezone.utc) - start_dt
    
    total_seconds = int(diff.total_seconds())
    days = diff.days
    hours = total_seconds // 3600 % 24
    minutes = total_seconds // 60 % 60
    
    if days > 0:
        return f"{days}d {hours}h ago"
    if hours > 0:
        return f"{hours}h {minutes}m ago"
    if minutes > 0:
        return f"{minutes}m ago"
    return "Just now"

class PlaceholderService:
    """Gathers and formats data for template placeholders."""

    def __init__(self, token_address: str, job_context: Dict[str, Any]):
        self.token_address = token_address
        self.job_context = job_context
        self.token_model = TokenModel(db)
        self.call_history_service = CallHistoryService()
        self._data_cache: Dict[str, Any] = {}

    async def get_all_placeholders(self) -> Dict[str, str]:
        """Fetch all data and return a dictionary of formatted placeholder values."""
        # Initialize with default values
        placeholders = {
            'address': self.token_address,
            'token_symbol': 'N/A',
            'token_name': 'N/A',
            'market_cap': 'N/A',
            'ath': 'N/A',
            'pair_created_at': 'N/A',
            'dex_id': 'N/A',
            'dex_paid': 'N/A',
            'volume_h1': 'N/A',
            'volume_h6': 'N/A',
            'volume_h24': 'N/A',
            'volume_m5': 'N/A',
            'price_change_h1': 'N/A',
            'price_change_h6': 'N/A',
            'price_change_h24': 'N/A',
            'price_change_m5': 'N/A',
            'txns_h1_buys': 'N/A',
            'txns_h1_sells': 'N/A',
            'txns_h6_buys': 'N/A',
            'txns_h6_sells': 'N/A',
            'txns_h24_buys': 'N/A',
            'txns_h24_sells': 'N/A',
            'txns_m5_buys': 'N/A',
            'txns_m5_sells': 'N/A',
            'bonding_status': 'N/A',
            'multiplier': 'N/A',
            'mention_count': 'N/A',
            'chain_id': 'N/A',
            'pair_address': 'N/A',
            'quote_token_name': 'N/A',
            'quote_token_symbol': 'N/A',
            'price_native': 'N/A',
            'price_usd': 'N/A',
            'fdv': 'N/A',
            'liquidity_usd': 'N/A',
            'call_history': 'N/A',
        }

        # Fetch data
        dex_service = get_dex_service()
        db_token = await self.token_model.get_by_address(self.token_address)
        dex_pairs = await dex_service._fetch_token_data(self.token_address)

        current_mc = None

        # Populate from DexScreener first
        if dex_pairs:
            pair_data = dex_pairs[0]
            placeholders.update({
                'token_symbol': pair_data.get('baseToken', {}).get('symbol', 'N/A'),
                'token_name': pair_data.get('baseToken', {}).get('name', 'N/A'),
                'dex_id': pair_data.get('dexId', 'N/A'),
                'chain_id': pair_data.get('chainId', 'N/A'),
                'pair_address': pair_data.get('pairAddress', 'N/A'),
                'quote_token_name': pair_data.get('quoteToken', {}).get('name', 'N/A'),
                'quote_token_symbol': pair_data.get('quoteToken', {}).get('symbol', 'N/A'),
                'price_native': pair_data.get('priceNative', 'N/A'),
                'price_usd': pair_data.get('priceUsd', 'N/A'),
                'fdv': format_market_cap(pair_data.get('fdv')),
            })

            mc_raw = pair_data.get('marketCap')
            if mc_raw:
                current_mc = Decimal(mc_raw)
                placeholders['market_cap'] = format_market_cap(current_mc)

            volume = pair_data.get('volume', {})
            placeholders.update({
                'volume_h1': format_market_cap(volume.get('h1')),
                'volume_h6': format_market_cap(volume.get('h6')),
                'volume_h24': format_market_cap(volume.get('h24')),
                'volume_m5': format_market_cap(volume.get('m5')),
            })

            price_change = pair_data.get('priceChange', {})
            placeholders.update({
                'price_change_h1': f"{price_change.get('h1', 0):.2f}",
                'price_change_h6': f"{price_change.get('h6', 0):.2f}",
                'price_change_h24': f"{price_change.get('h24', 0):.2f}",
                'price_change_m5': f"{price_change.get('m5', 0):.2f}",
            })

            txns = pair_data.get('txns', {})
            placeholders.update({
                'txns_h1_buys': txns.get('h1', {}).get('buys', 0),
                'txns_h1_sells': txns.get('h1', {}).get('sells', 0),
                'txns_h6_buys': txns.get('h6', {}).get('buys', 0),
                'txns_h6_sells': txns.get('h6', {}).get('sells', 0),
                'txns_h24_buys': txns.get('h24', {}).get('buys', 0),
                'txns_h24_sells': txns.get('h24', {}).get('sells', 0),
                'txns_m5_buys': txns.get('m5', {}).get('buys', 0),
                'txns_m5_sells': txns.get('m5', {}).get('sells', 0),
            })

            liquidity = pair_data.get('liquidity', {})
            placeholders['liquidity_usd'] = format_market_cap(liquidity.get('usd'))
            placeholders['bonding_status'] = "Bonded" if float(liquidity.get('usd', 0)) > 1 else "Not Bonded"

            if pair_data.get('pairCreatedAt'):
                pair_dt = datetime.fromtimestamp(pair_data['pairCreatedAt'] / 1000, tz=timezone.utc)
                placeholders['pair_created_at'] = format_time_diff(pair_dt)

            info = pair_data.get('info', {})
            is_paid = any(key in info for key in ["imageUrl", "header", "openGraph", "websites", "socials"])
            placeholders['dex_paid'] = "✅" if is_paid else "❌"

        # Fallback and supplement with DB data
        if db_token:
            if placeholders['token_symbol'] == 'N/A':
                placeholders['token_symbol'] = db_token.get('ticker', 'N/A')
            if current_mc is None:
                current_mc = db_token.get('last_mc')
                if current_mc:
                    placeholders['market_cap'] = format_market_cap(current_mc)
            
            initial_mc = db_token.get('first_seen_mc')
            if initial_mc and current_mc and initial_mc > 0:
                multiplier = (current_mc / initial_mc)
                placeholders['multiplier'] = f"{multiplier:.2f}"

            peak_mc = db_token.get('peak_mc')
            if peak_mc:
                placeholders['ath'] = format_market_cap(peak_mc)

            mention_count = await db.fetchval(
                "SELECT COUNT(*) FROM calls WHERE token_id = $1", db_token['id']
            )
            placeholders['mention_count'] = str(mention_count or 1)

        # Add call history
        try:
            call_history_text = await self.call_history_service.format_call_history_for_token(
                self.token_address
            )
            placeholders['call_history'] = call_history_text
        except Exception as history_error:
            logger.warning(f"Failed to fetch call history for {self.token_address}: {history_error}")
            placeholders['call_history'] = "🌕 Recent History\nCall history unavailable"

        # Add links
        placeholders['defined_link'] = f"https://www.defined.fi/sol/{self.token_address}"
        placeholders['dexscreener_link'] = f"https://dexscreener.com/solana/{self.token_address}"

        return placeholders

    def format_template(self, template_text: str, placeholders: Dict[str, str]) -> str:
        """Formats the template text with the given placeholder values."""
        formatted_text = template_text
        for key, value in placeholders.items():
            formatted_text = formatted_text.replace(f"{{{key}}}", str(value))
            # Support for ${...} syntax as well
            formatted_text = formatted_text.replace(f"${{{key}}}", str(value))
        return formatted_text
