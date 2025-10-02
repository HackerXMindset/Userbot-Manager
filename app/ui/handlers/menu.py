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
        self.cache = {}
        self.cache_time = {}
    
    def is_fresh(self, key, seconds=300):
        """Check if cache entry is fresh (default 5 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    async def get_cached_dashboard_stats(self):
        """Get dashboard stats using caching"""
        if self.is_fresh("dashboard_stats"):
            return self.cache["dashboard_stats"]
        
        stats = await self.db.fetchrow("""
            SELECT
                (SELECT COUNT(*) FROM groups WHERE enabled = true) as groups_count,
                (SELECT COUNT(*) FROM bots WHERE kind = 'userbot' AND status = 'active') as userbots_count,
                (SELECT COUNT(*) FROM tokens_tracked WHERE status = 'active') as tokens_active,
                (SELECT COUNT(*) FROM token_call_history WHERE DATE(called_at) = CURRENT_DATE) as calls_today
        """)
        
        self.cache["dashboard_stats"] = dict(stats) if stats else {}
        self.cache_time["dashboard_stats"] = time.time()
        return self.cache["dashboard_stats"]
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_time.clear()
        self._stats_cache.clear()  # Also clear old cache
    
    async def get_status_text(self) -> str:
        """Generate status overview"""
        try:
            # Use cached dashboard stats
            result = await self.get_cached_dashboard_stats()
            
            return (
                f"📊 <b>System Status</b>\n"
                f"├ Groups: {result['groups_count']} active\n"
                f"├ Userbots: {result['userbots_count']} online\n"
                f"├ Tokens: {result['tokens_active']} tracking\n"
                f"├ Calls Today: {result['calls_today']}\n"
                f"└ Time: {settings.get_local_time().strftime('%H:%M IST')}"
            )
        except Exception as e:
            logger.error(f"Error getting status: {e}")
            return "⚠️ Error loading status"
    
    async def show_main_menu(self, query: types.CallbackQuery):
        """Show the main menu"""
        try:
            status_text = await self.get_status_text()
            await query.message.edit_text(
                f"<b>🎛 Management Console</b>\n\n{status_text}",
                reply_markup=self.keyboards.main_menu()
            )
            await query.answer()
        except Exception as e:
            if "message is not modified" in str(e).lower():
                await query.answer()
            else:
                logger.error(f"Error showing main menu: {e}")
                await query.answer("❌ Error loading menu", show_alert=True)
    
    async def show_detailed_status(self, query: types.CallbackQuery):
        """Show detailed system status"""
        try:
            # Get detailed statistics
            token_stats = await self.token_model.get_token_stats()
            groups = await self.group_model.get_groups_with_stats()
            userbots = await self.bot_model.get_userbots_with_assignments()
            
            # Recent activity
            recent_calls = await self.db.fetchval("""
                SELECT COUNT(*) FROM token_call_history
                WHERE called_at > NOW() - INTERVAL '1 hour'
            """)
            
            recent_alerts = 0
            
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
                f"├ Calls Sent: {stats['calls_sent']}\n"
                f"└ Top Performer: {stats['top_multiplier']:.2f}x\n\n"
            )
            
            if stats['top_tokens']:
                text += f"<b>🏆 Top 5 Performers ({timeframe_labels.get(timeframe)}):</b>\n"
                for i, token in enumerate(stats['top_tokens'], 1):
                    display_name = f"${token['ticker']}" if token['ticker'] else f"{token['address'][:8]}..."
                    text += f"{i}. {display_name}: {token['multiplier']:.2f}x\n"
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
                )
                SELECT
                    -- Token statistics (count only new token detections)
                    (SELECT COUNT(*)
                     FROM tokens_tracked tt
                     WHERE tt.created_at >= (SELECT start_time FROM time_period)
                    ) as tokens_tracked,
                    
                    -- Average multiplier (handle nulls properly)
                    (SELECT COALESCE(AVG(CASE
                        WHEN first_seen_mc > 0 AND last_mc > 0
                        THEN LEAST(last_mc / first_seen_mc, 1000)
                        ELSE 1.0
                     END), 0.0)
                     FROM tokens_tracked tt
                     WHERE tt.created_at >= (SELECT start_time FROM time_period)
                    ) as avg_multiplier,
                    
                    -- Top multiplier
                    (SELECT COALESCE(MAX(CASE
                        WHEN first_seen_mc > 0 AND peak_mc > 0
                        THEN LEAST(peak_mc / first_seen_mc, 1000)
                        ELSE 1.0
                     END), 0.0)
                     FROM tokens_tracked tt
                     WHERE tt.created_at >= (SELECT start_time FROM time_period)
                    ) as top_multiplier,
                    
                    -- Success rate (active tokens vs total)
                    (SELECT
                        CASE
                            WHEN COUNT(*) > 0
                            THEN (COUNT(CASE WHEN status = 'active' THEN 1 END)::float / COUNT(*) * 100)
                            ELSE 0
                        END
                     FROM tokens_tracked tt
                     WHERE tt.created_at >= (SELECT start_time FROM time_period)
                    ) as success_rate,
                    
                    -- Alert count (disabled)
                    0 as alerts_count,
                    
                    -- Calls sent (count from token_call_history - new system)
                    (SELECT COUNT(*)
                     FROM token_call_history tch
                     WHERE tch.called_at >= (SELECT start_time FROM time_period)
                    ) as calls_sent
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
                            ticker,
                            CASE 
                                WHEN first_seen_mc > 0 AND peak_mc > 0 
                                THEN LEAST(peak_mc / first_seen_mc, 1000)
                                ELSE 1 
                            END as multiplier
                        FROM tokens_tracked
                        WHERE created_at >= NOW() - INTERVAL '{interval}'
                            AND first_seen_mc > 0 
                            AND peak_mc > 0
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
                        'ticker': token['ticker'],
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
    
    async def confirm_cleanup(self, query: types.CallbackQuery):
        """Show cleanup confirmation dialog"""
        try:
            text = (
                "<b>⚠️ Database Cleanup Confirmation</b>\n\n"
                "This will permanently delete:\n"
                "• All tracked tokens\n"
                "• All call records\n\n"
                "<b>This action cannot be undone!</b>\n\n"
                "Are you sure you want to proceed?"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="❌ Cancel", callback_data="tracking_time:1d"),
                    InlineKeyboardButton(text="🗑️ Delete All", callback_data="tracking:cleanup:confirm")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer()
            
        except Exception as e:
            logger.error(f"Error showing cleanup confirmation: {e}")
            await query.answer("❌ Error showing confirmation", show_alert=True)
    
    async def execute_cleanup(self, query: types.CallbackQuery):
        """Execute database cleanup after confirmation"""
        try:
            # Delete all data
            token_count = await self.db.fetchval("DELETE FROM tokens_tracked")
            await self.db.execute("DELETE FROM token_call_history")
            
            # Clear cache
            self.clear_cache()
            
            text = (
                "<b>✅ Cleanup Complete</b>\n\n"
                f"Successfully deleted:\n"
                f"• {token_count or 0} tokens\n"
                f"• All calls\n\n"
                "Database has been reset."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Tracking", callback_data="tracking_time:1d")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("🗑️ All data deleted successfully", show_alert=True)
            
        except Exception as e:
            logger.error(f"Error executing cleanup: {e}")
            await query.message.edit_text(
                "❌ Error during cleanup. Please try again.",
                reply_markup=self.keyboards.back_button("tracking_time:1d")
            )
            await query.answer("❌ Cleanup failed", show_alert=True)
    
