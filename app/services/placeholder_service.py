import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime, timezone

from app.db import db
from app.models.token import TokenModel
from app.dex import get_dex_service
from app.services.call_history_service import CallHistoryService
from app.services.rust_bridge import rust_dex_bridge

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


def format_bool(value: Optional[bool]) -> str:
    if value is None:
        return "N/A"
    return "Yes" if value else "No"


def format_number(value: Optional[float], decimals: int = 2) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.{decimals}f}"
    except (ValueError, TypeError):
        return str(value)


def format_int(value: Optional[int]) -> str:
    if value is None:
        return "N/A"
    try:
        return f"{int(value):,}"
    except (ValueError, TypeError):
        return str(value)


def format_timestamp_value(timestamp: Optional[int]) -> Dict[str, str]:
    if not timestamp:
        return {"ago": "N/A", "iso": "N/A"}

    try:
        ts_int = int(timestamp)
        if ts_int > 1_000_000_000_000:
            ts_int = ts_int // 1000
        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
    except (ValueError, TypeError, OSError, OverflowError):
        return {"ago": "N/A", "iso": str(timestamp)}

    return {"ago": format_time_diff(dt), "iso": dt.isoformat()}


def get_map_value(mapping: Optional[Dict[str, Any]], *keys: str) -> Any:
    """Return the first non-None value for the provided keys from a mapping."""
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            return mapping[key]
    return None

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
            'dex_pair_chain_id': 'N/A',
            'dex_pair_dex_id': 'N/A',
            'dex_pair_url': 'N/A',
            'dex_pair_address': 'N/A',
            'dex_pair_market_cap_raw': 'N/A',
            'dex_pair_fdv_raw': 'N/A',
            'dex_paid': 'N/A',
            'dex_time': 'N/A',
            'cto_status': 'N/A',
            'cto_time': 'N/A',
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
            'liquidity_base': 'N/A',
            'liquidity_quote': 'N/A',
            'call_history': 'N/A',
            'dex_info_image_url': 'N/A',
            'dex_info_header': 'N/A',
            'dex_info_open_graph': 'N/A',
            'dex_info_websites': 'N/A',
            'dex_info_socials': 'N/A',
            'dex_boosts_active': 'N/A',
            'pf_mint': 'N/A',
            'pf_name': 'N/A',
            'pf_symbol': 'N/A',
            'pf_description': 'N/A',
            'pf_image_uri': 'N/A',
            'pf_metadata_uri': 'N/A',
            'pf_twitter': 'N/A',
            'pf_telegram': 'N/A',
            'pf_website': 'N/A',
            'pf_social': 'N/A',
            'pf_ath_comparison': 'N/A',
            'pf_bonding_curve': 'N/A',
            'pf_associated_bonding_curve': 'N/A',
            'pf_creator': 'N/A',
            'pf_creator_short': 'N/A',
            'pf_creator_solscan': 'N/A',
            'pf_creator_stats': 'N/A',
            'pf_created_timestamp': 'N/A',
            'pf_created_timestamp_iso': 'N/A',
            'pf_created_timestamp_ago': 'N/A',
            'pf_last_trade_timestamp': 'N/A',
            'pf_last_trade_timestamp_iso': 'N/A',
            'pf_last_trade_timestamp_ago': 'N/A',
            'pf_ath_market_cap_timestamp': 'N/A',
            'pf_ath_market_cap_timestamp_iso': 'N/A',
            'pf_ath_market_cap_timestamp_ago': 'N/A',
            'pf_koth_timestamp': 'N/A',
            'pf_koth_timestamp_iso': 'N/A',
            'pf_koth_timestamp_ago': 'N/A',
            'pf_total_supply': 'N/A',
            'pf_market_cap_sol': 'N/A',
            'pf_market_cap_usd': 'N/A',
            'pf_ath_market_cap': 'N/A',
            'pf_real_sol_reserves': 'N/A',
            'pf_virtual_sol_reserves': 'N/A',
            'pf_virtual_token_reserves': 'N/A',
            'pf_real_token_reserves': 'N/A',
            'pf_reply_count': 'N/A',
            'pf_num_participants': 'N/A',
            'pf_is_currently_live': 'N/A',
            'pf_complete': 'N/A',
            'pf_raydium_pool': 'N/A',
            'pf_pump_swap_pool': 'N/A',
            'pf_hidden': 'N/A',
            'pf_show_name': 'N/A',
            'pf_nsfw': 'N/A',
            'pf_inverted': 'N/A',
            'pf_is_banned': 'N/A',
            'pf_initialized': 'N/A',
            'pf_hide_banner': 'N/A',
            'pf_livestream_ban_expiry': 'N/A',
            'pf_livestream_ban_expiry_iso': 'N/A',
            'pf_livestream_ban_expiry_ago': 'N/A',
            'pf_livestream_downrank_score': 'N/A',
            'pf_downrank_score': 'N/A',
            'pf_program': 'N/A',
            'pf_platform': 'N/A',
            'pf_market_id': 'N/A',
            'pf_updated_at': 'N/A',
            'pf_updated_at_iso': 'N/A',
            'pf_updated_at_ago': 'N/A',
            'pf_last_reply': 'N/A',
            'pf_last_reply_iso': 'N/A',
            'pf_last_reply_ago': 'N/A',
            'pf_thumbnail_updated_at': 'N/A',
            'pf_thumbnail_updated_at_iso': 'N/A',
            'pf_thumbnail_updated_at_ago': 'N/A',
            'pf_banner_uri': 'N/A',
            'pf_thumbnail_uri': 'N/A',
            'pf_video_uri': 'N/A',
            'jup_id': 'N/A',
            'jup_name': 'N/A',
            'jup_symbol': 'N/A',
            'jup_icon': 'N/A',
            'jup_decimals': 'N/A',
            'jup_token_program': 'N/A',
            'jup_launchpad': 'N/A',
            'jup_first_pool_id': 'N/A',
            'jup_first_pool_created_at': 'N/A',
            'jup_graduated_pool': 'N/A',
            'jup_graduated_at': 'N/A',
            'jup_holder_count': 'N/A',
            'jup_updated_at': 'N/A',
            'jup_circ_supply': 'N/A',
            'jup_total_supply': 'N/A',
            'jup_usd_price': 'N/A',
            'jup_mcap': 'N/A',
            'jup_fdv': 'N/A',
            'jup_liquidity': 'N/A',
            'jup_bonding_curve': 'N/A',
            'jup_price_block_id': 'N/A',
            'jup_is_verified': 'N/A',
            'jup_audit_mint_authority_disabled': 'N/A',
            'jup_audit_freeze_authority_disabled': 'N/A',
            'jup_audit_top_holders_pct': 'N/A',
            'jup_audit_snipers_pct': 'N/A',
            'jup_audit_dev_migrations': 'N/A',
            'jup_audit_dev_balance_pct': 'N/A',
            'jup_dev_address': 'N/A',
            'jup_dev_sol_balance': 'N/A',
            'jup_organic_score': 'N/A',
            'jup_organic_score_label': 'N/A',
            'jup_tags': 'N/A',
            'jup_ct_likes': 'N/A',
            'jup_smart_ct_likes': 'N/A',
            'jup_twitter': 'N/A',
            'jup_telegram': 'N/A',
            'jup_website': 'N/A',
            'jup_cexes': 'N/A',
            'helius_data_slot': 'N/A',
            'helius_holder_count': 'N/A',
            'helius_holder_total_ui_amount': 'N/A',
            'helius_creator_holding_ui_amount': 'N/A',
            'helius_creator_holding_ui_amount_string': 'N/A',
            'helius_creator_holding_raw_amount': 'N/A',
            'helius_creator_holding_percent_of_sample': 'N/A',
            'helius_creator_holding_percent_of_supply': 'N/A',
            'helius_creator_is_holder': 'N/A',
            'helius_top1_ui_amount': 'N/A',
            'helius_top5_ui_amount': 'N/A',
            'helius_top10_ui_amount': 'N/A',
            'helius_top20_ui_amount': 'N/A',
            'helius_top1_share': 'N/A',
            'helius_top5_share': 'N/A',
            'helius_top10_share': 'N/A',
            'helius_top20_share': 'N/A',
            'helius_remaining_share': 'N/A',
            'helius_holder_table': 'N/A',
        }

        for i in range(1, 6):
            placeholders[f'dex_info_website_{i}'] = 'N/A'
            placeholders[f'dex_info_social_{i}_platform'] = 'N/A'
            placeholders[f'dex_info_social_{i}_handle'] = 'N/A'

        stat_fields = [
            'price_change',
            'holder_change',
            'liquidity_change',
            'volume_change',
            'buy_volume',
            'sell_volume',
            'buy_organic_volume',
            'sell_organic_volume',
            'num_buys',
            'num_sells',
            'num_traders',
            'num_organic_buyers',
            'num_net_buyers',
        ]

        for timeframe in ['5m', '1h', '6h', '24h']:
            for field in stat_fields:
                placeholders[f'jup_stats_{timeframe}_{field}'] = 'N/A'

        for i in range(1, 21):
            placeholders[f'dex_order_{i}_type'] = 'N/A'
            placeholders[f'dex_order_{i}_status'] = 'N/A'
            placeholders[f'dex_order_{i}_timestamp'] = 'N/A'
            placeholders[f'dex_order_{i}_timestamp_iso'] = 'N/A'

        for i in range(1, 21):
            placeholders[f'helius_holder_{i}_address'] = 'N/A'
            placeholders[f'helius_holder_{i}_short'] = 'N/A'
            placeholders[f'helius_holder_{i}_ui_amount'] = 'N/A'
            placeholders[f'helius_holder_{i}_ui_amount_string'] = 'N/A'
            placeholders[f'helius_holder_{i}_raw_amount'] = 'N/A'
            placeholders[f'helius_holder_{i}_decimals'] = 'N/A'
            placeholders[f'helius_holder_{i}_percent_of_sample'] = 'N/A'
            placeholders[f'helius_holder_{i}_percent_of_supply'] = 'N/A'

        # Fetch data from Rust service first
        db_token = await self.token_model.get_by_address(self.token_address)
        rust_payload = await rust_dex_bridge.fetch_dex_payload(self.token_address)

        dex_pairs = []
        dex_orders = []
        pump_fun_payload = None
        jupiter_payload = None
        dev_sol_balance = None
        holders_payload = None
        supply_ui_amount = None
        if rust_payload:
            dex_pairs = rust_payload.get('pairs') or []
            dex_orders = rust_payload.get('orders') or []
            pump_fun_payload = rust_payload.get('pump_fun')
            jupiter_payload = rust_payload.get('jupiter')
            dev_sol_balance = rust_payload.get('dev_sol_balance')
            holders_payload = rust_payload.get('holders')
            supply_ui_amount = rust_payload.get('supply_ui_amount')

        if not dex_pairs:
            logger.warning(
                "Rust dex payload unavailable for %s, falling back to internal client",
                self.token_address,
            )
            dex_service = get_dex_service()
            dex_pairs = await dex_service._fetch_token_data(self.token_address) or []

        current_mc = None

        if dex_pairs:
            pair_data = dex_pairs[0]
            base_token = pair_data.get('baseToken') or {}
            quote_token = pair_data.get('quoteToken') or {}
            placeholders.update({
                'token_symbol': base_token.get('symbol') or 'N/A',
                'token_name': base_token.get('name') or 'N/A',
                'dex_id': pair_data.get('dexId') or 'N/A',
                'dex_pair_chain_id': pair_data.get('chainId') or 'N/A',
                'dex_pair_dex_id': pair_data.get('dexId') or 'N/A',
                'dex_pair_url': pair_data.get('url') or 'N/A',
                'dex_pair_address': pair_data.get('pairAddress') or 'N/A',
                'pair_address': pair_data.get('pairAddress') or 'N/A',
                'quote_token_name': quote_token.get('name') or 'N/A',
                'quote_token_symbol': quote_token.get('symbol') or 'N/A',
                'price_native': pair_data.get('priceNative') or 'N/A',
                'price_usd': pair_data.get('priceUsd') or 'N/A',
                'fdv': format_market_cap(pair_data.get('fdv')),
            })

            mc_raw = pair_data.get('marketCap')
            if mc_raw:
                try:
                    current_mc = Decimal(str(mc_raw))
                except Exception:
                    current_mc = Decimal(str(float(mc_raw)))
                placeholders['market_cap'] = format_market_cap(current_mc)
                placeholders['dex_pair_market_cap_raw'] = f"{mc_raw:.2f}" if isinstance(mc_raw, (int, float)) else str(mc_raw)

            fdv_raw = pair_data.get('fdv')
            if fdv_raw is not None:
                placeholders['dex_pair_fdv_raw'] = f"{fdv_raw:.2f}" if isinstance(fdv_raw, (int, float)) else str(fdv_raw)

            volume = pair_data.get('volume') or {}
            placeholders.update({
                'volume_h1': format_market_cap(volume.get('h1')),
                'volume_h6': format_market_cap(volume.get('h6')),
                'volume_h24': format_market_cap(volume.get('h24')),
                'volume_m5': format_market_cap(volume.get('m5')),
            })

            price_change = pair_data.get('priceChange') or {}
            placeholders.update({
                'price_change_h1': f"{price_change.get('h1', 0) or 0:.2f}",
                'price_change_h6': f"{price_change.get('h6', 0) or 0:.2f}",
                'price_change_h24': f"{price_change.get('h24', 0) or 0:.2f}",
                'price_change_m5': f"{price_change.get('m5', 0) or 0:.2f}",
            })

            txns = pair_data.get('txns') or {}
            h1_txn = txns.get('h1') or {}
            h6_txn = txns.get('h6') or {}
            h24_txn = txns.get('h24') or {}
            m5_txn = txns.get('m5') or {}

            placeholders.update({
                'txns_h1_buys': h1_txn.get('buys', 0),
                'txns_h1_sells': h1_txn.get('sells', 0),
                'txns_h6_buys': h6_txn.get('buys', 0),
                'txns_h6_sells': h6_txn.get('sells', 0),
                'txns_h24_buys': h24_txn.get('buys', 0),
                'txns_h24_sells': h24_txn.get('sells', 0),
                'txns_m5_buys': m5_txn.get('buys', 0),
                'txns_m5_sells': m5_txn.get('sells', 0),
            })

            liquidity = pair_data.get('liquidity') or {}
            placeholders['liquidity_usd'] = format_market_cap(liquidity.get('usd'))
            placeholders['liquidity_base'] = format_market_cap(liquidity.get('base'))
            placeholders['liquidity_quote'] = format_market_cap(liquidity.get('quote'))
            usd_liquidity = liquidity.get('usd') or 0
            try:
                usd_liquidity_value = float(usd_liquidity)
            except (TypeError, ValueError):
                usd_liquidity_value = 0
            placeholders['bonding_status'] = (
                "Bonded" if usd_liquidity_value and usd_liquidity_value > 1 else "Not Bonded"
            )

            if pair_data.get('pairCreatedAt'):
                pair_dt = datetime.fromtimestamp(pair_data['pairCreatedAt'] / 1000, tz=timezone.utc)
                placeholders['pair_created_at'] = format_time_diff(pair_dt)

            info = pair_data.get('info') or {}
            placeholders['dex_info_image_url'] = info.get('imageUrl', 'N/A') or 'N/A'
            placeholders['dex_info_header'] = info.get('header', 'N/A') or 'N/A'
            placeholders['dex_info_open_graph'] = info.get('openGraph', 'N/A') or 'N/A'

            websites = info.get('websites') or []
            if websites:
                formatted_websites = []
                for idx, entry in enumerate(websites[:5], start=1):
                    url_value = entry.get('url') or 'N/A'
                    placeholders[f'dex_info_website_{idx}'] = url_value
                    formatted_websites.append(url_value)
                placeholders['dex_info_websites'] = '\n'.join(formatted_websites)

            socials = info.get('socials') or []
            if socials:
                formatted_socials = []
                for idx, entry in enumerate(socials[:5], start=1):
                    platform = entry.get('platform') or 'N/A'
                    handle = entry.get('handle') or 'N/A'
                    placeholders[f'dex_info_social_{idx}_platform'] = platform
                    placeholders[f'dex_info_social_{idx}_handle'] = handle
                    formatted_socials.append(f"{platform}: {handle}")
                placeholders['dex_info_socials'] = '\n'.join(formatted_socials)

            boosts = pair_data.get('boosts') or {}
            if boosts:
                placeholders['dex_boosts_active'] = boosts.get('active', 'N/A') or 'N/A'

            is_paid = any(info.get(key) for key in ["imageUrl", "header", "openGraph"]) or bool(websites) or bool(socials)
            placeholders['dex_paid'] = "✅" if is_paid else "❌"

        # Dex orders placeholders
        if dex_orders:
            for idx, order in enumerate(dex_orders[:20], start=1):
                prefix = f'dex_order_{idx}'
                placeholders[f'{prefix}_type'] = order.get('type', 'N/A') or 'N/A'
                placeholders[f'{prefix}_status'] = order.get('status', 'N/A') or 'N/A'
                timestamp = order.get('paymentTimestamp')
                if timestamp:
                    try:
                        ts_int = int(timestamp)
                        if ts_int > 1_000_000_000_000:
                            ts_int = ts_int // 1000
                        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
                        placeholders[f'{prefix}_timestamp'] = format_time_diff(dt)
                        placeholders[f'{prefix}_timestamp_iso'] = dt.isoformat()
                    except (ValueError, OSError, OverflowError):
                        placeholders[f'{prefix}_timestamp'] = str(timestamp)
                        placeholders[f'{prefix}_timestamp_iso'] = str(timestamp)

        # Process CTO and DEX time placeholders
        placeholders['cto_status'] = '❌'
        placeholders['cto_time'] = 'N/A'
        placeholders['dex_time'] = 'N/A'

        if dex_orders:
            cto_order = None
            dex_paid_order = None

            for order in dex_orders:
                order_type = order.get('type')
                order_status = order.get('status')

                # Find most recent approved CTO order
                if order_type == 'communityTakeover' and order_status == 'approved':
                    if not cto_order:
                        cto_order = order

                # Find most recent tokenProfile order
                if order_type == 'tokenProfile':
                    if not dex_paid_order:
                        dex_paid_order = order

            # Set CTO placeholders
            if cto_order:
                placeholders['cto_status'] = '✅'
                timestamp = cto_order.get('paymentTimestamp')
                if timestamp:
                    try:
                        ts_int = int(timestamp)
                        if ts_int > 1_000_000_000_000:
                            ts_int = ts_int // 1000
                        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
                        placeholders['cto_time'] = format_time_diff(dt)
                    except (ValueError, OSError, OverflowError):
                        placeholders['cto_time'] = 'N/A'

            # Set DEX time placeholder
            if dex_paid_order:
                timestamp = dex_paid_order.get('paymentTimestamp')
                if timestamp:
                    try:
                        ts_int = int(timestamp)
                        if ts_int > 1_000_000_000_000:
                            ts_int = ts_int // 1000
                        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
                        placeholders['dex_time'] = format_time_diff(dt)
                    except (ValueError, OSError, OverflowError):
                        placeholders['dex_time'] = 'N/A'

        # Pump.fun placeholders
        if pump_fun_payload:
            pf = pump_fun_payload

            placeholders['pf_mint'] = pf.get('mint') or 'N/A'
            placeholders['pf_name'] = pf.get('name') or 'N/A'
            placeholders['pf_symbol'] = pf.get('symbol') or 'N/A'
            placeholders['pf_description'] = pf.get('description') or 'N/A'
            placeholders['pf_image_uri'] = pf.get('image_uri') or 'N/A'
            placeholders['pf_metadata_uri'] = pf.get('metadata_uri') or 'N/A'
            placeholders['pf_twitter'] = pf.get('twitter') or 'N/A'
            placeholders['pf_telegram'] = pf.get('telegram') or 'N/A'
            placeholders['pf_website'] = pf.get('website') or 'N/A'

            # Combined social links in hyperlink format
            social_links = []
            if pf.get('twitter') and pf.get('twitter') != 'N/A':
                social_links.append(f'<a href="{pf.get("twitter")}">Twitter</a>')
            if pf.get('telegram') and pf.get('telegram') != 'N/A':
                social_links.append(f'<a href="{pf.get("telegram")}">Telegram</a>')
            if pf.get('website') and pf.get('website') != 'N/A':
                social_links.append(f'<a href="{pf.get("website")}">Website</a>')

            placeholders['pf_social'] = ' | '.join(social_links) if social_links else 'N/A'
            placeholders['pf_bonding_curve'] = pf.get('bonding_curve') or 'N/A'
            placeholders['pf_associated_bonding_curve'] = pf.get('associated_bonding_curve') or 'N/A'

            creator = pf.get('creator')
            if creator:
                placeholders['pf_creator'] = creator
                placeholders['pf_creator_short'] = f"{creator[:6]}...{creator[-6:]}" if len(creator) > 12 else creator
                placeholders['pf_creator_solscan'] = f"https://solscan.io/account/{creator}"
                placeholders['pf_creator_stats'] = f"https://t.me/phanes_bot?start=pfdev_{creator}"

            timestamp_mappings = {
                'pf_created_timestamp': pf.get('created_timestamp'),
                'pf_last_trade_timestamp': pf.get('last_trade_timestamp'),
                'pf_ath_market_cap_timestamp': pf.get('ath_market_cap_timestamp'),
                'pf_koth_timestamp': pf.get('king_of_the_hill_timestamp'),
                'pf_livestream_ban_expiry': pf.get('livestream_ban_expiry'),
                'pf_updated_at': pf.get('updated_at'),
                'pf_last_reply': pf.get('last_reply'),
                'pf_thumbnail_updated_at': pf.get('thumbnail_updated_at'),
            }

            for base_key, raw_value in timestamp_mappings.items():
                iso_key = f"{base_key}_iso"
                ago_key = f"{base_key}_ago"
                if raw_value is not None:
                    placeholders[base_key] = str(raw_value)
                    formatted = format_timestamp_value(raw_value)
                    placeholders[iso_key] = formatted['iso']
                    placeholders[ago_key] = formatted['ago']
                else:
                    placeholders[base_key] = 'N/A'
                    placeholders[iso_key] = 'N/A'
                    placeholders[ago_key] = 'N/A'

            placeholders['pf_total_supply'] = format_int(pf.get('total_supply'))
            placeholders['pf_market_cap_sol'] = format_number(pf.get('market_cap'))
            placeholders['pf_market_cap_usd'] = format_market_cap(pf.get('usd_market_cap'))
            placeholders['pf_ath_market_cap'] = format_market_cap(pf.get('ath_market_cap'))
            placeholders['pf_real_sol_reserves'] = format_number(pf.get('real_sol_reserves'))
            placeholders['pf_virtual_sol_reserves'] = format_number(pf.get('virtual_sol_reserves'))
            placeholders['pf_virtual_token_reserves'] = format_number(pf.get('virtual_token_reserves'), decimals=0)
            placeholders['pf_real_token_reserves'] = format_number(pf.get('real_token_reserves'), decimals=0)
            placeholders['pf_reply_count'] = format_int(pf.get('reply_count'))
            placeholders['pf_num_participants'] = format_int(pf.get('num_participants'))
            placeholders['pf_is_currently_live'] = format_bool(pf.get('is_currently_live'))
            placeholders['pf_complete'] = format_bool(pf.get('complete'))
            placeholders['pf_raydium_pool'] = pf.get('raydium_pool') or 'N/A'
            placeholders['pf_pump_swap_pool'] = pf.get('pump_swap_pool') or 'N/A'
            placeholders['pf_hidden'] = format_bool(pf.get('hidden'))
            placeholders['pf_show_name'] = format_bool(pf.get('show_name'))
            placeholders['pf_nsfw'] = format_bool(pf.get('nsfw'))
            placeholders['pf_inverted'] = format_bool(pf.get('inverted'))
            placeholders['pf_is_banned'] = format_bool(pf.get('is_banned'))
            placeholders['pf_initialized'] = format_bool(pf.get('initialized'))
            placeholders['pf_hide_banner'] = format_bool(pf.get('hide_banner'))
            placeholders['pf_livestream_downrank_score'] = format_number(pf.get('livestream_downrank_score'))
            placeholders['pf_downrank_score'] = format_number(pf.get('downrank_score'))
            placeholders['pf_program'] = pf.get('program') or 'N/A'
            placeholders['pf_platform'] = pf.get('platform') or 'N/A'
            placeholders['pf_market_id'] = pf.get('market_id') or 'N/A'
            placeholders['pf_banner_uri'] = pf.get('banner_uri') or 'N/A'
            placeholders['pf_thumbnail_uri'] = pf.get('thumbnail') or 'N/A'
            placeholders['pf_video_uri'] = pf.get('video_uri') or 'N/A'

            # ATH comparison calculation
            current_mc = pf.get('usd_market_cap', 0)
            ath_mc = pf.get('ath_market_cap', 0)
            ath_timestamp = pf.get('ath_market_cap_timestamp')

            if current_mc and ath_mc and current_mc > 0 and ath_mc > 0:
                ratio = float(current_mc) / float(ath_mc)
                ath_comparison = f"{ratio:.2f}x from ATH"

                # Add time component if ATH timestamp exists
                if ath_timestamp:
                    try:
                        ts_int = int(ath_timestamp)
                        if ts_int > 1_000_000_000_000:
                            ts_int = ts_int // 1000
                        dt = datetime.fromtimestamp(ts_int, tz=timezone.utc)
                        now = datetime.now(timezone.utc)
                        diff = now - dt

                        # Convert to compact format (Xh:Ym)
                        hours = int(diff.total_seconds() // 3600)
                        minutes = int((diff.total_seconds() % 3600) // 60)

                        if hours > 0:
                            time_str = f"{hours}h:{minutes:02d}m"
                        else:
                            time_str = f"{minutes}m"

                        ath_comparison += f" ({time_str})"
                    except (ValueError, OSError, OverflowError):
                        pass

                placeholders['pf_ath_comparison'] = ath_comparison
            else:
                placeholders['pf_ath_comparison'] = 'N/A'

        if jupiter_payload:
            jup = jupiter_payload
            placeholders['jup_id'] = jup.get('id') or 'N/A'
            placeholders['jup_name'] = jup.get('name') or 'N/A'
            placeholders['jup_symbol'] = jup.get('symbol') or 'N/A'
            placeholders['jup_icon'] = jup.get('icon') or 'N/A'
            placeholders['jup_decimals'] = get_map_value(jup, 'decimals') or 'N/A'
            placeholders['jup_token_program'] = get_map_value(jup, 'token_program', 'tokenProgram') or 'N/A'
            placeholders['jup_launchpad'] = get_map_value(jup, 'launchpad') or 'N/A'

            first_pool = get_map_value(jup, 'first_pool', 'firstPool') or {}
            placeholders['jup_first_pool_id'] = get_map_value(first_pool, 'id') or 'N/A'
            placeholders['jup_first_pool_created_at'] = get_map_value(first_pool, 'created_at', 'createdAt') or 'N/A'
            placeholders['jup_graduated_pool'] = get_map_value(jup, 'graduated_pool', 'graduatedPool') or 'N/A'
            placeholders['jup_graduated_at'] = get_map_value(jup, 'graduated_at', 'graduatedAt') or 'N/A'

            placeholders['jup_holder_count'] = format_int(get_map_value(jup, 'holder_count', 'holderCount'))
            placeholders['jup_updated_at'] = get_map_value(jup, 'updated_at', 'updatedAt') or 'N/A'
            placeholders['jup_circ_supply'] = format_number(get_map_value(jup, 'circ_supply', 'circSupply'), decimals=2)
            placeholders['jup_total_supply'] = format_number(get_map_value(jup, 'total_supply', 'totalSupply'), decimals=2)
            placeholders['jup_usd_price'] = format_number(get_map_value(jup, 'usd_price', 'usdPrice'), decimals=10)
            placeholders['jup_mcap'] = format_market_cap(get_map_value(jup, 'mcap'))
            placeholders['jup_fdv'] = format_market_cap(get_map_value(jup, 'fdv'))
            placeholders['jup_liquidity'] = format_market_cap(get_map_value(jup, 'liquidity'))
            placeholders['jup_bonding_curve'] = format_number(get_map_value(jup, 'bonding_curve', 'bondingCurve'))
            price_block_id = get_map_value(jup, 'price_block_id', 'priceBlockId')
            placeholders['jup_price_block_id'] = str(price_block_id) if price_block_id is not None else 'N/A'

            placeholders['jup_is_verified'] = format_bool(get_map_value(jup, 'is_verified', 'isVerified'))

            audit = get_map_value(jup, 'audit') or {}
            placeholders['jup_audit_mint_authority_disabled'] = format_bool(get_map_value(audit, 'mint_authority_disabled', 'mintAuthorityDisabled'))
            placeholders['jup_audit_freeze_authority_disabled'] = format_bool(get_map_value(audit, 'freeze_authority_disabled', 'freezeAuthorityDisabled'))
            placeholders['jup_audit_top_holders_pct'] = format_number(get_map_value(audit, 'top_holders_percentage', 'topHoldersPercentage'))
            placeholders['jup_audit_snipers_pct'] = format_number(get_map_value(audit, 'snipers_holding_percentage', 'snipersHoldingPercentage'))
            placeholders['jup_audit_dev_migrations'] = format_int(get_map_value(audit, 'dev_migrations', 'devMigrations'))
            placeholders['jup_audit_dev_balance_pct'] = format_number(get_map_value(audit, 'dev_balance_percentage', 'devBalancePercentage'))

            placeholders['jup_dev_address'] = get_map_value(jup, 'dev') or 'N/A'

            placeholders['jup_organic_score'] = format_number(get_map_value(jup, 'organic_score', 'organicScore'))
            placeholders['jup_organic_score_label'] = get_map_value(jup, 'organic_score_label', 'organicScoreLabel') or 'N/A'

            tags = get_map_value(jup, 'tags') or []
            placeholders['jup_tags'] = ', '.join(tags) if tags else 'N/A'

            placeholders['jup_ct_likes'] = format_int(get_map_value(jup, 'ct_likes', 'ctLikes'))
            placeholders['jup_smart_ct_likes'] = format_int(get_map_value(jup, 'smart_ct_likes', 'smartCtLikes'))
            placeholders['jup_twitter'] = get_map_value(jup, 'twitter') or 'N/A'
            placeholders['jup_telegram'] = get_map_value(jup, 'telegram') or 'N/A'
            placeholders['jup_website'] = get_map_value(jup, 'website') or 'N/A'

            cexes = get_map_value(jup, 'cexes') or []
            placeholders['jup_cexes'] = ', '.join(cexes) if cexes else 'N/A'

            stats_map = {
                '5m': get_map_value(jup, 'stats_5m', 'stats5m') or {},
                '1h': get_map_value(jup, 'stats_1h', 'stats1h') or {},
                '6h': get_map_value(jup, 'stats_6h', 'stats6h') or {},
                '24h': get_map_value(jup, 'stats_24h', 'stats24h') or {},
            }

            for timeframe, stats in stats_map.items():
                placeholders[f'jup_stats_{timeframe}_price_change'] = format_number(get_map_value(stats, 'price_change', 'priceChange'))
                placeholders[f'jup_stats_{timeframe}_holder_change'] = format_number(get_map_value(stats, 'holder_change', 'holderChange'))
                placeholders[f'jup_stats_{timeframe}_liquidity_change'] = format_number(get_map_value(stats, 'liquidity_change', 'liquidityChange'))
                placeholders[f'jup_stats_{timeframe}_volume_change'] = format_number(get_map_value(stats, 'volume_change', 'volumeChange'))
                placeholders[f'jup_stats_{timeframe}_buy_volume'] = format_market_cap(get_map_value(stats, 'buy_volume', 'buyVolume'))
                placeholders[f'jup_stats_{timeframe}_sell_volume'] = format_market_cap(get_map_value(stats, 'sell_volume', 'sellVolume'))
                placeholders[f'jup_stats_{timeframe}_buy_organic_volume'] = format_market_cap(get_map_value(stats, 'buy_organic_volume', 'buyOrganicVolume'))
                placeholders[f'jup_stats_{timeframe}_sell_organic_volume'] = format_market_cap(get_map_value(stats, 'sell_organic_volume', 'sellOrganicVolume'))
                placeholders[f'jup_stats_{timeframe}_num_buys'] = format_int(get_map_value(stats, 'num_buys', 'numBuys'))
                placeholders[f'jup_stats_{timeframe}_num_sells'] = format_int(get_map_value(stats, 'num_sells', 'numSells'))
                placeholders[f'jup_stats_{timeframe}_num_traders'] = format_int(get_map_value(stats, 'num_traders', 'numTraders'))
                placeholders[f'jup_stats_{timeframe}_num_organic_buyers'] = format_int(get_map_value(stats, 'num_organic_buyers', 'numOrganicBuyers'))
                placeholders[f'jup_stats_{timeframe}_num_net_buyers'] = format_int(get_map_value(stats, 'num_net_buyers', 'numNetBuyers'))

        if dev_sol_balance is not None:
            placeholders['jup_dev_sol_balance'] = format_number(dev_sol_balance, decimals=4)

        if holders_payload:
            holders_result = holders_payload.get('result') or {}
            context = holders_result.get('context') or {}
            holder_list = holders_result.get('value') or []

            slot = context.get('slot')
            placeholders['helius_data_slot'] = str(slot) if slot is not None else 'N/A'
            placeholders['helius_holder_count'] = str(len(holder_list))

            total_ui = 0.0
            holder_entries = []
            for idx, holder in enumerate(holder_list[:20], start=1):
                address = holder.get('address') or 'N/A'
                ui_amount = holder.get('uiAmount')
                ui_amount_value = float(ui_amount) if isinstance(ui_amount, (int, float)) else 0.0
                ui_amount_string = holder.get('uiAmountString') or 'N/A'
                raw_amount = holder.get('amount') or 'N/A'
                decimals = holder.get('decimals')

                total_ui += ui_amount_value
                short_addr = address[:6] + '...' + address[-6:] if len(address) > 12 else address

                placeholders[f'helius_holder_{idx}_address'] = address
                placeholders[f'helius_holder_{idx}_short'] = short_addr
                placeholders[f'helius_holder_{idx}_ui_amount'] = format_number(ui_amount_value, decimals=6)
                placeholders[f'helius_holder_{idx}_ui_amount_string'] = ui_amount_string
                placeholders[f'helius_holder_{idx}_raw_amount'] = raw_amount
                placeholders[f'helius_holder_{idx}_decimals'] = decimals if decimals is not None else 'N/A'

                holder_entries.append({
                    'index': idx,
                    'address': address,
                    'ui_amount': ui_amount_value,
                    'ui_amount_fmt': format_number(ui_amount_value, decimals=6),
                    'ui_amount_string': ui_amount_string,
                    'raw_amount': raw_amount,
                    'short': short_addr,
                })

            placeholders['helius_holder_total_ui_amount'] = format_number(total_ui, decimals=6)

            if total_ui > 0:
                ranges = [(1, 'helius_top1'), (5, 'helius_top5'), (10, 'helius_top10'), (20, 'helius_top20')]
                for cutoff, prefix in ranges:
                    subset = [entry for entry in holder_entries if entry['index'] <= cutoff]
                    subset_total = sum(entry['ui_amount'] for entry in subset)
                    placeholders[f'{prefix}_ui_amount'] = format_number(subset_total, decimals=6)
                    placeholders[f'{prefix}_share'] = format_number((subset_total / total_ui) * 100.0, decimals=2)

                top20 = placeholders.get('helius_top20_share')
                if top20 not in (None, 'N/A'):
                    try:
                        placeholders['helius_remaining_share'] = format_number(100.0 - float(top20), decimals=2)
                    except ValueError:
                        placeholders['helius_remaining_share'] = 'N/A'

                for entry in holder_entries:
                    placeholders[f"helius_holder_{entry['index']}_percent_of_sample"] = format_number(
                        (entry['ui_amount'] / total_ui) * 100.0,
                        decimals=2,
                    )

            supply_value = None
            if supply_ui_amount is not None:
                try:
                    supply_value = float(supply_ui_amount)
                except (TypeError, ValueError):
                    supply_value = None

            if supply_value and supply_value > 0:
                for entry in holder_entries:
                    placeholders[f"helius_holder_{entry['index']}_percent_of_supply"] = format_number(
                        (entry['ui_amount'] / supply_value) * 100.0,
                        decimals=2,
                    )

            holder_lines = []
            for entry in holder_entries:
                share = placeholders.get(f"helius_holder_{entry['index']}_percent_of_sample", 'N/A')
                holder_lines.append(
                    f"{entry['index']}. {entry['short']} | Amount: {entry['ui_amount_fmt']} | Raw: {entry['raw_amount']} | Share: {share}%"
                )
            if holder_lines:
                placeholders['helius_holder_table'] = '\n'.join(holder_lines)

            creator_addr = placeholders.get('pf_creator')
            if not creator_addr or creator_addr == 'N/A':
                creator_addr = placeholders.get('jup_dev_address')

            if creator_addr and creator_addr != 'N/A':
                match_entry = next((entry for entry in holder_entries if entry['address'] == creator_addr), None)
                if match_entry:
                    placeholders['helius_creator_is_holder'] = 'Yes'
                    placeholders['helius_creator_holding_ui_amount'] = match_entry['ui_amount_fmt']
                    placeholders['helius_creator_holding_ui_amount_string'] = match_entry['ui_amount_string']
                    placeholders['helius_creator_holding_raw_amount'] = match_entry['raw_amount']
                    placeholders['helius_creator_holding_percent_of_sample'] = placeholders.get(
                        f"helius_holder_{match_entry['index']}_percent_of_sample",
                        'N/A',
                    )
                    if supply_value and supply_value > 0:
                        placeholders['helius_creator_holding_percent_of_supply'] = format_number(
                            (match_entry['ui_amount'] / supply_value) * 100.0,
                            decimals=2,
                        )
                else:
                    placeholders['helius_creator_is_holder'] = 'No'

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
                multiplier = (float(current_mc) / float(initial_mc))
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
