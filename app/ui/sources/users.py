import logging

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


async def start_add_user(service, query: types.CallbackQuery, source_id: int, state: FSMContext):
    """Start adding user to source"""
    try:
        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        title = source['title'] or f"ID: {source['source_chat_id']}"

        # Set source ID in state
        await state.set_data({'source_id': source_id})
        await state.set_state(ManagementStates.adding_source_user_id)

        text = f"<b>👥 Add User to {title}</b>\n\n"
        text += "Please enter the Telegram user ID of the person whose messages should trigger token forwards from this group.\n\n"
        text += "Example: <code>123456789</code>\n\n"
        text += "💡 <i>You can get user IDs by forwarding their message to @userinfobot</i>"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data=f"sources:users:{source_id}")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error starting add user: {e}")
        await query.answer("❌ Error starting user setup")


async def _lookup_user_info(service, user_id: int) -> dict:
    """Lookup user information from Telegram using an available userbot session"""
    try:
        # Get an active userbot to use for user lookup
        from app.models import BotModel
        bot_model = BotModel(service.db)
        userbots = await bot_model.get_active_userbots()

        if not userbots:
            return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

        # Use the first active userbot for lookup
        userbot = userbots[0]
        session_string = userbot.get('session_string')

        if not session_string:
            return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

        # Create temporary client for user lookup
        from telethon import TelegramClient
        from telethon.sessions import StringSession
        from app.config import settings

        client = TelegramClient(
            StringSession(session_string),
            settings.api_id,
            settings.api_hash
        )

        await client.connect()

        try:
            # Get user entity
            user_entity = await client.get_entity(user_id)

            return {
                "user_id": user_id,
                "username": user_entity.username,
                "first_name": user_entity.first_name or "Unknown",
                "last_name": user_entity.last_name
            }

        except Exception as lookup_error:
            logger.debug(f"Could not lookup user {user_id}: {lookup_error}")
            return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

        finally:
            await client.disconnect()

    except Exception as e:
        logger.error(f"Error in user lookup: {e}")
        return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}


async def process_user_input(service, message: types.Message, state: FSMContext):
    """Process user ID input for source filtering"""
    try:
        data = await state.get_data()
        source_id = data.get('source_id')

        if not source_id:
            await message.reply("❌ Session expired. Please start again.")
            await state.clear()
            return

        # Parse user ID
        try:
            user_id = int(message.text.strip())
        except ValueError:
            await message.reply("❌ Invalid user ID. Please enter a valid number.")
            return

        # Lookup real user info from Telegram
        user_info = await _lookup_user_info(service, user_id)

        # Add user to source with real info
        await service.source_model.add_user_to_source(
            source_id=source_id,
            user_id=user_id,
            username=user_info["username"],
            first_name=user_info["first_name"]
        )

        # Show user info in success message
        display_name = user_info["first_name"]
        if user_info["username"]:
            display_name = f"{user_info['first_name']} (@{user_info['username']})"
        elif user_info["first_name"] == "Unknown":
            display_name = f"User {user_id}"

        text = f"✅ <b>User Added</b>\n\n"
        text += f"Name: {display_name}\n"
        text += f"User ID: <code>{user_id}</code>\n"
        text += "This user can now trigger token forwards from this source."

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source_id}")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        await message.reply(text, reply_markup=keyboard)
        await state.clear()

    except Exception as e:
        logger.error(f"Error processing user input: {e}")
        await message.reply("❌ Error adding user")
        await state.clear()


async def manage_source_users(service, query: types.CallbackQuery, source_id: int):
    """Show user management for a source"""
    try:
        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        users = await service.source_model.get_source_users(source_id)

        title = source['title'] or f"ID: {source['source_chat_id']}"
        text = f"<b>👥 Users for {title}</b>\n\n"

        if source['source_type'] == 'channel':
            text += "This is a channel - all posts are forwarded automatically."
        elif not users:
            text += "No users configured. Add users to allow token forwards from this group."
        else:
            text += "These users can trigger token forwards:\n\n"
            for user in users:
                name = user['first_name'] or user['username'] or f"ID: {user['user_id']}"
                text += f"• {name} (<code>{user['user_id']}</code>)\n"

        keyboard_rows = []

        if source['source_type'] == 'group':
            keyboard_rows.append([
                InlineKeyboardButton(text="➕ Add User", callback_data=f"sources:add_user:{source_id}")
            ])

            for user in users:
                name = (user['first_name'] or user['username'] or f"ID: {user['user_id']}")[:20]
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"🗑️ Remove {name}",
                        callback_data=f"sources:remove_user:{source_id}:{user['user_id']}"
                    )
                ])

        keyboard_rows.extend([
            [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error managing source users: {e}")
        await query.answer("❌ Error loading users")


async def remove_user_from_source(service, query: types.CallbackQuery, source_id: int, user_id: int):
    """Remove user from source"""
    try:
        success = await service.source_model.remove_user_from_source(source_id, user_id)

        if success:
            await query.answer("✅ User removed")
            await service.manage_source_users(query, source_id)
        else:
            await query.answer("❌ Failed to remove user")

    except Exception as e:
        logger.error(f"Error removing user: {e}")
        await query.answer("❌ Error removing user")
