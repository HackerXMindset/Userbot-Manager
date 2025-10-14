import logging

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


class SourceUserMixin:
    """User assignment workflows for sources."""

    async def start_add_user(self, query: types.CallbackQuery, source_id: int, state: FSMContext):
        """Start adding user to source."""
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            title = source['title'] or f"ID: {source['source_chat_id']}"

            await state.set_data({'source_id': source_id})
            await state.set_state(ManagementStates.adding_source_user_id)

            text = (
                f"<b>👥 Add User to {title}</b>\n\n"
                "Please enter the Telegram user ID of the person whose messages should trigger token forwards from this group.\n\n"
                "Example: <code>123456789</code>\n\n"
                "💡 <i>You can get user IDs by forwarding their message to @userinfobot</i>"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"sources:users:{source_id}")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error starting add user: %s", exc)
            await query.answer("❌ Error starting user setup")

    async def _lookup_user_info(self, user_id: int) -> dict:
        """Lookup user information from Telegram using an available userbot session."""
        try:
            from app.models import BotModel
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from app.config import settings

            bot_model = BotModel(self.db)
            userbots = await bot_model.get_active_userbots()

            if not userbots:
                return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

            session_string = userbots[0].get('session_string')
            if not session_string:
                return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

            client = TelegramClient(StringSession(session_string), settings.api_id, settings.api_hash)
            await client.connect()
            try:
                user_entity = await client.get_entity(user_id)
                return {
                    "user_id": user_id,
                    "username": user_entity.username,
                    "first_name": user_entity.first_name or "Unknown",
                    "last_name": user_entity.last_name,
                }
            except Exception as lookup_error:  # pragma: no cover
                logger.debug("Could not lookup user %s: %s", user_id, lookup_error)
                return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}
            finally:
                await client.disconnect()

        except Exception as exc:  # pragma: no cover
            logger.error("Error in user lookup: %s", exc)
            return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

    async def process_user_input(self, message: types.Message, state: FSMContext):
        """Handle user ID input for source user management."""
        try:
            data = await state.get_data()
            source_id = data.get('source_id')

            if not source_id:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return

            try:
                user_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid user ID. Please enter a valid number.")
                return

            user_info = await self._lookup_user_info(user_id)
            await self.source_model.add_user_to_source(
                source_id=source_id,
                user_id=user_id,
                username=user_info["username"],
                first_name=user_info["first_name"],
            )

            display_name = user_info["first_name"]
            if user_info["username"]:
                display_name = f"{user_info['first_name']} (@{user_info['username']})"
            elif user_info["first_name"] == "Unknown":
                display_name = f"User {user_id}"

            text = (
                "✅ <b>User Added</b>\n\n"
                f"Name: {display_name}\n"
                f"User ID: <code>{user_id}</code>\n"
                "This user can now trigger token forwards from this source."
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source_id}")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
            ])

            await message.reply(text, reply_markup=keyboard)
            await state.clear()

        except Exception as exc:  # pragma: no cover
            logger.error("Error processing user input: %s", exc)
            await message.reply("❌ Error adding user")
            await state.clear()

    async def manage_source_users(self, query: types.CallbackQuery, source_id: int):
        """Show user management for a source."""
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            users = await self.source_model.get_source_users(source_id)

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
                            callback_data=f"sources:remove_user:{source_id}:{user['user_id']}",
                        )
                    ])

            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error managing source users: %s", exc)
            await query.answer("❌ Error loading users")

    async def remove_user_from_source(self, query: types.CallbackQuery, source_id: int, user_id: int):
        """Remove user from source."""
        try:
            success = await self.source_model.remove_user_from_source(source_id, user_id)

            if success:
                await query.answer("✅ User removed")
                await self.manage_source_users(query, source_id)
            else:
                await query.answer("❌ Failed to remove user")

        except Exception as exc:  # pragma: no cover
            logger.error("Error removing user: %s", exc)
            await query.answer("❌ Error removing user")
