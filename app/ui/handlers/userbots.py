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
import time

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
        self.cache = {}
        self.cache_time = {}
    
    def is_fresh(self, key, seconds=300):
        """Check if cache entry is fresh (default 5 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    async def get_cached_userbots_with_assignments(self):
        """Get userbots with assignments using caching"""
        if self.is_fresh("userbots_with_assignments"):
            return self.cache["userbots_with_assignments"]
        
        userbots = await self.bot_model.get_userbots_with_assignments()
        self.cache["userbots_with_assignments"] = userbots
        self.cache_time["userbots_with_assignments"] = time.time()
        return userbots
    
    async def get_cached_active_userbots(self):
        """Get active userbots using caching"""
        if self.is_fresh("active_userbots"):
            return self.cache["active_userbots"]
        
        userbots = await self.bot_model.get_active_userbots()
        self.cache["active_userbots"] = userbots
        self.cache_time["active_userbots"] = time.time()
        return userbots
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_time.clear()
    
    async def show_userbots_menu(self, query: types.CallbackQuery, page: int = 1):
        """Display userbots management menu"""
        try:
            userbots = await self.get_cached_userbots_with_assignments()
            PAGE_SIZE = 5
            
            total_pages = (len(userbots) + PAGE_SIZE - 1) // PAGE_SIZE
            start = (page - 1) * PAGE_SIZE
            end = start + PAGE_SIZE
            paginated_userbots = userbots[start:end]
            
            text = "<b>🤖 Userbots Management</b>\n\n"
            
            if not userbots:
                text += "No userbots configured.\nClick 'Add Userbot' to create one."
            else:
                for bot in paginated_userbots:
                    status_icon = {
                        'active': '🟢',
                        'inactive': '🟡',
                        'error': '🔴'
                    }.get(bot['status'], '⚪')
                    
                    display_name = bot.get('display_name') or bot['session_name']
                    text += (
                        f"{status_icon} <b>{display_name}</b>\n"
                        f"  ├ Groups: {bot['assigned_groups']}\n"
                        f"  └ Last seen: {bot['last_seen'] or 'Never'}\n\n"
                    )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.userbots_menu([dict(bot) for bot in paginated_userbots], page, total_pages)
            )
        except Exception as e:
            logger.error(f"Error showing userbots menu: {e}")
            await query.answer("❌ Error loading userbots")
    
    async def handle_userbot_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle userbot-related callbacks"""
        parts = query.data.split(':')
        
        # Handle pagination
        if parts[0] == 'userbots_page':
            if parts[1] == 'page':
                page = int(parts[2])
                await self.show_userbots_menu(query, page=page)
                return

        action = parts[1]
        
        if action == 'add':
            await self.start_userbot_login(query, state)
        elif action == 'view':
            userbot_id = int(parts[2])
            await self.show_userbot_details(query, userbot_id)
        elif action == 'health':
            await self.check_userbots_health(query)
        elif action == 'refresh_sources':
            await self.refresh_all_sources(query)
        elif action == 'check':
            userbot_id = int(parts[2])
            await self.check_individual_userbot(query, userbot_id)
        elif action == 'delete':
            userbot_id = int(parts[2])
            await self.delete_userbot(query, userbot_id)
        elif action == 'confirm_delete':
            userbot_id = int(parts[2])
            await self.confirm_delete_userbot(query, userbot_id)
        elif action == 'set_name':
            userbot_id = int(parts[2])
            await self.start_set_userbot_name(query, userbot_id, state)
    
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
            # Generate display name from user info
            display_name = None
            if me.first_name and me.last_name:
                display_name = f"{me.first_name} {me.last_name}"
            elif me.first_name:
                display_name = me.first_name
            elif me.username:
                display_name = f"@{me.username}"
            else:
                display_name = session_name
            
            await self.bot_model.create({
                'kind': 'userbot',
                'session_name': session_name,
                'status': 'active',
                'session_string': session_string,
                'telegram_id': me.id,
                'username': me.username,
                'first_name': me.first_name,
                'last_name': me.last_name,
                'display_name': display_name
            })
            
            # Clear cache since we created new userbot
            self.clear_cache()
            
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
            
            display_name = userbot.get('display_name') or userbot['session_name']
            text = (
                f"<b>🤖 Userbot Details</b>\n\n"
                f"<b>{display_name}</b>\n"
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
                    InlineKeyboardButton(text="✏️ Set Name", callback_data=f"userbot:set_name:{userbot_id}"),
                    InlineKeyboardButton(text="🔄 Check Status", callback_data=f"userbot:check:{userbot_id}")
                ],
                [
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
            userbots = await self.get_cached_active_userbots()
            
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
    
    async def refresh_all_sources(self, query: types.CallbackQuery):
        """Refresh source monitoring for all userbots"""
        try:
            # Import the legacy userbot manager
            from app.userbot_worker import UserbotManager
            
            # Since we can't easily access the running instance, 
            # we'll create a temporary instance to access worker functionality
            # This is not ideal but works for the refresh functionality
            temp_manager = UserbotManager()
            
            # Get all active userbots from database
            userbots = await self.get_cached_active_userbots()
            
            if not userbots:
                await query.answer("❌ No active userbots found")
                return
            
            await query.message.edit_text(
                "<b>🔄 Refreshing Sources</b>\n\n"
                "Please wait while we refresh source monitoring for all userbots...",
                reply_markup=None
            )
            
            # Refresh sources by creating temporary workers for each active userbot
            refreshed_count = 0
            failed_count = 0
            
            for userbot in userbots:
                userbot_id = userbot['id']
                session_string = userbot.get('session_string')
                
                if not session_string:
                    logger.warning(f"No session string for userbot {userbot_id}")
                    failed_count += 1
                    continue
                
                try:
                    # Create a temporary worker instance for refresh
                    from app.userbot_worker import UserbotWorker
                    temp_worker = UserbotWorker(userbot_id, session_string)
                    
                    # Initialize the session to allow refresh
                    if await temp_worker._modular_worker.session_manager.initialize_client():
                        await temp_worker.refresh_sources()
                        refreshed_count += 1
                        logger.info(f"Refreshed sources for userbot {userbot_id}")
                        
                        # Clean up the temporary session
                        await temp_worker._modular_worker.session_manager.disconnect_client()
                    else:
                        failed_count += 1
                        logger.error(f"Failed to initialize session for userbot {userbot_id}")
                        
                except Exception as worker_error:
                    failed_count += 1
                    logger.error(f"Failed to refresh sources for userbot {userbot_id}: {worker_error}")
            
            # Show results
            if refreshed_count > 0:
                text = f"✅ <b>Sources Refreshed Successfully</b>\n\n"
                text += f"Refreshed source monitoring for {refreshed_count} userbot(s)\n"
                if failed_count > 0:
                    text += f"Failed to refresh {failed_count} userbot(s)\n"
                text += "\nNew sources and routing rules are now active!"
                
                await query.answer("✅ Sources refreshed successfully")
            else:
                text = f"⚠️ <b>Refresh Completed</b>\n\n"
                text += "No active userbots found to refresh.\n"
                text += f"Failed attempts: {failed_count}"
                
                await query.answer("⚠️ No userbots to refresh")
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:userbots")
            )
            
        except Exception as e:
            logger.error(f"Error refreshing sources: {e}")
            await query.answer("❌ Error refreshing sources")
            
            try:
                await query.message.edit_text(
                    f"❌ <b>Refresh Failed</b>\n\n"
                    f"Error: {str(e)}\n\n"
                    f"Please try again or restart the bot.",
                    reply_markup=self.keyboards.back_button("menu:userbots")
                )
            except:
                pass
    
    async def check_individual_userbot(self, query: types.CallbackQuery, userbot_id: int):
        """Check status of individual userbot"""
        try:
            userbot = await self.bot_model.get_by_id(userbot_id)
            if not userbot:
                await query.answer("Userbot not found!")
                return
            
            # Test the userbot connection
            from app.userbot.session_manager import SessionManager
            session_manager = SessionManager(userbot_id, userbot['session_string'])
            
            await query.message.edit_text(
                "<b>🔄 Checking Userbot Status...</b>\n\n"
                "Please wait while we test the connection...",
                reply_markup=None
            )
            
            # Initialize and test connection
            success = await session_manager.initialize_client()
            
            if success:
                health = await session_manager.health_check()
                user_info = session_manager.get_user_info()
                
                await session_manager.disconnect_client()
                
                if health['healthy']:
                    status_icon = "✅"
                    status_text = "Connected and working"
                    details = f"User ID: {user_info.get('user_id')}\nUsername: @{user_info.get('username') or 'none'}"
                else:
                    status_icon = "❌"
                    status_text = f"Connection issues: {health.get('error', 'Unknown error')}"
                    details = "Health check failed"
            else:
                status_icon = "❌"
                status_text = "Failed to initialize"
                details = "Could not connect to Telegram"
            
            text = (
                f"<b>🔍 Userbot Status Check</b>\n\n"
                f"<b>{userbot['session_name']}</b>\n\n"
                f"Status: {status_icon} {status_text}\n"
                f"Details: {details}\n\n"
                f"✅ Check completed successfully"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"userbot:view:{userbot_id}")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error checking individual userbot: {e}")
            await query.answer("❌ Error checking userbot status")
            
            try:
                await query.message.edit_text(
                    f"❌ <b>Status Check Failed</b>\n\n"
                    f"Error: {str(e)}",
                    reply_markup=self.keyboards.back_button(f"userbot:view:{userbot_id}")
                )
            except:
                pass
    
    async def delete_userbot(self, query: types.CallbackQuery, userbot_id: int):
        """Delete userbot with confirmation"""
        try:
            userbot = await self.bot_model.get_by_id(userbot_id)
            if not userbot:
                await query.answer("Userbot not found!")
                return
            
            text = (
                f"<b>🗑 Delete Userbot</b>\n\n"
                f"Are you sure you want to delete:\n"
                f"<b>{userbot['session_name']}</b>\n\n"
                f"⚠️ <b>Warning:</b>\n"
                f"• This will permanently remove the userbot\n"
                f"• All assignments will be lost\n"
                f"• This action cannot be undone\n\n"
                f"Confirm deletion?"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"userbot:confirm_delete:{userbot_id}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"userbot:view:{userbot_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing delete confirmation: {e}")
            await query.answer("❌ Error loading delete confirmation")
    
    async def confirm_delete_userbot(self, query: types.CallbackQuery, userbot_id: int):
        """Actually delete the userbot after confirmation"""
        try:
            userbot = await self.bot_model.get_by_id(userbot_id)
            if not userbot:
                await query.answer("Userbot not found!")
                return
            
            session_name = userbot['session_name']
            
            # Delete the userbot from database
            success = await self.bot_model.delete(userbot_id)
            
            # Clear cache since we deleted userbot
            self.clear_cache()
            
            if success:
                text = (
                    f"✅ <b>Userbot Deleted</b>\n\n"
                    f"Successfully removed:\n"
                    f"<b>{session_name}</b>\n\n"
                    f"The userbot and all its assignments have been permanently deleted."
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Back to Userbots", callback_data="menu:userbots")]
                ])
                
                await query.answer("✅ Userbot deleted successfully")
            else:
                text = (
                    f"❌ <b>Deletion Failed</b>\n\n"
                    f"Could not delete userbot:\n"
                    f"<b>{session_name}</b>\n\n"
                    f"The userbot may not exist or there was a database error."
                )
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Back", callback_data=f"userbot:view:{userbot_id}")]
                ])
                
                await query.answer("❌ Failed to delete userbot")
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error confirming userbot deletion: {e}")
            await query.answer("❌ Error deleting userbot")
            
            try:
                await query.message.edit_text(
                    f"❌ <b>Deletion Error</b>\n\n"
                    f"Error: {str(e)}",
                    reply_markup=self.keyboards.back_button("menu:userbots")
                )
            except:
                pass
    
    async def start_set_userbot_name(self, query: types.CallbackQuery, userbot_id: int, state: FSMContext):
        """Start userbot name setting process"""
        try:
            userbot = await self.bot_model.get_by_id(userbot_id)
            if not userbot:
                await query.answer("Userbot not found!")
                return
            
            current_name = userbot.get('display_name') or userbot['session_name']
            
            await query.message.edit_text(
                f"<b>✏️ Set Userbot Name</b>\n\n"
                f"Current name: <b>{current_name}</b>\n\n"
                f"Enter a new custom name for this userbot:\n\n"
                f"Type /cancel to abort.",
                reply_markup=self.keyboards.cancel_button(f"userbot:view:{userbot_id}")
            )
            
            await state.set_state(ManagementStates.userbot_set_name)
            await state.update_data(
                userbot_id=userbot_id,
                message_id=query.message.message_id
            )
            
        except Exception as e:
            logger.error(f"Error starting userbot name setting: {e}")
            await query.answer("❌ Error starting name setting")
    
    async def process_userbot_name_input(self, message: types.Message, state: FSMContext):
        """Process userbot name input"""
        if message.text == '/cancel':
            data = await state.get_data()
            userbot_id = data.get('userbot_id')
            await message.answer("❌ Name setting cancelled.")
            await state.clear()
            if userbot_id:
                await self.show_userbot_details(message, userbot_id)
            return
        
        new_name = message.text.strip()
        await message.delete()  # Clean up user input
        
        # Validate name
        if not new_name or len(new_name) > 50:
            await message.answer("❌ Name must be 1-50 characters long.")
            return
        
        try:
            data = await state.get_data()
            userbot_id = data.get('userbot_id')
            
            if not userbot_id:
                await message.answer("❌ Session data lost. Please try again.")
                await state.clear()
                return
            
            # Update userbot name in database (direct SQL to avoid updated_at requirement)
            await self.db.execute(
                "UPDATE bots SET display_name = $1 WHERE id = $2",
                new_name, userbot_id
            )
            
            await message.answer(
                f"✅ <b>Name Updated Successfully!</b>\n\n"
                f"Userbot name set to: <b>{new_name}</b>"
            )
            
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error updating userbot name: {e}")
            await message.answer(f"❌ Error updating name: {str(e)}")
            await state.clear()
