from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models.notification import NotificationSettingsModel, NotificationBlacklistModel

logger = logging.getLogger(__name__)

class NotificationsHandler:
    """Handler for notification management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.notification_settings_model = NotificationSettingsModel(db)
        self.notification_blacklist_model = NotificationBlacklistModel(db)
    
    async def show_notifications_menu(self, query: types.CallbackQuery):
        """Display notifications management menu"""
        try:
            settings = await self.notification_settings_model.get_settings()
            blacklist = await self.notification_blacklist_model.get_all()
            
            channel_id = settings['notification_channel_id'] if settings else "Not set"
            
            text = f"<b>🔔 Notifications Management</b>\n\n"
            text += f"Notifications will be sent to channel: <code>{channel_id}</code>\n"
            text += f"Blacklisted users: {len(blacklist)}\n\n"
            text += "Configure where and from whom you receive notifications."
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.notifications_menu(settings, blacklist)
            )
        except Exception as e:
            logger.error(f"Error showing notifications menu: {e}")
            await query.answer("❌ Error loading notifications settings")

    async def handle_notifications_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle notification-related callbacks"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'set_channel':
            await self.start_set_notification_channel(query, state)
        elif action == 'blacklist':
            await self.show_blacklist_menu(query)
        elif action == 'add_blacklist':
            await self.start_add_blacklist_user(query, state)
        elif action == 'remove_blacklist':
            user_id = int(parts[2])
            await self.remove_from_blacklist(query, user_id)

    async def start_set_notification_channel(self, query: types.CallbackQuery, state: FSMContext):
        """Start the process to set the notification channel"""
        await query.message.edit_text(
            "<b>Set Notification Channel</b>\n\n" \
            "Forward a message from the desired channel to me, or send the channel ID.",
            reply_markup=self.keyboards.cancel_button("menu:notifications")
        )
        await state.set_state(ManagementStates.setting_notification_channel)
        await state.update_data(message_id=query.message.message_id)

    async def process_notification_channel_input(self, message: types.Message, state: FSMContext):
        """Process notification channel input"""
        if message.forward_from_chat:
            channel_id = message.forward_from_chat.id
        else:
            try:
                channel_id = int(message.text)
            except ValueError:
                await message.reply("Invalid input. Please forward a message or send a valid channel ID.")
                return

        await self.notification_settings_model.set_notification_channel(channel_id)
        await message.answer(f"✅ Notification channel set to <code>{channel_id}</code>")
        await state.clear()

    async def show_blacklist_menu(self, query: types.CallbackQuery):
        """Show the blacklist management menu"""
        blacklist = await self.notification_blacklist_model.get_all()
        text = "<b>🚫 Blacklist Management</b>\n\n"
        if not blacklist:
            text += "No users are blacklisted."
        else:
            text += "Messages from these users will be ignored:\n"
            for user in blacklist:
                text += f"- <code>{user['user_id']}</code>\n"
        
        await query.message.edit_text(
            text,
            reply_markup=self.keyboards.notification_blacklist_menu(blacklist)
        )

    async def start_add_blacklist_user(self, query: types.CallbackQuery, state: FSMContext):
        """Start adding a user to the blacklist"""
        await query.message.edit_text(
            "<b>Add to Blacklist</b>\n\n" \
            "Send me the user ID of the user to blacklist.",
            reply_markup=self.keyboards.cancel_button("notifications:blacklist")
        )
        await state.set_state(ManagementStates.adding_blacklist_user)
        await state.update_data(message_id=query.message.message_id)

    async def process_blacklist_input(self, message: types.Message, state: FSMContext):
        """Process blacklist user ID input"""
        try:
            user_id = int(message.text)
        except ValueError:
            await message.reply("Invalid user ID.")
            return

        await self.notification_blacklist_model.add_user(user_id)
        await message.answer(f"✅ User <code>{user_id}</code> has been blacklisted.")
        await state.clear()

    async def remove_from_blacklist(self, query: types.CallbackQuery, user_id: int):
        """Remove a user from the blacklist"""
        await self.notification_blacklist_model.remove_user(user_id)
        await query.answer(f"User {user_id} removed from blacklist.")
        await self.show_blacklist_menu(query)
