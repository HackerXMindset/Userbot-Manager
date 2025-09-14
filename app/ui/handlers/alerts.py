from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import json
from app.userbot.session_manager import SessionManager

logger = logging.getLogger(__name__)

class AlertsHandler:
    """Alert configuration handler - now re-enabled"""
    
    def __init__(self, db, keyboards):
        self.db = db
        self.keyboards = keyboards
        logger.info("AlertsHandler enabled - alert configuration available")
    
    async def show_alerts_menu(self, query: types.CallbackQuery):
        """Show alerts configuration menu"""
        try:
            # Get current thresholds
            gain_settings = await self.db.fetchval("SELECT value FROM settings WHERE key = 'gain_multipliers'")
            drop_settings = await self.db.fetchval("SELECT value FROM settings WHERE key = 'drop_percentage'")
            
            gain_multipliers = json.loads(gain_settings) if gain_settings else [2, 7, 25]
            drop_percentage = float(json.loads(drop_settings)) if drop_settings else 0.70
            
            # Format thresholds display
            thresholds_text = ", ".join([f"{x}x" for x in sorted(gain_multipliers)])
            drop_text = f"{drop_percentage*100:.0f}%"
            
            text = (
                f"<b>🚨 Alert Configuration</b>\n\n"
                f"<b>📈 Gain Thresholds:</b>\n"
                f"├ Current: {thresholds_text}\n"
                f"└ Triggers /pnl when tokens hit these multipliers\n\n"
                f"<b>📉 Stop-Loss Threshold:</b>\n"
                f"├ Current: -{drop_text} from peak\n"
                f"└ Stops monitoring when tokens drop this much\n\n"
                f"<b>💡 Status:</b> ✅ Active"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📈 Configure Gains", callback_data="alerts:gains"),
                    InlineKeyboardButton(text="📉 Configure Drop", callback_data="alerts:drop")
                ],
                [InlineKeyboardButton(text="🧪 Test Alert", callback_data="alerts:test")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing alerts menu: {e}")
            await query.message.edit_text(
                "❌ Error loading alerts configuration",
                reply_markup=self.keyboards.back_button("menu:main")
            )
    
    async def handle_alerts_action(self, query: types.CallbackQuery):
        """Handle alerts configuration actions"""
        try:
            action = query.data.split(':', 1)[1]
            
            if action == "gains":
                await self.show_gains_config(query)
            elif action == "drop": 
                await self.show_drop_config(query)
            elif action == "test":
                await self.test_alert_system(query)
            elif action == "menu":
                await self.show_alerts_menu(query)
            else:
                await query.answer("❌ Unknown action")
                
        except Exception as e:
            logger.error(f"Error handling alerts action: {e}")
            await query.answer("❌ Error processing action")
    
    async def show_gains_config(self, query: types.CallbackQuery):
        """Show gain thresholds configuration"""
        try:
            gain_settings = await self.db.fetchval("SELECT value FROM settings WHERE key = 'gain_multipliers'")
            gain_multipliers = json.loads(gain_settings) if gain_settings else [2, 7, 25]
            
            # Available threshold options
            available_thresholds = [2, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100]
            
            text = (
                f"<b>📈 Gain Alert Thresholds</b>\n\n"
                f"<b>Selected:</b> {', '.join([f'{x}x' for x in sorted(gain_multipliers)])}\n\n"
                f"✅ = Enabled  ❌ = Disabled\n"
                f"Tap any threshold to toggle on/off:\n\n"
            )
            
            # Create keyboard with threshold buttons (4 per row)
            keyboard_rows = []
            for i in range(0, len(available_thresholds), 4):
                row = []
                for threshold in available_thresholds[i:i+4]:
                    is_enabled = threshold in gain_multipliers
                    status = "✅" if is_enabled else "❌"
                    button_text = f"{status} {threshold}x"
                    callback_data = f"gains:toggle:{threshold}"
                    row.append(InlineKeyboardButton(text=button_text, callback_data=callback_data))
                keyboard_rows.append(row)
            
            # Add control buttons
            keyboard_rows.extend([
                [
                    InlineKeyboardButton(text="🔄 Quick: 2x,5x,10x", callback_data="gains:quick:conservative"),
                    InlineKeyboardButton(text="🚀 Quick: 2x,25x,100x", callback_data="gains:quick:moon")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="alerts:menu")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing gains config: {e}")
            await query.answer("❌ Error loading gains config")
    
    async def show_drop_config(self, query: types.CallbackQuery):
        """Show drop threshold configuration"""  
        try:
            logger.debug("Entering show_drop_config")
            drop_settings = await self.db.fetchval("SELECT value FROM settings WHERE key = 'drop_percentage'")
            logger.debug(f"Fetched drop_settings from DB: {drop_settings}")
            
            drop_percentage = float(json.loads(drop_settings)) if drop_settings else 0.70
            logger.debug(f"Calculated drop_percentage: {drop_percentage}")

            text = (
                f"<b>📉 Stop-Loss Configuration</b>\n\n"
                f"Current: -{drop_percentage*100:.0f}% from peak\n\n"
                f"When tokens drop this much from their highest multiplier, "
                f"monitoring will stop to prevent further losses.\n\n"
                f"<b>Quick Settings:</b>"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="-50%", callback_data="drop:set:0.50"),
                    InlineKeyboardButton(text="-70%", callback_data="drop:set:0.70"),
                    InlineKeyboardButton(text="-90%", callback_data="drop:set:0.90")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="alerts:menu")]
            ])
            
            logger.debug("Displaying drop config menu")
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing drop config: {e}")
            await query.answer("❌ Error loading drop config")
    
    async def test_alert_system(self, query: types.CallbackQuery):
        """Test the alert system with a sample token"""
        try:
            # Get a sample active token for testing
            test_token = await self.db.fetchrow("""
                SELECT * FROM tokens_tracked 
                WHERE status = 'active' AND first_seen_mc > 0 
                ORDER BY created_at DESC 
                LIMIT 1
            """)
            
            if not test_token:
                await query.answer("❌ No active tokens found for testing")
                return
            
            # Get a working userbot with session string
            userbot = await self.db.fetchrow("""
                SELECT id, session_string FROM bots 
                WHERE kind = 'userbot' AND session_string IS NOT NULL 
                LIMIT 1
            """)
            
            if not userbot:
                await query.answer("❌ No userbot available for testing")
                return
            
            # Send test alert directly via userbot client
            session_manager = SessionManager(userbot['id'], userbot['session_string'])
            success = await session_manager.initialize_client()
            
            if not success:
                await query.answer("❌ Failed to initialize userbot client")
                return
                
            client = session_manager.get_client()
            message = f"/pnl {test_token['address']}"
            target_chat_id = -1001561952101
            
            # Send message directly
            sent_message = await client.send_message(target_chat_id, message)
            
            text = (
                f"<b>🧪 Test Alert SENT</b>\n\n"
                f"Token: {test_token['address'][:8]}...{test_token['address'][-8:]}\n"
                f"Command: /pnl {test_token['address']}\n\n"
                f"✅ Test alert sent directly!\n"
                f"Message ID: {sent_message.id}"
            )
            
            await query.message.edit_text(
                text, 
                reply_markup=self.keyboards.back_button("alerts:menu")
            )
            
            logger.info(f"Test alert sent directly for token {test_token['address'][:8]}... (msg_id: {sent_message.id})")
            
        except Exception as e:
            logger.error(f"Error testing alert system: {e}")
            await query.answer("❌ Error sending test alert")
    
    async def handle_gains_preset(self, query: types.CallbackQuery):
        """Handle gain configuration actions"""
        try:
            logger.info(f"[DEBUG] Gains handler called with: {query.data}")
            parts = query.data.split(':')
            action = parts[1]
            logger.info(f"[DEBUG] Action: {action}, Parts: {parts}")
            
            # Get current settings
            gain_settings = await self.db.fetchval("SELECT value FROM settings WHERE key = 'gain_multipliers'")
            current_multipliers = json.loads(gain_settings) if gain_settings else [2, 7, 25]
            
            if action == "toggle":
                logger.info(f"[DEBUG] Executing toggle branch")
                # Toggle individual threshold
                threshold = int(parts[2])
                logger.info(f"[DEBUG] Threshold: {threshold}")
                if threshold in current_multipliers:
                    current_multipliers.remove(threshold)
                    status_msg = f"❌ Disabled {threshold}x alerts"
                else:
                    current_multipliers.append(threshold)
                    status_msg = f"✅ Enabled {threshold}x alerts"
                
                logger.info(f"[DEBUG] New multipliers: {current_multipliers}")
                
                # Save changes immediately
                await self.db.execute("""
                    INSERT INTO settings (key, value, updated_at) 
                    VALUES ('gain_multipliers', $1, NOW())
                    ON CONFLICT (key) DO UPDATE SET 
                        value = $1, updated_at = NOW()
                """, json.dumps(current_multipliers))
                
                logger.info(f"[DEBUG] Saved to database successfully")
                await query.answer(status_msg)
                await self.show_gains_config(query)
                
            elif action == "quick":
                logger.info(f"[DEBUG] Executing quick branch")
                # Quick preset selection
                preset = parts[2]
                logger.info(f"[DEBUG] Preset: {preset}")
                presets = {
                    'conservative': [2, 5, 10],
                    'moon': [2, 25, 100]
                }
                
                if preset in presets:
                    multipliers = presets[preset]
                    logger.info(f"[DEBUG] Setting multipliers to: {multipliers}")
                    
                    # Save immediately
                    await self.db.execute("""
                        INSERT INTO settings (key, value, updated_at) 
                        VALUES ('gain_multipliers', $1, NOW())
                        ON CONFLICT (key) DO UPDATE SET 
                            value = $1, updated_at = NOW()
                    """, json.dumps(multipliers))
                    
                    logger.info(f"[DEBUG] Quick preset saved successfully")
                    await query.answer(f"✅ Quick set: {', '.join([f'{x}x' for x in multipliers])}")
                    await self.show_gains_config(query)
                else:
                    logger.error(f"[DEBUG] Unknown preset: {preset}")
                    
            elif action == "preset":
                # Legacy preset support
                preset = parts[2]
                presets = {
                    'conservative': [2, 5, 10],
                    'aggressive': [2, 7, 25], 
                    'moon': [5, 20, 100]
                }
                
                if preset in presets:
                    multipliers = presets[preset]
                    await self.db.execute("""
                        INSERT INTO settings (key, value, updated_at) 
                        VALUES ('gain_multipliers', $1, NOW())
                        ON CONFLICT (key) DO UPDATE SET 
                            value = $1, updated_at = NOW()
                    """, json.dumps(multipliers))
                    
                    await query.answer(f"✅ Set to {preset}: {', '.join([f'{x}x' for x in multipliers])}")
                    await self.show_gains_config(query)
            
        except Exception as e:
            logger.error(f"[DEBUG] Exception in gains handler: {e}")
            logger.error(f"[DEBUG] Callback data was: {query.data}")
            await query.answer("❌ Error setting preset")
    
    async def handle_drop_setting(self, query: types.CallbackQuery):
        """Handle drop threshold setting"""
        try:
            logger.debug(f"handle_drop_setting received callback: {query.data}")
            threshold = float(query.data.split(':')[2])
            logger.debug(f"Parsed threshold value: {threshold}")

            # Update settings
            logger.debug("Updating drop_percentage in database...")
            await self.db.execute("""
                INSERT INTO settings (key, value, updated_at) 
                VALUES ('drop_percentage', $1, NOW())
                ON CONFLICT (key) DO UPDATE SET 
                    value = $1, updated_at = NOW()
            """, json.dumps(threshold))
            logger.debug("Database update complete.")
            
            await query.answer(f"✅ Stop-loss set to -{threshold*100:.0f}%")

            logger.debug("Refreshing drop config view.")
            await self.show_drop_config(query)
            
        except Exception as e:
            logger.error(f"Error setting drop threshold: {e}")
            await query.answer("❌ Error setting threshold")