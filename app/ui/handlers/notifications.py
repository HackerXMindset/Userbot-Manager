from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging
import json

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import NotificationModel

logger = logging.getLogger(__name__)

class NotificationsHandler:
    """Handler for notification settings management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.notification_model = NotificationModel(db)
    
    async def show_notifications_menu(self, query: types.CallbackQuery):
        """Show notifications configuration menu"""
        try:
            # Get current notification settings
            stats = await self.notification_model.get_stats()
            
            # Get recent events count
            recent_events = await self.db.fetch("""
                SELECT kind, COUNT(*) as count 
                FROM events 
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY kind
                ORDER BY count DESC
            """)
            
            # Build status text
            text = "<b>📢 Notification Settings</b>\n\n"
            
            if stats['channel_configured']:
                text += f"📡 <b>Channel:</b> <code>{stats['notification_channel_id']}</code> ✅\n"
            else:
                text += "📡 <b>Channel:</b> Not configured ❌\n"
            
            text += f"🚫 <b>Blacklisted Users:</b> {stats['blacklisted_users']}\n"
            text += f"🔔 <b>Event Types:</b> {stats['enabled_events']}/{stats['total_event_types']} enabled\n\n"
            
            text += "<b>Event Activity (24h):</b>\n"
            if recent_events:
                for event in recent_events:
                    enabled = "✅" if stats['event_types'].get(event['kind'], True) else "❌"
                    text += f"• {event['kind']}: {event['count']} {enabled}\n"
            else:
                text += "No recent events\n"
            
            keyboard_rows = [
                [
                    InlineKeyboardButton(text="📡 Set Channel", callback_data="notifications:set_channel"),
                    InlineKeyboardButton(text="🚫 Blacklist", callback_data="notifications:blacklist")
                ],
                [
                    InlineKeyboardButton(text="🔔 Event Types", callback_data="notifications:event_types"),
                    InlineKeyboardButton(text="🧪 Test", callback_data="notifications:test")
                ]
            ]
            
            if stats['channel_configured']:
                keyboard_rows.append([
                    InlineKeyboardButton(text="🗑️ Clear Channel", callback_data="notifications:clear_channel")
                ])
            
            keyboard_rows.extend([
                [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:notifications"),
                    InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")
                ]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing notifications menu: {e}")
            await query.answer("❌ Error loading notifications settings")
    
    async def handle_notifications_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle notifications-related callbacks"""
        parts = query.data.split(':', 2)
        action = parts[1]
        
        if action == 'set_channel':
            await self.start_set_channel(query, state)
        elif action == 'blacklist':
            await self.show_blacklist_menu(query)
        elif action == 'add_blacklist':
            await self.start_add_blacklist(query, state)
        elif action == 'remove_blacklist':
            if len(parts) > 2:
                user_id = int(parts[2])
                await self.remove_from_blacklist(query, user_id)
            else:
                await self.show_remove_blacklist_menu(query)
        elif action == 'event_types':
            await self.show_event_types_menu(query)
        elif action == 'toggle_event':
            if len(parts) > 2:
                event_type = parts[2]
                await self.toggle_event_type(query, event_type)
        elif action == 'test':
            await self.send_test_notification(query)
        elif action == 'clear_channel':
            await self.clear_notification_channel(query)
        else:
            await self.show_notifications_menu(query)
    
    async def start_set_channel(self, query: types.CallbackQuery, state: FSMContext):
        """Start setting notification channel"""
        try:
            text = "<b>📡 Set Notification Channel</b>\n\n"
            text += "Please enter the channel ID where notifications should be sent.\n\n"
            text += "Examples:\n"
            text += "• Channel: -1001234567890\n"
            text += "• Group: -1001234567890\n"
            text += "• Private chat: 123456789\n\n"
            text += "Type /cancel to abort."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:notifications")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.setting_notification_channel)
            
        except Exception as e:
            logger.error(f"Error starting set channel: {e}")
            await query.answer("❌ Error starting channel setup")
    
    async def process_channel_input(self, message: types.Message, state: FSMContext):
        """Process notification channel input"""
        try:
            if message.text == '/cancel':
                await message.reply("❌ Channel setup cancelled.")
                await state.clear()
                return
            
            # Parse channel ID
            try:
                channel_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid channel ID. Please enter a valid number.")
                return
            
            # Test channel access before setting
            from app.notification_sender import notification_sender
            test_result = await notification_sender.test_channel_access(channel_id)
            
            if not test_result['success']:
                error_text = f"❌ <b>Channel Access Failed</b>\n\n"
                error_text += f"Channel ID: <code>{channel_id}</code>\n"
                error_text += f"Error: {test_result['error']}\n\n"
                error_text += "Please:\n"
                error_text += "• Verify the channel ID is correct\n"
                error_text += "• Add the bot as an admin to the channel\n"
                error_text += "• Ensure the channel exists and is accessible"
                
                await message.reply(error_text)
                return
            
            # Set the channel after successful test
            await self.notification_model.set_notification_channel(channel_id)
            
            text = f"✅ <b>Notification Channel Set</b>\n\n"
            text += f"Channel ID: <code>{channel_id}</code>\n\n"
            text += "Channel access verified! All notifications will now be sent to this channel."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 View Settings", callback_data="menu:notifications")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await message.reply(text, reply_markup=keyboard)
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error processing channel input: {e}")
            await message.reply("❌ Error setting channel")
            await state.clear()
    
    async def show_blacklist_menu(self, query: types.CallbackQuery):
        """Show blacklist management menu"""
        try:
            blacklisted_users = await self.notification_model.get_blacklisted_users()
            
            text = "<b>🚫 Blacklist Management</b>\n\n"
            text += f"Currently blacklisted users: {len(blacklisted_users)}\n\n"
            
            if blacklisted_users:
                text += "<b>Blacklisted User IDs:</b>\n"
                for user_id in blacklisted_users:
                    text += f"• <code>{user_id}</code>\n"
            else:
                text += "No users are currently blacklisted.\n"
            
            text += "\nBlacklisted users' events (replies, mentions, DMs) will be ignored."
            
            keyboard_rows = [
                [
                    InlineKeyboardButton(text="➕ Add User", callback_data="notifications:add_blacklist"),
                ]
            ]
            
            if blacklisted_users:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➖ Remove User", callback_data="notifications:remove_blacklist")
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:notifications")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing blacklist menu: {e}")
            await query.answer("❌ Error loading blacklist")
    
    async def start_add_blacklist(self, query: types.CallbackQuery, state: FSMContext):
        """Start adding user to blacklist"""
        try:
            text = "<b>➕ Add User to Blacklist</b>\n\n"
            text += "Please enter the Telegram user ID to blacklist.\n\n"
            text += "Examples:\n"
            text += "• User ID: 123456789\n"
            text += "• Bot ID: 987654321\n\n"
            text += "Events from this user will be ignored.\n"
            text += "Type /cancel to abort."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="notifications:blacklist")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.adding_blacklist_user)
            
        except Exception as e:
            logger.error(f"Error starting add blacklist: {e}")
            await query.answer("❌ Error starting blacklist setup")
    
    async def process_blacklist_input(self, message: types.Message, state: FSMContext):
        """Process blacklist user input"""
        try:
            if message.text == '/cancel':
                await message.reply("❌ Blacklist addition cancelled.")
                await state.clear()
                return
            
            # Parse user ID
            try:
                user_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid user ID. Please enter a valid number.")
                return
            
            # Add to blacklist
            added = await self.notification_model.add_to_blacklist(user_id)
            
            if added:
                text = f"✅ <b>User Added to Blacklist</b>\n\n"
                text += f"User ID: <code>{user_id}</code>\n\n"
                text += "Events from this user will now be ignored."
            else:
                text = f"ℹ️ <b>User Already Blacklisted</b>\n\n"
                text += f"User ID: <code>{user_id}</code>\n\n"
                text += "This user is already in the blacklist."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚫 Manage Blacklist", callback_data="notifications:blacklist")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await message.reply(text, reply_markup=keyboard)
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error processing blacklist input: {e}")
            await message.reply("❌ Error adding to blacklist")
            await state.clear()
    
    async def show_remove_blacklist_menu(self, query: types.CallbackQuery):
        """Show menu to remove users from blacklist"""
        try:
            blacklisted_users = await self.notification_model.get_blacklisted_users()
            
            if not blacklisted_users:
                await query.answer("❌ No users in blacklist")
                return
            
            text = "<b>➖ Remove from Blacklist</b>\n\n"
            text += "Select a user to remove from blacklist:"
            
            keyboard_rows = []
            for user_id in blacklisted_users:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"Remove {user_id}",
                        callback_data=f"notifications:remove_blacklist:{user_id}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="notifications:blacklist")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing remove blacklist menu: {e}")
            await query.answer("❌ Error loading blacklist")
    
    async def remove_from_blacklist(self, query: types.CallbackQuery, user_id: int):
        """Remove user from blacklist"""
        try:
            removed = await self.notification_model.remove_from_blacklist(user_id)
            
            if removed:
                text = f"✅ <b>User Removed from Blacklist</b>\n\n"
                text += f"User ID: <code>{user_id}</code>\n\n"
                text += "Events from this user will now be processed normally."
                await query.answer("✅ User removed from blacklist")
            else:
                text = f"ℹ️ <b>User Not in Blacklist</b>\n\n"
                text += f"User ID: <code>{user_id}</code>\n\n"
                text += "This user was not in the blacklist."
                await query.answer("ℹ️ User not found in blacklist")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🚫 Manage Blacklist", callback_data="notifications:blacklist")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error removing from blacklist: {e}")
            await query.answer("❌ Error removing from blacklist")
    
    async def show_event_types_menu(self, query: types.CallbackQuery):
        """Show event types configuration"""
        try:
            stats = await self.notification_model.get_stats()
            event_types = stats['event_types']
            
            text = "<b>🔔 Event Types Configuration</b>\n\n"
            text += "Toggle which event types should trigger notifications:\n\n"
            
            for event_type, enabled in event_types.items():
                status = "✅" if enabled else "❌"
                text += f"{status} {event_type.title()}\n"
            
            keyboard_rows = []
            for event_type, enabled in event_types.items():
                status = "Disable" if enabled else "Enable"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status} {event_type.title()}",
                        callback_data=f"notifications:toggle_event:{event_type}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:notifications")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing event types menu: {e}")
            await query.answer("❌ Error loading event types")
    
    async def toggle_event_type(self, query: types.CallbackQuery, event_type: str):
        """Toggle an event type on/off"""
        try:
            stats = await self.notification_model.get_stats()
            current_types = stats['event_types'].copy()
            current_types[event_type] = not current_types.get(event_type, True)
            
            await self.notification_model.update_event_types(current_types)
            
            status = "enabled" if current_types[event_type] else "disabled"
            await query.answer(f"✅ {event_type.title()} {status}")
            
            await self.show_event_types_menu(query)
            
        except Exception as e:
            logger.error(f"Error toggling event type: {e}")
            await query.answer("❌ Error updating event type")
    
    async def send_test_notification(self, query: types.CallbackQuery):
        """Send a test notification"""
        try:
            channel_id = await self.notification_model.get_notification_channel()
            
            if not channel_id:
                await query.answer("❌ No notification channel configured")
                return
            
            # Send test notification directly
            from app.notification_sender import notification_sender
            
            test_event = {
                'kind': 'test',
                'user_id': query.from_user.id,
                'created_at': None,
                'payload': {
                    'message_text': '🧪 This is a test notification',
                    'user_name': query.from_user.full_name or 'Test User',
                    'chat_title': 'Management Bot'
                }
            }
            
            result = await notification_sender.send_notification(test_event)
            
            if result:
                await query.answer("✅ Test notification sent successfully")
            else:
                await query.answer("❌ Failed to send test notification - check channel configuration")
            
        except Exception as e:
            logger.error(f"Error sending test notification: {e}")
            await query.answer("❌ Error sending test notification")
    
    async def clear_notification_channel(self, query: types.CallbackQuery):
        """Clear the notification channel configuration"""
        try:
            success = await self.notification_model.clear_notification_channel()
            
            if success:
                text = f"✅ <b>Notification Channel Cleared</b>\n\n"
                text += "The notification channel has been removed.\n"
                text += "No notifications will be sent until a new channel is configured.\n\n"
                text += "To set up notifications:\n"
                text += "1. Create a channel or group\n"
                text += "2. Add @AshMRXbot as admin with 'Send Messages' permission\n" 
                text += "3. Use '📡 Set Channel' to configure it"
                
                await query.answer("✅ Channel cleared")
            else:
                text = "❌ <b>Error Clearing Channel</b>\n\n"
                text += "Failed to clear the notification channel configuration."
                await query.answer("❌ Error clearing channel")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📢 View Settings", callback_data="menu:notifications")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error clearing notification channel: {e}")
            await query.answer("❌ Error clearing channel")