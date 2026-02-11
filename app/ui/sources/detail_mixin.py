from __future__ import annotations

import logging
from typing import Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


class SourceDetailMixin:
    """Source creation, detail view, and bot assignment helpers."""

    async def start_add_global_source(self, query: types.CallbackQuery, state: FSMContext):
        """Start adding a global source - show type selection."""
        try:
            await state.clear()  # Clear any existing state

            text = "<b>➕ Add Global Source</b>\n\n"
            text += "What type of source are you adding?\n\n"
            text += "📢 <b>Channel</b> - Monitors all posts from a channel\n"
            text += "👥 <b>Group</b> - Monitors group with user filtering\n"
            text += "💬 <b>DM</b> - Monitors direct messages from a user"

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📢 Channel", callback_data="source_global_type:channel"),
                    InlineKeyboardButton(text="👥 Group", callback_data="source_global_type:group"),
                ],
                [InlineKeyboardButton(text="💬 DM", callback_data="source_global_type:dm")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")],
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error starting add global source: %s", exc)
            await query.answer("❌ Error starting source setup")

    async def start_add_source(self, query: types.CallbackQuery):
        """Start adding a source - select group."""
        try:
            groups = await self.get_cached_groups()

            if not groups:
                await query.answer("❌ No groups available. Add groups first.")
                return

            text = "<b>➕ Add Source Chat</b>\n\n"
            text += "Select which group this source should forward to:"

            keyboard_rows = []
            for group in groups:
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=group_name,
                        callback_data=f"source_group:{group['id']}",
                    )
                ])

            keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error starting add source: %s", exc)
            await query.answer("❌ Error starting source setup")

    async def show_manage_sources(self, query: types.CallbackQuery):
        """Show source management - select group."""
        try:
            groups = await self.get_cached_groups()

            text = "<b>📋 Manage Sources</b>\n\n"
            text += "Select group to manage its sources:"

            keyboard_rows = []
            for group in groups:
                sources = await self.source_model.get_by_group(group['id'])
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{group_name} ({len(sources)} sources)",
                        callback_data=f"sources:select_group:{group['id']}",
                    )
                ])

            keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error showing manage sources: %s", exc)
            await query.answer("❌ Error loading sources")

    async def show_group_sources(self, query: types.CallbackQuery, group_id: int):
        """Show sources for a specific group."""
        try:
            sources = await self.source_model.get_by_group(group_id)
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

            text = f"<b>📋 Sources for {group_name}</b>\n\n"
            if not sources:
                text += "No sources assigned to this group."
            else:
                for source in sources:
                    type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
                    status = "✅" if source['enabled'] else "❌"
                    type_emoji = type_emojis.get(source['source_type'], '📡')
                    name = source.get('display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
                    text += f"{status} {type_emoji} <b>{name}</b>\n"

            keyboard_rows = [
                [InlineKeyboardButton(text="➕ Add Source", callback_data=f"source_group:{group_id}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage_global")],
            ]

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error showing group sources: %s", exc)
            await query.answer("❌ Error loading sources")

    async def show_source_details(self, query: types.CallbackQuery, source_id: int):
        """Show detailed source information and routing management."""
        try:
            source = await self.db.fetchrow(
                """
                SELECT sc.*,
                       mb.session_name as monitoring_bot_name,
                       fb.session_name as forwarding_bot_name
                FROM source_chats sc
                LEFT JOIN bots mb ON mb.id = sc.default_monitoring_userbot_id
                LEFT JOIN bots fb ON fb.id = sc.default_forwarding_userbot_id
                WHERE sc.id = $1
                """,
                source_id,
            )
            if not source:
                await query.answer("❌ Source not found")
                return

            routes = await self.source_model.get_routing_rules(source_id)

            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            status = "✅" if source['enabled'] else "❌"
            type_emoji = type_emojis.get(source['source_type'], '📡')
            name = (
                source.get('display_name')
                or source['name']
                or source['title']
                or f"ID: {source['source_chat_id']}"
            )

            text = f"<b>⚙️ {type_emoji} Source Details</b>\n\n"
            text += f"<b>Name:</b> {name}\n"
            text += f"<b>Chat/User ID:</b> <code>{source['source_chat_id']}</code>\n"
            text += f"<b>Type:</b> {source['source_type'].title()}\n"
            text += f"<b>Status:</b> {status}\n\n"

            monitor_bot = source.get('monitoring_bot_name') or 'None'
            forward_bot = source.get('forwarding_bot_name') or 'None'
            text += "<b>🤖 Source-Level Bots:</b>\n"
            text += f"   Monitor: <code>{monitor_bot}</code>\n"
            text += f"   Forward: <code>{forward_bot}</code>\n\n"

            if routes:
                text += f"<b>🔄 Routing Rules ({len(routes)}):</b>\n"
                for route in routes:
                    route_status = "✅" if route['enabled'] else "❌"
                    group_name = route['group_title'] or f"Chat {route['tg_chat_id']}"

                    allowed_chains = route.get('allowed_chains', ['SOL'])
                    chain_emojis = self.keyboards.format_blockchain_emojis(allowed_chains)

                    text += f"{route_status} → <b>{group_name}</b>\n"
                    text += f"     {chain_emojis}\n"

                    userbot_info = []
                    if route['monitoring_userbot_name']:
                        userbot_info.append(f"👁️ {route['monitoring_userbot_name']}")
                    if route['forwarding_userbot_name']:
                        userbot_info.append(f"📤 {route['forwarding_userbot_name']}")

                    if userbot_info:
                        text += f"     {' | '.join(userbot_info)}\n"
                    else:
                        text += "     🤖 Auto-assigned\n"
            else:
                text += "📭 <b>No routing rules configured</b>\n"
                text += "Add routes to forward tokens to target groups."

            keyboard_rows = [
                [
                    InlineKeyboardButton(text="✏️ Set Name", callback_data=f"sources:set_name:{source_id}"),
                    InlineKeyboardButton(
                        text="🔴 Disable" if source['enabled'] else "🟢 Enable",
                        callback_data=f"sources:toggle:{source_id}",
                    ),
                ],
                [
                    InlineKeyboardButton(text="🤖 Set Monitor Bot", callback_data=f"sources:set_monitor:{source_id}"),
                    InlineKeyboardButton(text="📤 Set Forward Bot", callback_data=f"sources:set_forward:{source_id}"),
                ],
                [
                    InlineKeyboardButton(text="❌ Clear Bots", callback_data=f"sources:clear_bots:{source_id}"),
                    InlineKeyboardButton(
                        text="➕ Add Route",
                        callback_data=f"sources:add_route:{source_id}",
                    ),
                ],
            ]

            if source['source_type'] == 'group':
                keyboard_rows.append([
                    InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source_id}")
                ])

            for route in routes:
                group_name = (route['group_title'] or f"Chat {route['tg_chat_id']}")[:20]
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"🤖 Bots → {group_name}",
                        callback_data=f"sources:create_route:{source_id}:{route['target_group_id']}",
                    ),
                    InlineKeyboardButton(
                        text="⛓️ Chains",
                        callback_data=f"routing:edit_chains:{route['id']}",
                    ),
                    InlineKeyboardButton(
                        text="🗑️",
                        callback_data=f"sources:remove_route:{source_id}:{route['target_group_id']}",
                    ),
                ])

            keyboard_rows.extend([
                [InlineKeyboardButton(text="🗑️ Delete Source", callback_data=f"sources:delete:{source_id}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage_global")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")],
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error showing source details: %s", exc)
            await query.answer("❌ Error loading source details")

    async def start_set_source_name(self, query: types.CallbackQuery, source_id: int, state: FSMContext):
        """Prompt admin to set source display name."""
        try:
            await state.set_state(ManagementStates.source_set_name)
            await state.set_data({'source_id': source_id})

            await query.message.edit_text(
                "<b>✏️ Set Source Name</b>\n\n"
                "Send the display name for this source.\n"
                "Example: Pump.fun Alerts\n\n"
                "Type /cancel to abort.",
                reply_markup=self.keyboards.cancel_button(f"sources:source_details:{source_id}"),
            )
        except Exception as exc:  # pragma: no cover
            logger.error("Error starting source name input: %s", exc)
            await query.answer("❌ Error setting name")

    async def process_source_name_input(self, message: types.Message, state: FSMContext):
        """Handle name input for a source."""
        try:
            data = await state.get_data()
            source_id = data.get('source_id')
            if not source_id:
                await message.reply("❌ Session expired. Please try again.")
                await state.clear()
                return

            name = message.text.strip()
            if not name:
                await message.reply("❌ Name cannot be empty. Try again.")
                return

            await self.source_model.update_display_name(source_id, name)
            await message.reply(f"✅ Source name updated to <b>{name}</b>.")
            await state.clear()
        except Exception as exc:  # pragma: no cover
            logger.error("Error processing source name input: %s", exc)
            await message.reply("❌ Error updating name")
            await state.clear()

    async def show_monitor_bot_selection(self, query: types.CallbackQuery, source_id: int):
        """Show monitor bot selection for a source."""
        await self._show_bot_selection(query, source_id, role="monitor")

    async def show_forward_bot_selection(self, query: types.CallbackQuery, source_id: int):
        """Show forward bot selection for a source."""
        await self._show_bot_selection(query, source_id, role="forward")

    async def _show_bot_selection(self, query: types.CallbackQuery, source_id: int, role: str):
        try:
            bots = await self.db.fetch(
                """
                SELECT id, session_name, status
                FROM bots
                WHERE kind = 'userbot'
                ORDER BY status DESC, session_name
                """
            )

            if not bots:
                await query.answer("❌ No userbots available.", show_alert=True)
                return

            text = "<b>🤖 Select Userbot</b>\n\n"
            text += "Choose which userbot should "
            text += "monitor this source." if role == "monitor" else "forward messages for this source."

            keyboard_rows = []
            for bot in bots:
                status_icon = "🟢" if bot['status'] == 'active' else "🔴"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {bot['session_name']}",
                        callback_data=f"sources:set_{role}:{source_id}:{bot['id']}",
                    )
                ])

            keyboard_rows.append([
                InlineKeyboardButton(text="❌ Clear", callback_data=f"sources:clear_bots:{source_id}")
            ])
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")
            ])

            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as exc:  # pragma: no cover
            logger.error("Error showing bot selection: %s", exc)
            await query.answer("❌ Error loading userbots")

    async def set_monitor_bot(self, query: types.CallbackQuery, source_id: int, bot_id: int):
        """Assign monitor bot to a source."""
        try:
            await self.source_model.set_default_monitor_bot(source_id, bot_id)
            await query.answer("✅ Monitor bot set!")
            await self.show_source_details(query, source_id)
        except Exception as exc:  # pragma: no cover
            logger.error("Error setting monitor bot: %s", exc)
            await query.answer("❌ Error setting monitor bot")

    async def set_forward_bot(self, query: types.CallbackQuery, source_id: int, bot_id: int):
        """Assign forward bot to a source."""
        try:
            await self.source_model.set_default_forward_bot(source_id, bot_id)
            await query.answer("✅ Forward bot set!")
            await self.show_source_details(query, source_id)
        except Exception as exc:  # pragma: no cover
            logger.error("Error setting forward bot: %s", exc)
            await query.answer("❌ Error setting forward bot")

    async def clear_source_bots(self, query: types.CallbackQuery, source_id: int):
        """Clear default bots assigned to a source."""
        try:
            await self.source_model.clear_default_bots(source_id)
            await query.answer("✅ Bots cleared!")
            await self.show_source_details(query, source_id)
        except Exception as exc:  # pragma: no cover
            logger.error("Error clearing source bots: %s", exc)
            await query.answer("❌ Error clearing bots")
