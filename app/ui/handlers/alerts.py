from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
import logging

from app.ui.keyboards import Keyboards
from app.models import AlertModel

logger = logging.getLogger(__name__)

class AlertsHandler:
    """Handler for alerts configuration"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.alert_model = AlertModel(db)
    
    async def show_alerts_menu(self, query: types.CallbackQuery):
        """Display alerts configuration"""
        try:
            # Get current settings
            gains = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'gain_multipliers'"
            )
            drop = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'drop_percentage'"
            )
            
            import json
            if gains:
                try:
                    current_gains = json.loads(gains) if isinstance(gains, str) else gains
                except:
                    current_gains = [5, 10, 15]
            else:
                current_gains = [5, 10, 15]
            try:
                drop_pct = float(drop) if drop else 0.70
            except (ValueError, TypeError):
                drop_pct = 0.70
            
            # Get alert stats
            alerts_today = await self.db.fetchval("""
                SELECT COUNT(*) FROM alerts 
                WHERE triggered_at > CURRENT_DATE
            """)
            
            text = (
                f"<b>🚨 Alerts Configuration</b>\n\n"
                f"<b>Current Settings:</b>\n"
                f"├ Gain Thresholds: {', '.join([f'{g}x' for g in current_gains])}\n"
                f"├ Drop Threshold: {drop_pct*100:.0f}%\n"
                f"└ Alerts Today: {alerts_today}\n\n"
                f"<b>How it works:</b>\n"
                f"• Post /pnl when token hits gain thresholds\n"
                f"• Stop tracking globally at {drop_pct*100:.0f}% drop\n"
                f"• Each threshold fires once per token"
            )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.alerts_config(current_gains, drop_pct)
            )
            
        except Exception as e:
            logger.error(f"Error showing alerts menu: {e}")
            await query.answer("❌ Error loading alerts configuration")
    
    async def handle_alerts_action(self, query: types.CallbackQuery):
        """Handle alerts-related callbacks"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'gains':
            await self.show_add_gain(query)
        elif action == 'drop':
            await self.show_drop_editor(query)
        elif action == 'add_gain':
            await self.show_add_gain(query)
        elif action == 'remove_gain':
            await self.show_remove_gain(query)
        elif action == 'set_drop':
            await self.show_drop_editor(query)
        elif action == 'per_group':
            await self.show_per_group_alerts(query)
        elif action == 'reset_gains':
            await self.reset_gains_to_default(query)
    
    async def show_gains_editor(self, query: types.CallbackQuery):
        """Show gain thresholds editor"""
        try:
            gains = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'gain_multipliers'"
            )
            import json
            if gains:
                try:
                    current_gains = json.loads(gains) if isinstance(gains, str) else gains
                except:
                    current_gains = [5, 10, 15]
            else:
                current_gains = [5, 10, 15]
            
            text = (
                f"<b>📈 Gain Thresholds</b>\n\n"
                f"Current: {', '.join([f'{g}x' for g in current_gains])}\n\n"
                f"These are the multipliers that trigger alerts.\n"
                f"Each threshold fires once per token."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Add Threshold", callback_data="alerts:add_gain"),
                    InlineKeyboardButton(text="➖ Remove Threshold", callback_data="alerts:remove_gain")
                ],
                [
                    InlineKeyboardButton(text="🔄 Reset to Default", callback_data="alerts:reset_gains")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:alerts")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing gains editor: {e}")
            await query.answer("❌ Error loading gains settings")
    
    async def show_drop_editor(self, query: types.CallbackQuery):
        """Show drop threshold editor"""
        try:
            drop = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'drop_percentage'"
            )
            try:
                drop_pct = float(drop) if drop else 0.70
            except (ValueError, TypeError):
                drop_pct = 0.70
            
            text = (
                f"<b>📉 Drop Threshold</b>\n\n"
                f"Current: {drop_pct*100:.0f}%\n\n"
                f"When a token drops by this percentage from its peak,\n"
                f"it will be stopped globally across all groups."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="40%", callback_data="drop:set:0.40"),
                    InlineKeyboardButton(text="50%", callback_data="drop:set:0.50"),
                    InlineKeyboardButton(text="60%", callback_data="drop:set:0.60")
                ],
                [
                    InlineKeyboardButton(text="70%", callback_data="drop:set:0.70"),
                    InlineKeyboardButton(text="75%", callback_data="drop:set:0.75"),
                    InlineKeyboardButton(text="80%", callback_data="drop:set:0.80")
                ],
                [
                    InlineKeyboardButton(text="85%", callback_data="drop:set:0.85"),
                    InlineKeyboardButton(text="90%", callback_data="drop:set:0.90"),
                    InlineKeyboardButton(text="95%", callback_data="drop:set:0.95")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:alerts")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing drop editor: {e}")
            await query.answer("❌ Error loading drop settings")
    
    async def show_recent_alerts(self, query: types.CallbackQuery):
        """Show recent alerts"""
        try:
            recent_alerts = await self.alert_model.get_recent_alerts(hours=24)
            
            text = "<b>🚨 Recent Alerts (24h)</b>\n\n"
            
            if not recent_alerts:
                text += "No alerts in the last 24 hours."
            else:
                for alert in recent_alerts[:10]:
                    address_short = f"{alert['address'][:8]}...{alert['address'][-8:]}"
                    multiplier = alert['multiplier']
                    time_str = alert['triggered_at'].strftime('%H:%M')
                    text += f"• {time_str}: {address_short} hit {multiplier}x\n"
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:alerts")
            )
            
        except Exception as e:
            logger.error(f"Error showing recent alerts: {e}")
            await query.answer("❌ Error loading recent alerts")
    
    async def update_gain_thresholds(self, thresholds: List[int]):
        """Update gain thresholds in database with validation"""
        try:
            # Validate thresholds
            if not thresholds:
                raise ValueError("Must have at least one gain threshold")
            
            # Ensure all values are positive integers
            validated = []
            for t in thresholds:
                if not isinstance(t, (int, float)) or t <= 0:
                    raise ValueError(f"Invalid threshold: {t}. Must be positive number")
                if t > 1000:
                    raise ValueError(f"Threshold {t} too large. Maximum is 1000x")
                validated.append(int(t))
            
            # Remove duplicates and sort
            validated = sorted(list(set(validated)))
            
            import json
            await self.db.execute(
                "INSERT INTO settings (key, value) VALUES ('gain_multipliers', $1) ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()",
                json.dumps(validated)
            )
        except Exception as e:
            logger.error(f"Error updating gain thresholds: {e}")
            raise
    
    async def update_drop_threshold(self, percentage: float):
        """Update drop threshold in database with validation"""
        try:
            # Validate percentage
            if not isinstance(percentage, (int, float)):
                raise ValueError(f"Invalid percentage: {percentage}. Must be a number")
            
            if percentage <= 0 or percentage >= 1:
                raise ValueError(f"Drop percentage {percentage*100:.1f}% invalid. Must be between 1% and 99%")
            
            await self.db.execute(
                "INSERT INTO settings (key, value) VALUES ('drop_percentage', $1) ON CONFLICT (key) DO UPDATE SET value = $1, updated_at = NOW()",
                str(float(percentage))
            )
        except Exception as e:
            logger.error(f"Error updating drop threshold: {e}")
            raise
    
    async def show_add_gain(self, query: types.CallbackQuery):
        """Show interface to add a new gain threshold"""
        try:
            gains = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'gain_multipliers'"
            )
            import json
            if gains:
                try:
                    current_gains = json.loads(gains) if isinstance(gains, str) else gains
                except:
                    current_gains = [5, 10, 15]
            else:
                current_gains = [5, 10, 15]
            
            text = (
                f"<b>📈 Gain Thresholds</b>\n\n"
                f"Current: {', '.join([f'{g}x' for g in current_gains])}\n\n"
                f"<b>Add new threshold:</b>"
            )
            
            # Suggest common thresholds that aren't already added
            all_options = [2, 3, 4, 5, 7, 10, 15, 20, 25, 30, 50, 100]
            available = [x for x in all_options if x not in current_gains]
            
            keyboard_rows = []
            for i in range(0, len(available), 4):
                row = []
                for j in range(i, min(i + 4, len(available))):
                    threshold = available[j]
                    row.append(InlineKeyboardButton(
                        text=f"{threshold}x",
                        callback_data=f"gain:add:{threshold}"
                    ))
                keyboard_rows.append(row)
            
            # Add remove options if there are current gains
            if len(current_gains) > 1:
                keyboard_rows.append([
                    InlineKeyboardButton(text="─────── Remove ───────", callback_data="ignore")
                ])
                for threshold in current_gains:
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            text=f"🗑️ Remove {threshold}x",
                            callback_data=f"gain:remove:{threshold}"
                        )
                    ])
            
            # Reset and back buttons
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔄 Reset to Default", callback_data="alerts:reset_gains")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:alerts")]
            ])
            
            await query.message.edit_text(
                text, 
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            )
            
        except Exception as e:
            logger.error(f"Error showing add gain: {e}")
            await query.answer("❌ Error loading add gain interface")
    
    async def show_remove_gain(self, query: types.CallbackQuery):
        """Show interface to remove a gain threshold"""
        try:
            gains = await self.db.fetchval(
                "SELECT value FROM settings WHERE key = 'gain_multipliers'"
            )
            import json
            if gains:
                try:
                    current_gains = json.loads(gains) if isinstance(gains, str) else gains
                except:
                    current_gains = [5, 10, 15]
            else:
                current_gains = [5, 10, 15]
            
            if len(current_gains) <= 1:
                await query.answer("❌ Must have at least one gain threshold")
                return
            
            text = (
                f"<b>➖ Remove Gain Threshold</b>\n\n"
                f"Select a threshold to remove:"
            )
            
            keyboard_rows = []
            for threshold in current_gains:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"Remove {threshold}x",
                        callback_data=f"gain:remove:{threshold}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="alerts:gains")
            ])
            
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            )
            
        except Exception as e:
            logger.error(f"Error showing remove gain: {e}")
            await query.answer("❌ Error loading remove gain interface")
    
    async def show_per_group_alerts(self, query: types.CallbackQuery):
        """Show per-group alerts configuration"""
        try:
            # Get groups with their alert settings  
            groups = await self.db.fetch("""
                SELECT g.*, 
                       s1.value as gain_overrides_raw,
                       s2.value as drop_override_raw
                FROM groups g
                LEFT JOIN settings s1 ON s1.key = 'group_' || g.id || '_gains'
                LEFT JOIN settings s2 ON s2.key = 'group_' || g.id || '_drop'
                WHERE g.enabled = true
                ORDER BY g.title
            """)
            
            text = "<b>🎯 Per-Group Alert Settings</b>\n\n"
            
            if not groups:
                text += "No active groups found."
            else:
                text += "Configure different alert thresholds per group:\n\n"
                
                # Get global defaults
                global_gains = await self.db.fetchval(
                    "SELECT value FROM settings WHERE key = 'gain_multipliers'"
                )
                global_drop = await self.db.fetchval(
                    "SELECT value FROM settings WHERE key = 'drop_percentage'"
                )
                
                import json
                default_gains = [5, 10, 15]
                if global_gains:
                    try:
                        default_gains = json.loads(global_gains) if isinstance(global_gains, str) else global_gains
                    except:
                        pass
                
                default_drop = 0.70
                if global_drop:
                    try:
                        default_drop = float(global_drop)
                    except:
                        pass
                
                for group in groups[:5]:  # Limit display
                    title = group['title'] or f"Chat {group['tg_chat_id']}"
                    
                    # Parse group-specific gains or use global default
                    group_gains = default_gains
                    if group['gain_overrides_raw']:
                        try:
                            if isinstance(group['gain_overrides_raw'], str):
                                group_gains = json.loads(group['gain_overrides_raw'])
                            elif isinstance(group['gain_overrides_raw'], list):
                                group_gains = group['gain_overrides_raw']
                            else:
                                # Handle other types by converting to list
                                group_gains = list(group['gain_overrides_raw']) if group['gain_overrides_raw'] else default_gains
                        except (json.JSONDecodeError, TypeError) as e:
                            logger.error(f"Error parsing group gains for group {group['id']}: {e}")
                            group_gains = default_gains
                    
                    # Parse group-specific drop or use global default  
                    group_drop = default_drop
                    if group['drop_override_raw']:
                        try:
                            group_drop = float(group['drop_override_raw'])
                        except:
                            pass
                    
                    # Ensure gains are integers and format properly
                    try:
                        gains = ', '.join([f"{int(g)}x" for g in group_gains if isinstance(g, (int, float, str)) and str(g).replace('.','').isdigit()])
                    except (ValueError, TypeError):
                        gains = "5x, 10x, 15x"  # Fallback
                    drop = f"{group_drop*100:.0f}%"
                    text += f"<b>{title}</b>\n├ Gains: {gains}\n└ Drop: {drop}\n\n"
            
            keyboard_rows = []
            for group in groups[:5]:
                title = group['title'] or f"ID: {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"⚙️ {title}",
                        callback_data=f"group_alerts:{group['id']}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:alerts")
            ])
            
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            )
            
        except Exception as e:
            logger.error(f"Error showing per-group alerts: {e}")
            await query.answer("❌ Error loading per-group alerts")
    
    async def reset_gains_to_default(self, query: types.CallbackQuery):
        """Reset gain thresholds to default values"""
        try:
            default_gains = [5, 10, 15]
            await self.update_gain_thresholds(default_gains)
            await query.answer("✅ Reset gains to default: 5x, 10x, 15x")
            await self.show_add_gain(query)
        except Exception as e:
            logger.error(f"Error resetting gains: {e}")
            await query.answer("❌ Error resetting gains")
