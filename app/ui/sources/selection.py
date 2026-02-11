from __future__ import annotations

import logging

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


async def handle_source_group_selection(service, query: types.CallbackQuery, state: FSMContext):
    """Handle source group selection - show source type picker."""
    try:
        group_id = int(query.data.split(':', 1)[1])
        await state.set_data({'group_id': group_id})

        group = await service.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
        group_name = group['title'] or f"Chat {group['tg_chat_id']}"

        text = (
            f"<b>➕ Add Source for {group_name}</b>\n\n"
            "What type of source are you adding?\n\n"
            "📢 <b>Channel</b> - Monitors all posts from a channel\n"
            "👥 <b>Group</b> - Monitors group with user filtering\n"
            "💬 <b>DM</b> - Monitors direct messages from a user"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="📢 Channel", callback_data=f"source_type:channel:{group_id}"),
                InlineKeyboardButton(text="👥 Group", callback_data=f"source_type:group:{group_id}"),
            ],
            [InlineKeyboardButton(text="💬 DM", callback_data=f"source_type:dm:{group_id}")],
            [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")],
        ])

        await query.message.edit_text(text, reply_markup=keyboard)
    except Exception as error:  # pragma: no cover
        logger.error("Error handling source group selection: %s", error)
        await query.answer("❌ Error processing selection")


async def handle_source_type_selection(service, query: types.CallbackQuery, state: FSMContext):
    """Handle source type selection for adding a new source."""
    try:
        parts = query.data.split(':')
        source_type = parts[1]
        group_id = int(parts[2])

        data = await state.get_data()
        data['source_type'] = source_type
        await state.set_data(data)
        await state.set_state(ManagementStates.adding_source_chat_id)

        group = await service.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
        group_name = group['title'] or f"Chat {group['tg_chat_id']}"

        type_instructions = {
            'channel': {
                'emoji': '📢',
                'name': 'Channel',
                'id_format': 'Channel ID (negative): -1001234567890',
                'example': '-1001234567890',
                'validation': 'Must be negative and typically start with -100',
            },
            'group': {
                'emoji': '👥',
                'name': 'Group',
                'id_format': 'Group ID (negative): -1001234567890 or -123456789',
                'example': '-1001234567890',
                'validation': 'Must be negative',
            },
            'dm': {
                'emoji': '💬',
                'name': 'DM',
                'id_format': 'User ID (positive): 123456789',
                'example': '123456789',
                'validation': 'Must be positive',
            },
        }

        info = type_instructions[source_type]

        text = (
            f"<b>➕ Add {info['emoji']} {info['name']} Source</b>\n\n"
            f"Target Group: <b>{group_name}</b>\n"
            f"Source Type: {info['emoji']} {info['name']}\n\n"
            f"Please enter the {info['id_format']}\n\n"
            f"<b>Example:</b> <code>{info['example']}</code>\n\n"
            f"💡 <i>{info['validation']}</i>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")]]
        )

        await query.message.edit_text(text, reply_markup=keyboard)
    except Exception as error:  # pragma: no cover
        logger.error("Error handling source type selection: %s", error)
        await query.answer("❌ Error selecting source type")


async def handle_global_source_type_selection(service, query: types.CallbackQuery, state: FSMContext):
    """Handle global source type selection."""
    try:
        source_type = query.data.split(':', 1)[1]

        await state.set_data({'source_type': source_type})
        await state.set_state(ManagementStates.adding_source_chat_id)

        type_instructions = {
            'channel': {
                'emoji': '📢',
                'name': 'Channel',
                'id_format': 'Channel ID (negative): -1001234567890',
                'example': '-1001234567890',
                'validation': 'Must be negative and typically start with -100',
            },
            'group': {
                'emoji': '👥',
                'name': 'Group',
                'id_format': 'Group ID (negative): -1001234567890 or -123456789',
                'example': '-1001234567890',
                'validation': 'Must be negative',
            },
            'dm': {
                'emoji': '💬',
                'name': 'DM',
                'id_format': 'User ID (positive): 123456789',
                'example': '123456789',
                'validation': 'Must be positive',
            },
        }

        info = type_instructions[source_type]

        text = (
            f"<b>➕ Add {info['emoji']} {info['name']} Source</b>\n\n"
            f"Please enter the {info['id_format']}\n\n"
            f"<b>Example:</b> <code>{info['example']}</code>\n\n"
            f"💡 <i>{info['validation']}</i>\n\n"
            "<i>After adding, you can configure routing to target groups.</i>"
        )

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")]]
        )

        await query.message.edit_text(text, reply_markup=keyboard)
    except Exception as error:  # pragma: no cover
        logger.error("Error handling global source type selection: %s", error)
        await query.answer("❌ Error selecting source type")


async def handle_source_edit(service, query: types.CallbackQuery):
    """Handle source edit menu."""
    try:
        source_id = int(query.data.split(':', 1)[1])

        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        if not source:
            await query.answer("❌ Source not found")
            return

        title = source['title'] or f"ID: {source['source_chat_id']}"
        status = "✅ Enabled" if source['enabled'] else "❌ Disabled"
        type_name = "📢 Channel" if source['source_type'] == 'channel' else "👥 Group"

        text = (
            f"<b>⚙️ Edit Source</b>\n\n"
            f"{type_name} {title}\n"
            f"Status: {status}\n"
            f"Chat ID: <code>{source['source_chat_id']}</code>\n"
        )

        keyboard_rows = [[
            InlineKeyboardButton(
                text="🔄 Toggle Enable/Disable",
                callback_data=f"sources:toggle:{source_id}",
            )
        ]]

        if source['source_type'] == 'group':
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="👥 Manage Users",
                    callback_data=f"sources:users:{source_id}",
                )
            ])

        keyboard_rows.extend([
            [InlineKeyboardButton(text="🗑️ Remove Source", callback_data=f"sources:remove:{source_id}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")],
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        await query.message.edit_text(text, reply_markup=keyboard)
    except Exception as error:  # pragma: no cover
        logger.error("Error handling source edit: %s", error)
        await query.answer("❌ Error loading source")
