import logging

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class SourceInputMixin:
    """Text-input handlers for source creation flows."""

    async def process_source_input(self, message: types.Message, state: FSMContext):
        """Process source chat ID input."""
        try:
            data = await state.get_data()
            source_type = data.get('source_type')
            group_id = data.get('group_id')

            if not source_type:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return

            try:
                source_chat_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid chat ID. Please enter a valid number.")
                return

            if source_type == 'dm':
                if source_chat_id <= 0:
                    await message.reply("❌ DM user IDs must be positive numbers.")
                    return
                title = f"User {source_chat_id}"
            elif source_type in ['channel', 'group']:
                if source_chat_id >= 0:
                    await message.reply(f"❌ {source_type.title()} IDs must be negative numbers.")
                    return
                title = f"{source_type.title()} {source_chat_id}"
            else:
                await message.reply("❌ Invalid source type.")
                return

            if group_id:
                source = await self.source_model.add_source(
                    source_chat_id=source_chat_id,
                    source_type=source_type,
                    name=title,
                    title=title,
                )
                await self.source_model.add_routing_rule(source['id'], group_id)
            else:
                source = await self.source_model.add_source(
                    source_chat_id=source_chat_id,
                    source_type=source_type,
                    name=title,
                    title=title,
                )

            self.clear_cache()

            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            text = (
                f"✅ <b>{type_emojis.get(source_type, '')} {source_type.title()} Source Added</b>\n\n"
                f"Chat/User ID: <code>{source_chat_id}</code>\n"
                f"Type: {source_type.title()}\n\n"
            )

            keyboard_rows = []

            if group_id:
                if source_type == 'group':
                    text += (
                        "Since this is a group, you can configure which users are allowed to trigger forwards.\n"
                    )
                    keyboard_rows.append([
                        InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source['id']}")
                    ])
                elif source_type == 'channel':
                    text += "This channel will forward all token addresses posted."
                elif source_type == 'dm':
                    text += "This DM source will forward all token addresses from this user."

                keyboard_rows.extend([
                    [InlineKeyboardButton(text="📋 View Sources", callback_data=f"sources:select_group:{group_id}")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
                ])
            else:
                text += "Source added to global pool!\n\n"
                if source_type == 'group':
                    text += "Next steps:\n• Configure user filtering (optional)\n• Set up routing to target groups"
                    keyboard_rows.append([
                        InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source['id']}")
                    ])
                elif source_type == 'channel':
                    text += "Next step: Set up routing to target groups"
                elif source_type == 'dm':
                    text += "Next step: Set up routing to target groups"

                keyboard_rows.extend([
                    [InlineKeyboardButton(text="🔄 Setup Routing", callback_data=f"sources:add_route:{source['id']}")],
                    [InlineKeyboardButton(text="📋 View Sources", callback_data="sources:manage_global")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
                ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await message.reply(text, reply_markup=keyboard)
            await state.clear()

        except Exception as exc:  # pragma: no cover
            logger.error("Error processing source input: %s", exc)
            await message.reply("❌ Error adding source")
            await state.clear()
