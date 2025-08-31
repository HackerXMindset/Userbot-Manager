from aiogram import types
from typing import Dict, Any
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.ui.keyboards import Keyboards
from app.models import TokenModel, GroupModel, BotModel
from app.config import settings
import time
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)

class MenuHandler:
    """Handler for main menu operations"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.token_model = TokenModel(db)
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)
        
        # Simple cache for tracking stats (5 minute TTL)
        self._stats_cache = {}
        self._cache_ttl = 300  # 5 minutes
        self._max_cache_entries = 20  # Limit cache size
    
    async def get_status_text(self) -> str:
        """Generate status overview"""
        try:
            # Get counts from database
            groups_count = await self.db.fetchval("SELECT COUNT(*) FROM groups WHERE enabled = true")
            userbots_count = await self.db.fetchval("SELECT COUNT(*) FROM bots WHERE kind = 'userbot' AND status = 'active'")
            tokens_active = await self.db.fetchval("SELECT COUNT(*) FROM tokens_tracked WHERE status = 'active'")
            calls_today = await self.db.fetchval("""
                SELECT COUNT(*) FROM calls 
                WHERE sent_at > CURRENT_DATE 
                AND status = 'sent'
            """)
            
            return (
                f"📊 <b>System Status</b>\n"
                f"├ Groups: {groups_count} active\n"
                f"├ Userbots: {userbots_count} online\n"
                f"├ Tokens: {tokens_active} tracking\n"
                f"├ Calls Today: {calls_today}\n"
                f"└ Time: {settings.get_local_time().strftime('%H:%M IST')}"
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return "⚠️ Error loading status"
    
    async def show_main_menu(self, query: types.CallbackQuery):
        """Show the main menu"""
        status_text = await self.get_status_text()
        await query.message.edit_text(
            f"<b>🎛 Management Console</b>\n\n{status_text}",
            reply_markup=self.keyboards.main_menu()
        )
    
    async def show_detailed_status(self, query: types.CallbackQuery):
        """Show detailed system status"""
        try:
            # Get detailed statistics
            token_stats = await self.token_model.get_token_stats()
            groups = await self.group_model.get_groups_with_stats()
            userbots = await self.bot_model.get_userbots_with_assignments()
            
            # Recent activity
            recent_calls = await self.db.fetchval("""
                SELECT COUNT(*) FROM calls 
                WHERE created_at > NOW() - INTERVAL '1 hour'
            """)
            
            recent_alerts = await self.db.fetchval("""
                SELECT COUNT(*) FROM alerts 
                WHERE triggered_at > NOW() - INTERVAL '1 hour'
            """)
            
            text = (
                f"<b>📊 Detailed System Status</b>\n\n"
                f"<b>🔢 Statistics:</b>\n"
                f"├ Total Groups: {len(groups)}\n"
                f"├ Active Groups: {len([g for g in groups if g['enabled']])}\n"
                f"├ Total Userbots: {len(userbots)}\n"
                f"├ Active Userbots: {len([u for u in userbots if u['status'] == 'active'])}\n"
                f"├ Tracked Tokens: {token_stats.get('total_tokens', 0)}\n"
                f"├ Active Tokens: {token_stats.get('active_tokens', 0)}\n"
                f"└ Avg Multiplier: {(token_stats.get('avg_multiplier') or 0):.2f}x\n\n"
                f"<b>📈 Recent Activity (1h):</b>\n"
                f"├ Calls: {recent_calls}\n"
                f"└ Alerts: {recent_alerts}\n\n"
                f"<b>⏰ System Info:</b>\n"
                f"├ Timezone: {settings.timezone}\n"
                f"├ DEx Poll: {settings.dex_poll_secs}s\n"
                f"└ Current Time: {settings.get_local_time().strftime('%Y-%m-%d %H:%M:%S %Z')}"
            )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:main")
            )
            
        except Exception as e:
            logger.error(f"Error showing detailed status: {e}")
            await query.message.edit_text(
                "❌ Error loading detailed status",
                reply_markup=self.keyboards.back_button("menu:main")
            )
    
    async def show_tracking_menu(self, query: types.CallbackQuery, timeframe: str = "1d"):
        """Show token tracking overview with time-based analytics"""
        try:
            # Get time-based statistics
            stats = await self.get_tracking_stats_by_time(timeframe)
            
            # Format timeframe display
            timeframe_labels = {
                "4h": "4 Hours", "12h": "12 Hours", "1d": "24 Hours", "2d": "2 Days", 
                "3d": "3 Days", "7d": "7 Days", "14d": "14 Days", "1mo": "1 Month",
                "3mo": "3 Months", "6mo": "6 Months"
            }
            
            text = (
                f"<b>📈 Tracking Analytics</b>\n\n"
                f"<b>📊 {timeframe_labels.get(timeframe, timeframe)} Stats:</b>\n"
                f"├ Tokens Tracked: {stats['tokens_tracked']}\n"
                f"├ Average Performance: {stats['avg_multiplier']:.2f}x\n"
                f"├ Success Rate: {stats['success_rate']:.1f}%\n"
                f"├ Alerts Triggered: {stats['alerts_count']}\n"
                f"├ Calls Sent: {stats['calls_sent']}\n"
                f"└ Top Performer: {stats['top_multiplier']:.2f}x\n\n"
            )
            
            if stats['top_tokens']:
                text += f"<b>🏆 Top 5 Performers ({timeframe_labels.get(timeframe)}):</b>\n"
                for i, token in enumerate(stats['top_tokens'], 1):
                    address_short = f"{token['address'][:8]}...{token['address'][-8:]}"
                    text += f"{i}. {address_short}: {token['multiplier']:.2f}x\n"
            else:
                text += "No tokens tracked in this period."
            
            # Time period selector buttons
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="4h", callback_data="tracking_time:4h"),
                    InlineKeyboardButton(text="12h", callback_data="tracking_time:12h"),
                    InlineKeyboardButton(text="1d", callback_data="tracking_time:1d"),
                    InlineKeyboardButton(text="2d", callback_data="tracking_time:2d")
                ],
                [
                    InlineKeyboardButton(text="3d", callback_data="tracking_time:3d"),
                    InlineKeyboardButton(text="7d", callback_data="tracking_time:7d"),
                    InlineKeyboardButton(text="14d", callback_data="tracking_time:14d"),
                    InlineKeyboardButton(text="1mo", callback_data="tracking_time:1mo")
                ],
                [
                    InlineKeyboardButton(text="3mo", callback_data="tracking_time:3mo"),
                    InlineKeyboardButton(text="6mo", callback_data="tracking_time:6mo")
                ],
                [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data=f"tracking_time:{timeframe}"),
                    InlineKeyboardButton(text="🧹 Cleanup", callback_data="tracking:cleanup")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            try:
                await query.message.edit_text(text, reply_markup=keyboard)
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    # Content is identical, just answer the callback
                    await query.answer("✅ Tracking data is up to date")
                else:
                    raise edit_error
            
        except Exception as e:
            logger.error(f"Error showing tracking menu: {e}")
            await query.message.edit_text(
                "❌ Error loading tracking data",
                reply_markup=self.keyboards.back_button("menu:main")
            )
    
    def _get_cache_key(self, timeframe: str) -> str:
        """Generate cache key for timeframe"""
        return f"tracking_stats_{timeframe}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self._stats_cache:
            return False
        
        cache_entry = self._stats_cache[cache_key]
        return time.time() - cache_entry['timestamp'] < self._cache_ttl
    
    def _cleanup_cache(self):
        """Remove expired entries and limit cache size"""
        current_time = time.time()
        
        # Remove expired entries
        expired_keys = [
            key for key, entry in self._stats_cache.items()
            if current_time - entry['timestamp'] > self._cache_ttl
        ]
        
        for key in expired_keys:
            del self._stats_cache[key]
        
        # If still too many entries, remove oldest ones
        if len(self._stats_cache) > self._max_cache_entries:
            # Sort by timestamp and keep only the newest entries
            sorted_entries = sorted(
                self._stats_cache.items(),
                key=lambda x: x[1]['timestamp'],
                reverse=True
            )
            
            # Keep only the newest max_cache_entries
            self._stats_cache = dict(sorted_entries[:self._max_cache_entries])
            
            logger.info(f"Cache cleanup: kept {len(self._stats_cache)} entries")
    
    async def get_tracking_stats_by_time(self, timeframe: str) -> dict:
        """Get tracking statistics for a specific time period (with caching)"""
        try:
            # Check cache first
            cache_key = self._get_cache_key(timeframe)
            if self._is_cache_valid(cache_key):
                logger.info(f"Returning cached tracking stats for {timeframe}")
                return self._stats_cache[cache_key]['data']
            # Convert timeframe to PostgreSQL interval (use days instead of months for consistency)
            interval_map = {
                "4h": "4 hours", "12h": "12 hours", "1d": "1 day", "2d": "2 days",
                "3d": "3 days", "7d": "7 days", "14d": "14 days", "1mo": "30 days",
                "3mo": "90 days", "6mo": "180 days"
            }
            
            interval = interval_map.get(timeframe, "1 day")
            
            # Get comprehensive statistics with timeout
            try:
                stats = await asyncio.wait_for(
                    self.db.fetchrow(f"""
                WITH time_period AS (
                    SELECT NOW() - INTERVAL '{interval}' AS start_time
                ),
                token_stats AS (
                    SELECT 
                        COUNT(*) as tokens_tracked,
                        AVG(CASE 
                            WHEN first_seen_mc > 0 AND last_mc > 0 
                            THEN LEAST(last_mc / first_seen_mc, 1000) -- Cap at 1000x to avoid infinity
                            ELSE 1 
                        END) as avg_multiplier,
                        MAX(CASE 
                            WHEN first_seen_mc > 0 AND last_mc > 0 
                            THEN LEAST(last_mc / first_seen_mc, 1000) -- Cap at 1000x
                            ELSE 1 
                        END) as top_multiplier,
                        COUNT(CASE WHEN status = 'active' THEN 1 END) as active_tokens,
                        COUNT(CASE WHEN status = 'stopped' THEN 1 END) as stopped_tokens
                    FROM tokens_tracked tt, time_period tp
                    WHERE tt.created_at >= tp.start_time
                ),
                alert_stats AS (
                    SELECT COUNT(*) as alerts_count
                    FROM alerts a, time_period tp
                    WHERE a.triggered_at >= tp.start_time
                ),
                call_stats AS (
                    SELECT COUNT(*) as calls_sent
                    FROM calls c, time_period tp
                    WHERE c.sent_at >= tp.start_time AND c.status = 'sent'
                )
                SELECT 
                    COALESCE(ts.tokens_tracked, 0) as tokens_tracked,
                    COALESCE(ts.avg_multiplier, 0) as avg_multiplier,
                    COALESCE(ts.top_multiplier, 0) as top_multiplier,
                    CASE 
                        WHEN COALESCE(ts.tokens_tracked, 0) > 0 
                        THEN (COALESCE(ts.active_tokens, 0)::float / ts.tokens_tracked * 100)
                        ELSE 0 
                    END as success_rate,
                    COALESCE(als.alerts_count, 0) as alerts_count,
                    COALESCE(cs.calls_sent, 0) as calls_sent
                FROM token_stats ts
                CROSS JOIN alert_stats als
                CROSS JOIN call_stats cs
            """), timeout=30.0  # 30 second timeout
                )
            except asyncio.TimeoutError:
                logger.error(f"Database query timeout for {timeframe} stats")
                return {
                    'tokens_tracked': 0, 'avg_multiplier': 0.0, 'top_multiplier': 0.0,
                    'success_rate': 0.0, 'alerts_count': 0, 'calls_sent': 0, 'top_tokens': []
                }
            
            # Get top performing tokens for the period (with division by zero protection and timeout)
            try:
                top_tokens = await asyncio.wait_for(
                    self.db.fetch(f"""
                        SELECT 
                            address,
                            CASE 
                                WHEN first_seen_mc > 0 AND last_mc > 0 
                                THEN LEAST(last_mc / first_seen_mc, 1000)
                                ELSE 1 
                            END as multiplier
                        FROM tokens_tracked
                        WHERE created_at >= NOW() - INTERVAL '{interval}'
                            AND first_seen_mc > 0 
                            AND last_mc > 0
                        ORDER BY multiplier DESC
                        LIMIT 5
                    """), timeout=15.0  # 15 second timeout for smaller query
                )
            except asyncio.TimeoutError:
                logger.error(f"Top tokens query timeout for {timeframe}")
                top_tokens = []
            
            # Prepare results
            result = {
                'tokens_tracked': int(stats['tokens_tracked'] or 0),
                'avg_multiplier': float(stats['avg_multiplier'] or 0),
                'top_multiplier': float(stats['top_multiplier'] or 0),
                'success_rate': float(stats['success_rate'] or 0),
                'alerts_count': int(stats['alerts_count'] or 0),
                'calls_sent': int(stats['calls_sent'] or 0),
                'top_tokens': [
                    {
                        'address': token['address'], 
                        'multiplier': float(token['multiplier'])
                    } for token in top_tokens
                ]
            }
            
            # Cache the results
            self._stats_cache[cache_key] = {
                'data': result,
                'timestamp': time.time()
            }
            
            # Clean up cache periodically
            self._cleanup_cache()
            
            logger.info(f"Cached new tracking stats for {timeframe}")
            return result
            
        except Exception as e:
            logger.error(f"Error getting tracking stats for {timeframe}: {e}")
            
            # Check for specific database errors and provide helpful fallbacks
            error_msg = str(e).lower()
            if "column" in error_msg and "does not exist" in error_msg:
                logger.error(f"Database schema mismatch: {e}")
                # Try a simpler fallback query
                try:
                    basic_stats = await asyncio.wait_for(
                        self.db.fetchval(f"""
                            SELECT COUNT(*) FROM tokens_tracked 
                            WHERE created_at >= NOW() - INTERVAL '{interval_map.get(timeframe, "1 day")}'
                        """), timeout=10.0
                    )
                    return {
                        'tokens_tracked': int(basic_stats or 0), 'avg_multiplier': 0.0, 'top_multiplier': 0.0,
                        'success_rate': 0.0, 'alerts_count': 0, 'calls_sent': 0, 'top_tokens': []
                    }
                except Exception as fallback_error:
                    logger.error(f"Fallback query also failed: {fallback_error}")
            elif "relation" in error_msg and "does not exist" in error_msg:
                logger.error(f"Database table missing: {e}")
            elif "timeout" in error_msg or "connection" in error_msg:
                logger.error(f"Database connection issue: {e}")
            
            return {
                'tokens_tracked': 0, 'avg_multiplier': 0.0, 'top_multiplier': 0.0,
                'success_rate': 0.0, 'alerts_count': 0, 'calls_sent': 0, 'top_tokens': []
            }
    
    async def show_settings_menu(self, query: types.CallbackQuery):
        """Show system settings"""
        try:
            # Get current settings from database
            settings_data = await self.db.fetch("SELECT key, value FROM settings")
            settings_dict = {s['key']: s['value'] for s in settings_data}
            
            text = (
                f"<b>⚙️ System Settings</b>\n\n"
                f"<b>📊 Alerts:</b>\n"
                f"├ Gain Thresholds: {settings_dict.get('gain_multipliers', [])}\n"
                f"└ Drop Threshold: {float(settings_dict.get('drop_percentage', 0.7)) * 100:.0f}%\n\n"
                f"<b>🔧 System:</b>\n"
                f"├ Timezone: {settings_dict.get('timezone', 'Asia/Kolkata')}\n"
                f"├ DEx Poll Rate: {settings_dict.get('dex_poll_secs', 5)}s\n"
                f"└ Admin ID: {settings_dict.get('admin_id', 'Not set')}\n\n"
                f"<b>📱 Telegram API:</b>\n"
                f"├ API ID: {settings.api_id}\n"
                f"└ API Hash: {'*' * 20}"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🚨 Alert Settings", callback_data="menu:alerts"),
                    InlineKeyboardButton(text="🌍 Timezone", callback_data="settings:timezone")
                ],
                [
                    InlineKeyboardButton(text="📊 DEx Settings", callback_data="settings:dex"),
                    InlineKeyboardButton(text="🔧 Advanced", callback_data="settings:advanced")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing settings: {e}")
            await query.message.edit_text(
                "❌ Error loading settings",
                reply_markup=self.keyboards.back_button("menu:main")
            )