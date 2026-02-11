from __future__ import annotations

import logging
from typing import Optional

from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


class SourceRoutingMixin:
    """Routing wizard helpers for sources."""

    async def show_add_route_menu(self, query: types.CallbackQuery, source_id: int, page: int = 1):
        """Show available groups to route to with pagination."""
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            if not source:
                await query.answer("❌ Source not found")
                return

            groups = await self.get_cached_groups()
            existing_routes = await self.source_model.get_routing_rules(source_id)
            existing_group_ids = {route['target_group_id'] for route in existing_routes}

            available_groups = [g for g in groups if g['id'] not in existing_group_ids]
            source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"

            page_size = 9
            total_pages = max((len(available_groups) + page_size - 1) // page_size, 1)
            page = max(1, min(page, total_pages))
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_groups = available_groups[start_index:end_index]

            text = f"<b>➕ Add Route for {source_name} (Page {page}/{total_pages})</b>\n\n"
            keyboard_rows = []

            if not available_groups:
                text += "No available groups to route to.\nAll groups already have routing rules from this source."
            else:
                text += "Select target group to route to:"
                for group in paginated_groups:
                    group_name = (
                        group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                    )
                    status_icon = "✅" if group['enabled'] else "❌"
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            text=f"{status_icon} {group_name}",
                            callback_data=f"sources:create_route:{source_id}:{group['id']}",
                        )
                    ])

            if total_pages > 1:
                pagination_buttons = self.keyboards.pagination(f"add_route_page:{source_id}", page, total_pages)
                keyboard_rows.append(pagination_buttons)

            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer()

        except Exception as exc:  # pragma: no cover
            logger.error("Error showing add route menu: %s", exc, exc_info=True)
            await query.answer("❌ Error loading available routes")

    async def show_userbot_selection(
        self,
        query: types.CallbackQuery,
        source_id: int,
        group_id: int,
        monitor_bot_id: Optional[int] = None,
        forward_bot_id: Optional[int] = None,
    ):
        """Show userbot assignment UI for a route."""
        try:
            from app.models.bot import BotModel

            bot_model = BotModel(self.db)
            route = await self.db.fetchrow(
                "SELECT * FROM routing_rules WHERE source_chat_id = $1 AND target_group_id = $2",
                source_id,
                group_id,
            )
            if route:
                if monitor_bot_id is None:
                    monitor_bot_id = route.get('monitoring_userbot_id')
                if forward_bot_id is None:
                    forward_bot_id = route.get('forwarding_userbot_id')

            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)

            if monitor_bot_id is None and source:
                monitor_bot_id = source.get('default_monitoring_userbot_id')
            if forward_bot_id is None and source:
                forward_bot_id = source.get('default_forwarding_userbot_id')

            source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

            monitor_bot_name = "Not Set"
            if monitor_bot_id:
                bot = await bot_model.get_by_id(monitor_bot_id)
                if bot:
                    monitor_bot_name = bot.get('display_name') or bot['session_name']

            forward_bot_name = "Not Set"
            if forward_bot_id:
                bot = await bot_model.get_by_id(forward_bot_id)
                if bot:
                    forward_bot_name = bot.get('display_name') or bot['session_name']

            text = (
                f"<b>🤖 Assign Userbots</b>\n\n"
                f"<b>Source:</b> {source_name}\n"
                f"<b>Target:</b> {group_name}\n\n"
                "Select userbots for monitoring this source and forwarding calls to the target.\n\n"
                f"👁️ <b>Monitor Bot:</b> {monitor_bot_name}\n"
                f"📤 <b>Forward Bot:</b> {forward_bot_name}"
            )

            keyboard_rows = [
                [
                    InlineKeyboardButton(
                        text="👁️ Set Monitor",
                        callback_data=f"sources:select_role:{source_id}:{group_id}:monitor:{monitor_bot_id or 0}:{forward_bot_id or 0}",
                    ),
                    InlineKeyboardButton(
                        text="📤 Set Forward",
                        callback_data=f"sources:select_role:{source_id}:{group_id}:forward:{monitor_bot_id or 0}:{forward_bot_id or 0}",
                    ),
                ]
            ]

            if monitor_bot_id or forward_bot_id:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text="✅ Save Assignment",
                        callback_data=f"sources:finalize_route:{source_id}:{group_id}:{monitor_bot_id or 'None'}:{forward_bot_id or 'None'}",
                    )
                ])

            keyboard_rows.extend([
                [InlineKeyboardButton(text="⭐ Auto-assign Both", callback_data=f"sources:auto_assign:{source_id}:{group_id}")],
                [InlineKeyboardButton(text="➡️ Create Without Assignment", callback_data=f"sources:finalize_route:{source_id}:{group_id}:None:None")],
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")],
            ])

            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))

        except Exception as exc:  # pragma: no cover
            logger.error("Error in show_userbot_selection: %s", exc, exc_info=True)
            await query.answer("❌ Error loading userbot assignment UI")

    async def show_bot_picker(
        self,
        query: types.CallbackQuery,
        source_id: int,
        group_id: int,
        role: str,
        monitor_bot_id: int,
        forward_bot_id: int,
    ):
        """Show a list of userbots to choose for a role."""
        try:
            from app.models.bot import BotModel

            bot_model = BotModel(self.db)
            userbots = await bot_model.get_active_userbots()

            text = f"<b>Select {role.title()} Bot</b>"
            keyboard_rows = []
            for bot in userbots:
                bot_name = bot.get('display_name') or bot['session_name']

                new_monitor_id = bot['id'] if role == 'monitor' else monitor_bot_id
                new_forward_id = bot['id'] if role == 'forward' else forward_bot_id

                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=bot_name,
                        callback_data=f"sources:set_bot:{source_id}:{group_id}:{new_monitor_id}:{new_forward_id}",
                    )
                ])

            new_monitor_id = 0 if role == 'monitor' else monitor_bot_id
            new_forward_id = 0 if role == 'forward' else forward_bot_id
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="🚫 Unset",
                    callback_data=f"sources:set_bot:{source_id}:{group_id}:{new_monitor_id}:{new_forward_id}",
                )
            ])

            keyboard_rows.append([
                InlineKeyboardButton(
                    text="🔙 Back",
                    callback_data=f"sources:set_bot:{source_id}:{group_id}:{monitor_bot_id}:{forward_bot_id}",
                )
            ])

            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))

        except Exception as exc:  # pragma: no cover
            logger.error("Error in show_bot_picker: %s", exc, exc_info=True)
            await query.answer("❌ Error loading bot list")

    async def handle_auto_assign(self, query: types.CallbackQuery, source_id: int, group_id: int):
        """Handle auto-assignment of both monitoring and forwarding to first available userbot."""
        try:
            from app.models.bot import BotModel

            bot_model = BotModel(self.db)
            userbots = await bot_model.get_active_userbots()

            if not userbots:
                await query.answer("❌ No active userbots available")
                return

            first_bot = userbots[0]
            await self.create_routing_rule(query, source_id, group_id, first_bot['id'], first_bot['id'])

        except Exception as exc:  # pragma: no cover
            logger.error("Error handling auto assign: %s", exc)
            await query.answer("❌ Error auto-assigning userbots")

    async def create_routing_rule(
        self,
        query: types.CallbackQuery,
        source_id: int,
        group_id: int,
        monitoring_userbot_id: int = None,
        forwarding_userbot_id: int = None,
    ):
        """Create a new routing rule with optional userbot assignments."""
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)

            if not source or not group:
                await query.answer("❌ Source or group not found")
                return

            await self.source_model.add_routing_rule(
                source_id,
                group_id,
                monitoring_userbot_id,
                forwarding_userbot_id,
            )

            self.clear_cache()

            source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

            text = (
                "✅ <b>Routing Rule Created</b>\n\n"
                f"<b>Source:</b> {source_name}\n"
                f"<b>Target:</b> {group_name}\n\n"
            )

            if monitoring_userbot_id or forwarding_userbot_id:
                text += "<b>Userbot Assignments:</b>\n"
                if monitoring_userbot_id:
                    monitor_bot = await self.db.fetchrow("SELECT session_name FROM bots WHERE id = $1", monitoring_userbot_id)
                    text += f"• Monitor: {monitor_bot['session_name'] if monitor_bot else 'Unknown'}\n"
                if forwarding_userbot_id:
                    forward_bot = await self.db.fetchrow("SELECT session_name FROM bots WHERE id = $1", forwarding_userbot_id)
                    text += f"• Forward: {forward_bot['session_name'] if forward_bot else 'Unknown'}\n"
                text += "\n"

            text += "Tokens detected in this source will now be forwarded to the target group."

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Add Another Route", callback_data=f"sources:add_route:{source_id}"),
                    InlineKeyboardButton(text="⚙️ Source Details", callback_data=f"sources:source_details:{source_id}"),
                ],
                [InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Route created successfully")

        except Exception as exc:  # pragma: no cover
            logger.error("Error creating routing rule: %s", exc)
            await query.answer("❌ Error creating routing rule")

    async def remove_routing_rule(self, query: types.CallbackQuery, source_id: int, group_id: int):
        """Remove a routing rule."""
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)

            if not source or not group:
                await query.answer("❌ Source or group not found")
                return

            success = await self.source_model.remove_routing_rule(source_id, group_id)
            self.clear_cache()

            source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

            if success:
                text = (
                    "✅ <b>Routing Rule Removed</b>\n\n"
                    f"<b>Source:</b> {source_name}\n"
                    f"<b>Target:</b> {group_name}\n\n"
                    "This source will no longer forward tokens to this target."
                )
                await query.answer("✅ Route removed successfully")
            else:
                text = (
                    "❌ <b>Route Removal Failed</b>\n\n"
                    f"Could not remove route from {source_name} to {group_name}.\n"
                    "The route may have already been removed."
                )
                await query.answer("❌ Failed to remove route")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="⚙️ Source Details", callback_data=f"sources:source_details:{source_id}")],
                [InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error removing routing rule: %s", exc)
            await query.answer("❌ Error removing routing rule")
