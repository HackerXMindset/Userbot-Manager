from __future__ import annotations

import logging

from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def show_sources_menu(service, query: types.CallbackQuery):
    """Show global sources overview."""
    try:
        sources = await service.get_cached_sources()

        text = "<b>📡 Global Sources</b>\n\n"
        text += "Source chats monitor for token addresses and route them to targets.\n\n"

        if not sources:
            text += "No sources configured yet."
        else:
            for source in sources[:8]:  # Show max 8 sources
                type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
                status = "✅" if source['enabled'] else "❌"
                type_emoji = type_emojis.get(source['source_type'], '📡')
                name = (
                    source.get('display_name')
                    or source.get('group_display_name')
                    or source['name']
                    or source['title']
                    or f"ID: {source['source_chat_id']}"
                )
                route_count = source['route_count'] or 0

                text += f"{status} {type_emoji} <b>{name}</b>\n"
                text += f"   Routes: {route_count} targets\n"

                monitor_bot = source.get('monitoring_bot_name', 'None')
                forward_bot = source.get('forwarding_bot_name', 'None')
                text += f"   Monitor: {monitor_bot} | Forward: {forward_bot}\n\n"

        keyboard_rows = [
            [
                InlineKeyboardButton(text="➕ Add Source", callback_data="sources:add_global"),
                InlineKeyboardButton(text="🔄 Routing", callback_data="sources:routing:1"),
            ]
        ]

        if sources:
            keyboard_rows.append([
                InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")
            ])

        keyboard_rows.extend([
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:sources")],
            [InlineKeyboardButton(text="🗑️ Clear Cache", callback_data="sources:clear_cache")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")],
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        try:
            await query.message.edit_text(text, reply_markup=keyboard)
        except Exception as edit_error:  # pragma: no cover - API quirk handling
            if "message is not modified" in str(edit_error):
                await query.answer()
            else:
                raise

    except Exception as exc:  # pragma: no cover
        logger.error("Error showing sources menu: %s", exc)
        await query.answer("❌ Error loading sources")


async def show_manage_global_sources(service, query: types.CallbackQuery, page: int = 1):
    """Show all sources for management."""
    logger.debug("Entering show_manage_global_sources, page=%s", page)
    try:
        sources = await service.get_cached_sources()
        logger.debug("Found %s sources from cache.", len(sources))

        page_size = 9
        total_pages = (len(sources) + page_size - 1) // page_size or 1
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_sources = sources[start_index:end_index]

        text = f"<b>📋 Manage Global Sources (Page {page}/{total_pages})</b>\n\n"

        if not sources:
            text += "No sources configured yet."
        else:
            text += "Click a source to view details and manage routing:\n\n"

        keyboard_rows = []
        for source in paginated_sources:
            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            status = "✅" if source['enabled'] else "❌"
            type_emoji = type_emojis.get(source['source_type'], '📡')
            name = (
                source.get('display_name')
                or source.get('group_display_name')
                or source['name']
                or source['title']
                or f"ID: {source['source_chat_id']}"
            )

            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"{status} {type_emoji} {name}",
                    callback_data=f"sources:source_details:{source['id']}",
                )
            ])

        if total_pages > 1:
            pagination_buttons = service.keyboards.pagination("sources_manage_page", page, total_pages)
            keyboard_rows.append(pagination_buttons)

        keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as exc:  # pragma: no cover
        logger.error("Error showing manage sources: %s", exc, exc_info=True)
        await query.answer("❌ Error loading sources")


async def show_routing_menu(service, query: types.CallbackQuery, page: int = 1):
    """Show routing rules overview with pagination."""
    try:
        sources = await service.get_cached_sources()
        page_size = 9

        if not sources:
            text = "<b>🔄 Routing Rules</b>\n\nNo sources configured yet to create routing rules for."
            keyboard_rows = [[InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")]]
            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
            return

        total_pages = (len(sources) + page_size - 1) // page_size or 1
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        paginated_sources = sources[start_index:end_index]

        text = f"<b>🔄 Routing Rules (Page {page}/{total_pages})</b>\n\n"
        text += "Manage how sources route to target groups.\n\n"
        text += "Select a source to manage its routing:"

        keyboard_rows = []
        for source in paginated_sources:
            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            type_emoji = type_emojis.get(source['source_type'], '📡')
            name = (
                source.get('display_name')
                or source.get('group_display_name')
                or source['name']
                or source['title']
                or f"ID: {source['source_chat_id']}"
            )
            route_count = source['route_count'] or 0

            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"{type_emoji} {name} ({route_count} routes)",
                    callback_data=f"sources:source_details:{source['id']}",
                )
            ])

        if total_pages > 1:
            pagination_buttons = service.keyboards.pagination("sources:routing", page, total_pages)
            keyboard_rows.append(pagination_buttons)

        keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as exc:  # pragma: no cover
        logger.error("Error showing routing menu: %s", exc, exc_info=True)
        await query.answer("❌ Error loading routing menu")
