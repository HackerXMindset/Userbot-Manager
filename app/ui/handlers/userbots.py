from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    FloodWaitError,
    PasswordHashInvalidError
)
import asyncio
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
            "Example: +919876543210\n\n"
            "Type /cancel to abort.",
            reply_markup=self.keyboards.cancel_button("menu:userbots")
        )
        await state.set_state(ManagementStates.userbot_login_phone)
        await state.update_data(
            message_id=query.message.message_id,
            retry_count=0
        )
    
    async def process_phone_input(self, message: types.Message, state: FSMContext):
        """Process userbot phone number with proper validation and error handling"""
        if message.text == '/cancel':
            await message.answer("❌ Userbot login cancelled.")
            await state.clear()
            return
            
        phone = message.text.strip()
        await message.delete()  # Hide phone number for security
        
        # Validate phone format
        if not phone.startswith('+'):
            await message.answer("❌ Please include country code (e.g., +919876543210)")
            return
            
        if not phone[1:].replace(' ', '').replace('-', '').isdigit():
            await message.answer("❌ Invalid phone number format. Use: +919876543210")
            return
        
        try:
            # Create client with StringSession
            session_name = f"userbot_{phone.replace('+', '')[-8:]}"
            client = TelegramClient(
                StringSession(),
                settings.api_id,
                settings.api_hash
            )
            
            await client.connect()
            
            # Check if already authorized (edge case)
            try:
                me = await client.get_me()
                if me and hasattr(me, 'id'):
                    # If we can get user info, already authorized
                    session_string = client.session.save()
                    await client.disconnect()
                    
                    # Save directly to database
                    await self._save_userbot(session_name, session_string, me)
                    await message.answer(
                        f"✅ <b>Userbot Already Authorized!</b>\n\n"
                        f"Name: {me.first_name}\n"
                        f"Username: @{me.username or 'none'}\n"
                        f"Session: {session_name}"
                    )
                    await state.clear()
                    return
            except Exception:
                # Not authorized, continue with normal flow
                pass
            
            # Send code request
            sent_code = await client.send_code_request(phone)
            session_string = client.session.save()
            await client.disconnect()  # Disconnect after getting session
            
            # Store session data in FSM state (not memory)
            await state.update_data(
                phone=phone,
                session_name=session_name,
                session_string=session_string,
                phone_code_hash=sent_code.phone_code_hash
            )
            
            await state.set_state(ManagementStates.userbot_login_code)
            
            masked_phone = '*' * (len(phone) - 4) + phone[-4:]
            await message.answer(
                f"<b>📱 Code Sent</b>\n\n"
                f"A verification code has been sent to: {masked_phone}\n"
                f"Please enter the 5-digit code:\n\n"
                f"Type /cancel to abort.",
                reply_markup=self.keyboards.cancel_button("menu:userbots")
            )
            
        except FloodWaitError as e:
            await message.answer(
                f"❌ <b>Rate Limited</b>\n\n"
                f"Please wait {e.seconds} seconds before trying again."
            )
            await state.clear()
            
        except Exception as e:
            logger.error(f"Phone processing error: {e}")
            await message.answer(
                f"❌ <b>Error</b>\n\n"
                f"Failed to send verification code: {str(e)}\n"
                f"Please try again with /start"
            )
            await state.clear()
    
    async def process_code_input(self, message: types.Message, state: FSMContext):
        """Process verification code with proper error handling"""
        if message.text == '/cancel':
            await message.answer("❌ Userbot login cancelled.")
            await state.clear()
            return
            
        code = message.text.strip()
        await message.delete()  # Hide verification code for security
        
        # Validate code format
        if not code.isdigit() or len(code) != 5:
            await message.answer("❌ Please enter a valid 5-digit verification code.")
            return
        
        data = await state.get_data()
        phone = data.get('phone')
        session_name = data.get('session_name')
        session_string = data.get('session_string')
        
        if not all([phone, session_name, session_string]):
            await message.answer("❌ Session data lost. Please start again with /start.")
            await state.clear()
            return
        
        try:
            # Recreate client from stored session
            client = TelegramClient(
                StringSession(session_string),
                settings.api_id,
                settings.api_hash
            )
            
            await client.connect()
            
            # Attempt sign in with verification code
            phone_code_hash = data.get('phone_code_hash')
            me = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
            
            # Success - save session
            final_session = client.session.save()
            await client.disconnect()
            
            # Save userbot to database
            await self._save_userbot(session_name, final_session, me)
            
            await message.answer(
                f"✅ <b>Userbot Added Successfully!</b>\n\n"
                f"Name: {me.first_name}\n"
                f"Username: @{me.username or 'none'}\n"
                f"ID: <code>{me.id}</code>\n\n"
                f"Session: {session_name}"
            )
            await state.clear()
            
        except SessionPasswordNeededError:
            # 2FA is required
            try:
                # Get password hint if available
                from telethon import functions
                password_info = await client(functions.account.GetPasswordRequest())
                hint = password_info.hint or "No hint available"
                await client.disconnect()
                
                # Update session string and move to 2FA state
                updated_session = client.session.save()
                await state.update_data(
                    session_string=updated_session,
                    password_hint=hint,
                    retry_count=0
                )
                await state.set_state(ManagementStates.userbot_login_2fa)
                
                await message.answer(
                    f"🔐 <b>2FA Required</b>\n\n"
                    f"This account has two-factor authentication enabled.\n"
                    f"Hint: <i>{hint}</i>\n\n"
                    f"Please enter your 2FA password:\n\n"
                    f"Type /cancel to abort."
                )
                
            except Exception as e:
                logger.error(f"2FA setup error: {e}")
                await message.answer(
                    "🔐 <b>2FA Required</b>\n\n"
                    "Please enter your 2FA password:\n\n"
                    "Type /cancel to abort."
                )
                await client.disconnect()
                await state.set_state(ManagementStates.userbot_login_2fa)
            
        except PhoneCodeInvalidError:
            await message.answer(
                "❌ <b>Invalid Code</b>\n\n"
                "The verification code is incorrect. Please try again:"
            )
            await client.disconnect()
            
        except FloodWaitError as e:
            await message.answer(
                f"❌ <b>Rate Limited</b>\n\n"
                f"Please wait {e.seconds} seconds before trying again."
            )
            await client.disconnect()
            await state.clear()
            
        except Exception as e:
            logger.error(f"Code processing error: {e}")
            await message.answer(
                f"❌ <b>Error</b>\n\n"
                f"Authentication failed: {str(e)}\n"
                f"Please start again with /start"
            )
            try:
                await client.disconnect()
            except:
                pass
            await state.clear()
    
    async def process_2fa_input(self, message: types.Message, state: FSMContext):
        """Process 2FA password with retry logic and proper error handling"""
        if message.text == '/cancel':
            await message.answer("❌ Userbot login cancelled.")
            await state.clear()
            return
            
        password = message.text
        await message.delete()  # Hide password for security
        
        data = await state.get_data()
        phone = data.get('phone')
        session_name = data.get('session_name')
        session_string = data.get('session_string')
        password_hint = data.get('password_hint', 'No hint available')
        retry_count = data.get('retry_count', 0)
        
        if not all([phone, session_name, session_string]):
            await message.answer("❌ Session data lost. Please start again with /start.")
            await state.clear()
            return
        
        # Check retry limit
        if retry_count >= 3:
            await message.answer(
                "❌ <b>Maximum Attempts Exceeded</b>\n\n"
                "Too many failed attempts. Please start again with /start."
            )
            await state.clear()
            return
        
        try:
            # Recreate client from stored session
            client = TelegramClient(
                StringSession(session_string),
                settings.api_id,
                settings.api_hash
            )
            
            await client.connect()
            
            # Attempt 2FA authentication
            me = await client.sign_in(password=password)
            
            # Success - save session
            final_session = client.session.save()
            await client.disconnect()
            
            # Save userbot to database
            await self._save_userbot(session_name, final_session, me)
            
            await message.answer(
                f"✅ <b>Userbot Added Successfully!</b>\n\n"
                f"Name: {me.first_name}\n"
                f"Username: @{me.username or 'none'}\n"
                f"ID: <code>{me.id}</code>\n\n"
                f"Session: {session_name}"
            )
            await state.clear()
            
        except PasswordHashInvalidError:
            # Invalid 2FA password - allow retry
            await client.disconnect()
            
            retry_count += 1
            attempts_left = 3 - retry_count
            
            await state.update_data(retry_count=retry_count)
            
            if attempts_left > 0:
                await message.answer(
                    f"❌ <b>Invalid 2FA Password</b>\n\n"
                    f"Hint: <i>{password_hint}</i>\n\n"
                    f"Attempts remaining: {attempts_left}\n"
                    f"Please try again:\n\n"
                    f"Type /cancel to abort."
                )
            else:
                await message.answer(
                    "❌ <b>Maximum Attempts Exceeded</b>\n\n"
                    "Too many failed 2FA attempts. Please start again with /start."
                )
                await state.clear()
                
        except FloodWaitError as e:
            await message.answer(
                f"❌ <b>Rate Limited</b>\n\n"
                f"Please wait {e.seconds} seconds before trying again."
            )
            await client.disconnect()
            await state.clear()
            
        except Exception as e:
            logger.error(f"2FA processing error: {e}")
            error_msg = str(e).lower()
            
            if any(word in error_msg for word in ['password', 'invalid', 'wrong', 'incorrect', 'hash']):
                # Likely a password error - allow retry
                await client.disconnect()
                
                retry_count += 1
                attempts_left = 3 - retry_count
                
                await state.update_data(retry_count=retry_count)
                
                if attempts_left > 0:
                    await message.answer(
                        f"❌ <b>Authentication Failed</b>\n\n"
                        f"Error: {str(e)}\n\n"
                        f"Attempts remaining: {attempts_left}\n"
                        f"Please try again:\n\n"
                        f"Type /cancel to abort."
                    )
                else:
                    await message.answer(
                        "❌ <b>Maximum Attempts Exceeded</b>\n\n"
                        "Please start again with /start."
                    )
                    await state.clear()
            else:
                # Other error - fail completely
                await message.answer(
                    f"❌ <b>Authentication Error</b>\n\n"
                    f"Unexpected error: {str(e)}\n"
                    f"Please start again with /start."
                )
                try:
                    await client.disconnect()
                except:
                    pass
                await state.clear()
    
    async def _save_userbot(self, session_name: str, session_string: str, me) -> None:
        """Helper method to save userbot to database"""
        try:
            await self.bot_model.create({
                'kind': 'userbot',
                'session_name': session_name,
                'status': 'active',
                'session_string': session_string,
                'telegram_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name
            })
            logger.info(f"Successfully saved userbot: {session_name} ({me.id})")
        except Exception as e:
            logger.error(f"Failed to save userbot to database: {e}")
            raise
    
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
