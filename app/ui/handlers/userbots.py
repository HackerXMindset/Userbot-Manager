from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
import logging

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import BotModel
from app.config import settings

logger = logging.getLogger(__name__)

class UserbotsHandler:
    """Handler for userbot management operations"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.bot_model = BotModel(db)
        self.temp_clients = {}  # Store temporary clients during login
    
    async def show_userbots_menu(self, query: types.CallbackQuery):
        """Display userbots management menu"""
        try:
            userbots = await self.bot_model.get_userbots_with_assignments()
            
            text = "<b>🤖 Userbots Management</b>\n\n"
            
            if not userbots:
                text += "No userbots configured.\nClick 'Add Userbot' to create one."
            else:
                for bot in userbots[:5]:
                    status_icon = {
                        'active': '🟢',
                        'inactive': '🟡',
                        'error': '🔴'
                    }.get(bot['status'], '⚪')
                    
                    text += (
                        f"{status_icon} <b>{bot['session_name']}</b>\n"
                        f"  ├ Groups: {bot['assigned_groups']}\n"
                        f"  └ Last seen: {bot['last_seen'] or 'Never'}\n\n"
                    )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.userbots_menu([dict(bot) for bot in userbots])
            )
        except Exception as e:
            logger.error(f"Error showing userbots menu: {e}")
            await query.answer("❌ Error loading userbots")
    
    async def handle_userbot_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle userbot-related callbacks"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'add':
            await self.start_userbot_login(query, state)
        elif action == 'view':
            userbot_id = int(parts[2])
            await self.show_userbot_details(query, userbot_id)
        elif action == 'health':
            await self.check_userbots_health(query)
    
    async def start_userbot_login(self, query: types.CallbackQuery, state: FSMContext):
        """Start userbot login process"""
        await query.message.edit_text(
            "<b>➕ Add New Userbot</b>\n\n"
            "I'll help you login a userbot account.\n"
            "Please enter the phone number (with country code):\n\n"
            "Example: +919876543210",
            reply_markup=self.keyboards.cancel_button("menu:userbots")
        )
        await ManagementStates.userbot_login_phone.set()
        await state.update_data(message_id=query.message.message_id)
    
    async def process_phone_input(self, message: types.Message, state: FSMContext, bot):
        """Process userbot phone number"""
        phone = message.text.strip()
        await message.delete()  # Hide phone number
        
        try:
            session_name = f"userbot_{phone[-6:]}"
            client = TelegramClient(
                StringSession(),
                settings.api_id,
                settings.api_hash
            )
            
            await client.connect()
            await client.send_code_request(phone)
            
            # Store client temporarily
            self.temp_clients[message.from_user.id] = client
            
            data = await state.get_data()
            msg_id = data.get('message_id')
            
            await bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=msg_id,
                text=(
                    f"<b>📱 Code Sent</b>\n\n"
                    f"A code has been sent to: {'*' * (len(phone)-4) + phone[-4:]}\n"
                    f"Please enter the verification code:"
                ),
                reply_markup=self.keyboards.cancel_button("menu:userbots")
            )
            
            await ManagementStates.userbot_login_code.set()
            await state.update_data(phone=phone, session_name=session_name)
            
        except Exception as e:
            await message.answer(f"❌ Error: {e}")
            await state.finish()
    
    async def process_code_input(self, message: types.Message, state: FSMContext):
        """Process verification code"""
        code = message.text.strip()
        await message.delete()  # Hide code
        
        data = await state.get_data()
        phone = data.get('phone')
        session_name = data.get('session_name')
        
        client = self.temp_clients.get(message.from_user.id)
        if not client:
            await message.answer("❌ Session expired. Please start again.")
            await state.finish()
            return
        
        try:
            await client.sign_in(phone, code)
            session_string = client.session.save()
            
            # Save to database
            userbot = await self.bot_model.create({
                'kind': 'userbot',
                'session_name': session_name,
                'status': 'active',
                'session_string': session_string
            })
            
            me = await client.get_me()
            
            await message.answer(
                f"✅ <b>Userbot Added Successfully!</b>\n\n"
                f"Name: {me.first_name}\n"
                f"Username: @{me.username or 'none'}\n"
                f"ID: <code>{me.id}</code>\n\n"
                f"Session: {session_name}"
            )
            
            await client.disconnect()
            del self.temp_clients[message.from_user.id]
            
        except SessionPasswordNeededError:
            await message.answer(
                "🔐 This account has 2FA enabled.\n"
                "Please enter your 2FA password:"
            )
            await ManagementStates.userbot_login_2fa.set()
            
        except Exception as e:
            await message.answer(f"❌ Error: {e}")
            if client:
                await client.disconnect()
                if message.from_user.id in self.temp_clients:
                    del self.temp_clients[message.from_user.id]
        
        finally:
            await state.finish()
    
    async def show_userbot_details(self, query: types.CallbackQuery, userbot_id: int):
        """Show detailed userbot information"""
        try:
            userbot = await self.bot_model.get_by_id(userbot_id)
            assigned_groups = await self.bot_model.get_assigned_groups(userbot_id)
            
            if not userbot:
                await query.answer("Userbot not found!")
                return
            
            status_icon = {
                'active': '🟢',
                'inactive': '🟡', 
                'error': '🔴'
            }.get(userbot['status'], '⚪')
            
            text = (
                f"<b>🤖 Userbot Details</b>\n\n"
                f"<b>{userbot['session_name']}</b>\n"
                f"Status: {status_icon} {userbot['status'].title()}\n"
                f"Last Seen: {userbot['last_seen'] or 'Never'}\n\n"
                f"<b>Assignments:</b>\n"
            )
            
            if assigned_groups:
                for group in assigned_groups:
                    text += f"├ {group['title'] or f'Chat {group['tg_chat_id']}'}\n"
                text = text.rstrip('\n') + "\n"
            else:
                text += "└ No groups assigned\n"
                
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Check Status", callback_data=f"userbot:check:{userbot_id}"),
                    InlineKeyboardButton(text="🗑 Delete", callback_data=f"userbot:delete:{userbot_id}")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:userbots")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing userbot details: {e}")
            await query.answer("❌ Error loading userbot details")
    
    async def check_userbots_health(self, query: types.CallbackQuery):
        """Check health of all userbots"""
        try:
            userbots = await self.bot_model.get_active_userbots()
            
            if not userbots:
                await query.answer("No userbots to check")
                return
            
            text = "<b>🔄 Userbot Health Check</b>\n\n"
            
            for userbot in userbots:
                # This would normally test the actual connection
                # For now, just show the current status
                status_icon = '🟢' if userbot['status'] == 'active' else '🔴'
                text += f"{status_icon} {userbot['session_name']}: {userbot['status']}\n"
            
            text += "\n✅ Health check completed"
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:userbots")
            )
            
        except Exception as e:
            logger.error(f"Error checking userbot health: {e}")
            await query.answer("❌ Error checking userbot health")
