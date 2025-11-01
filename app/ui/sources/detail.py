import json
import logging
from typing import Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


async def start_add_global_source(service, query: types.CallbackQuery, state: FSMContext):
    """Start adding a global source - show type selection"""
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
                InlineKeyboardButton(text="👥 Group", callback_data="source_global_type:group")
            ],
            [
                InlineKeyboardButton(text="💬 DM", callback_data="source_global_type:dm")
            ],
            [
                InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")
            ]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error starting add global source: {e}")
        await query.answer("❌ Error starting source setup")


async def start_add_source(service, query: types.CallbackQuery):
    """Start adding a source - select group"""
    try:
        groups = await service.get_cached_groups()

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
                    callback_data=f"source_group:{group['id']}"
                )
            ])

        keyboard_rows.append([
            InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error starting add source: {e}")
        await query.answer("❌ Error starting source setup")


async def show_manage_sources(service, query: types.CallbackQuery):
    """Show source management - select group"""
    try:
        groups = await service.get_cached_groups()

        text = "<b>📋 Manage Sources</b>\n\n"
        text += "Select group to manage its sources:"

        keyboard_rows = []
        for group in groups:
            sources = await service.source_model.get_by_group(group['id'])
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"{group_name} ({len(sources)} sources)",
                    callback_data=f"sources:select_group:{group['id']}"
                )
            ])

        keyboard_rows.append([
            InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing manage sources: {e}")
        await query.answer("❌ Error loading sources")


async def show_group_sources(service, query: types.CallbackQuery, group_id: int):
    """Show sources for a specific group"""
    try:
        group = await service.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
        sources = await service.source_model.get_by_group(group_id)

        group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
        text = f"<b>📋 Sources for {group_name}</b>\n\n"

        if not sources:
            text += "No sources configured."
        else:
            for source in sources:
                status = "✅" if source['enabled'] else "❌"
                type_emoji = "📢" if source['source_type'] == 'channel' else "👥"
                title = source['title'] or f"ID: {source['source_chat_id']}"
                user_count = source['user_count'] if source['source_type'] == 'group' else "All"
                text += f"{status} {type_emoji} {title}\n"
                text += f"   Users: {user_count}\n\n"

        keyboard_rows = []
        for source in sources:
            title = (source['title'] or f"ID: {source['source_chat_id']}")[:25]
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"⚙️ {title}",
                    callback_data=f"source_edit:{source['id']}"
                )
            ])

        keyboard_rows.extend([
            [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing group sources: {e}")
        await query.answer("❌ Error loading group sources")


async def show_source_details(service, query: types.CallbackQuery, source_id: int):
    """Show detailed source information and routing management"""
    try:
        # Get source details with bot information
        source = await service.db.fetchrow("""
            SELECT sc.*,
                   COALESCE(mb.display_name, mb.session_name) as monitoring_bot_name,
                   COALESCE(fb.display_name, fb.session_name) as forwarding_bot_name
            FROM source_chats sc
            LEFT JOIN bots mb ON mb.id = sc.default_monitoring_userbot_id
            LEFT JOIN bots fb ON fb.id = sc.default_forwarding_userbot_id
            WHERE sc.id = $1
        """, source_id)
        if not source:
            await query.answer("❌ Source not found")
            return

        # Get routing rules
        routes = await service.source_model.get_routing_rules(source_id)

        type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
        status = "✅" if source['enabled'] else "❌"
        type_emoji = type_emojis.get(source['source_type'], '📡')
        name = source.get('display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"

        text = f"<b>⚙️ {type_emoji} Source Details</b>\n\n"
        text += f"<b>Name:</b> {name}\n"
        text += f"<b>Chat/User ID:</b> <code>{source['source_chat_id']}</code>\n"
        text += f"<b>Type:</b> {source['source_type'].title()}\n"
        text += f"<b>Status:</b> {status}\n\n"

        # Show source-level bot assignments
        monitor_bot = source.get('monitoring_bot_name') or 'None'
        forward_bot = source.get('forwarding_bot_name') or 'None'
        text += f"<b>🤖 Source-Level Bots:</b>\n"
        text += f"   Monitor: <code>{monitor_bot}</code>\n"
        text += f"   Forward: <code>{forward_bot}</code>\n\n"

        if routes:
            text += f"<b>🔄 Routing Rules ({len(routes)}):</b>\n"
            for route in routes:
                route_status = "✅" if route['enabled'] else "❌"
                group_name = route['group_title'] or f"Chat {route['tg_chat_id']}"

                # Format blockchain filter
                allowed_chains = route.get('allowed_chains', ['SOL'])
                if isinstance(allowed_chains, str):
                    try:
                        allowed_chains = json.loads(allowed_chains)
                    except Exception:
                        allowed_chains = ['SOL']
                chain_emojis = service.keyboards.format_blockchain_emojis(allowed_chains)

                forwarding_mode = (route.get('forwarding_mode') or 'tokens').lower()
                keyword_filters = route.get('keyword_filters', [])
                if isinstance(keyword_filters, str):
                    try:
                        keyword_filters = json.loads(keyword_filters)
                    except Exception:
                        keyword_filters = []
                keyword_filters = keyword_filters or []

                text += f"{route_status} → <b>{group_name}</b>\n"
                if forwarding_mode == 'tokens':
                    text += f"     Mode: 🔗 Token calls\n"
                    text += f"     Chains: {chain_emojis}\n"
                elif forwarding_mode == 'keywords':
                    text += f"     Mode: 📝 Keyword match\n"
                    if keyword_filters:
                        formatted_keywords = ", ".join(f"<code>{kw}</code>" for kw in keyword_filters)
                        text += f"     Keywords: {formatted_keywords}\n"
                    else:
                        text += "     Keywords: <i>None configured</i>\n"
                elif forwarding_mode == 'everything':
                    text += f"     Mode: 📬 Forward everything\n"
                else:
                    text += f"     Mode: {forwarding_mode}\n"

                rewrite_rules = route.get('forward_rewrite_rules') or []
                if rewrite_rules:
                    if isinstance(rewrite_rules, str):
                        try:
                            rewrite_rules = json.loads(rewrite_rules)
                        except Exception:
                            rewrite_rules = []
                    replacements_display = []
                    for rewrite in rewrite_rules:
                        if not isinstance(rewrite, dict):
                            continue
                        source_val = rewrite.get('source') or ''
                        target_val = rewrite.get('target') or ''
                        if not source_val:
                            continue
                        if target_val:
                            replacements_display.append(f"{source_val} → {target_val}")
                        else:
                            replacements_display.append(f"{source_val} → (removed)")
                    if replacements_display:
                        text += "     Replacements:\n"
                        for entry in replacements_display[:3]:
                            text += f"         • {entry}\n"
                        if len(replacements_display) > 3:
                            text += "         • …\n"

                # Add userbot assignments if present
                userbot_info = []
                monitor_name = route.get('monitoring_userbot_name')
                forward_name = route.get('forwarding_userbot_name')
                if monitor_name:
                    userbot_info.append(f"👁️ {monitor_name}")
                if forward_name:
                    userbot_info.append(f"📤 {forward_name}")

                if userbot_info:
                    text += f"     {' | '.join(userbot_info)}\n"
                else:
                    text += f"     🤖 Auto-assigned\n"

                media_status = "📸 Media forwarding enabled" if route.get('forward_media', True) else "🚫 Media forwarding disabled"
                text += f"     {media_status}\n"
        else:
            text += "📭 <b>No routing rules configured</b>\n"
            text += "Add routes to forward tokens to target groups."

        # Build keyboard
        keyboard_rows = [
            [
                InlineKeyboardButton(text="✏️ Set Name", callback_data=f"sources:set_name:{source_id}"),
                InlineKeyboardButton(
                    text="🔴 Disable" if source['enabled'] else "🟢 Enable",
                    callback_data=f"sources:toggle:{source_id}"
                )
            ],
            [
                InlineKeyboardButton(text="🤖 Set Monitor Bot", callback_data=f"sources:set_monitor:{source_id}"),
                InlineKeyboardButton(text="📤 Set Forward Bot", callback_data=f"sources:set_forward:{source_id}")
            ],
            [
                InlineKeyboardButton(text="❌ Clear Bots", callback_data=f"sources:clear_bots:{source_id}"),
                InlineKeyboardButton(
                    text="➕ Add Route",
                    callback_data=f"sources:add_route:{source_id}"
                )
            ]
        ]

        if source['source_type'] == 'group':
            keyboard_rows.append([
                InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source_id}")
            ])

        # Add edit/remove route buttons for existing routes
        for route in routes:
            group_name = (route['group_title'] or f"Chat {route['tg_chat_id']}")[:20]
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"🤖 Bots → {group_name}",
                    callback_data=f"sources:create_route:{source_id}:{route['target_group_id']}"
                ),
                InlineKeyboardButton(
                    text="🎛️ Filters",
                    callback_data=f"sources:route_filters:{route['id']}"
                ),
                InlineKeyboardButton(
                    text="🗑️",
                    callback_data=f"sources:remove_route:{source_id}:{route['target_group_id']}"
                )
            ])

        keyboard_rows.extend([
            [InlineKeyboardButton(text="🗑️ Delete Source", callback_data=f"sources:delete:{source_id}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage_global")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error showing source details: {e}")
        await query.answer("❌ Error loading source details")


async def start_set_source_name(service, query: types.CallbackQuery, source_id: int, state: FSMContext):
    """Start source name setting process"""
    try:
        source = await service.source_model.get_by_id(source_id)
        if not source:
            await query.answer("Source not found!")
            return

        current_name = source.get('display_name') or source['name'] or source['title'] or f"Source {source['source_chat_id']}"

        await query.message.edit_text(
            f"<b>✏️ Set Source Name</b>\n\n"
            f"Current name: <b>{current_name}</b>\n\n"
            f"Enter a new custom name for this source:\n\n"
            f"Type /cancel to abort.",
            reply_markup=service.keyboards.cancel_button(f"sources:source_details:{source_id}")
        )

        await state.set_state(ManagementStates.source_set_name)
        await state.update_data(
            source_id=source_id,
            message_id=query.message.message_id
        )

    except Exception as e:
        logger.error(f"Error starting source name setting: {e}")
        await query.answer("❌ Error starting name setting")


async def process_source_name_input(service, message: types.Message, state: FSMContext):
    """Process source name input"""
    if message.text == '/cancel':
        data = await state.get_data()
        source_id = data.get('source_id')
        await message.answer("❌ Name setting cancelled.")
        await state.clear()
        return

    new_name = message.text.strip()
    await message.delete()  # Clean up user input

    # Validate name
    if not new_name or len(new_name) > 50:
        await message.answer("❌ Name must be 1-50 characters long.")
        return

    try:
        data = await state.get_data()
        source_id = data.get('source_id')

        if not source_id:
            await message.answer("❌ Session data lost. Please try again.")
            await state.clear()
            return

        # Update source name in database (direct SQL to avoid updated_at requirement)
        await service.db.execute(
            "UPDATE source_chats SET display_name = $1 WHERE id = $2",
            new_name, source_id
        )

        await message.answer(
            f"✅ <b>Source Name Updated Successfully!</b>\n\n"
            f"Source name set to: <b>{new_name}</b>"
        )

        await state.clear()

    except Exception as e:
        logger.error(f"Error updating source name: {e}")
        await message.answer(f"❌ Error updating name: {str(e)}")
        await state.clear()

        # Try to show error message
        try:
            text = f"❌ <b>Rename Error</b>\n\n"
            text += f"Failed to update the source name due to an error:\n<code>{str(e)}</code>\n\n"
            text += "Please try again or contact support."

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])

            await message.answer(text, reply_markup=keyboard)
        except Exception:
            pass


async def show_monitor_bot_selection(service, query: types.CallbackQuery, source_id: int):
    """Show available bots for monitor bot selection"""
    try:
        from app.models.bot import BotModel
        bot_model = BotModel(service.db)
        bots = await bot_model.get_active_userbots()

        text = "<b>🤖 Select Monitor Bot</b>\n\n"
        text += "Choose which userbot will monitor this source for tokens:\n\n"

        keyboard_rows = []
        for bot in bots:
            name = bot.get('display_name') or bot['session_name']
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"🤖 {name}",
                    callback_data=f"sources:select_monitor_bot:{source_id}:{bot['id']}"
                )
            ])

        keyboard_rows.append([
            InlineKeyboardButton(text="❌ Clear Monitor", callback_data=f"sources:select_monitor_bot:{source_id}:0")
        ])
        keyboard_rows.append([
            InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")
        ])

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))

    except Exception as e:
        logger.error(f"Error showing monitor bot selection: {e}")
        await query.answer("❌ Error loading bots")


async def show_forward_bot_selection(service, query: types.CallbackQuery, source_id: int):
    """Show available bots for forward bot selection"""
    try:
        from app.models.bot import BotModel
        bot_model = BotModel(service.db)
        bots = await bot_model.get_active_userbots()

        text = "<b>📤 Select Forward Bot</b>\n\n"
        text += "Choose which userbot will forward curated calls from this source:\n\n"

        keyboard_rows = []
        for bot in bots:
            name = bot.get('display_name') or bot['session_name']
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"🤖 {name}",
                    callback_data=f"sources:select_forward_bot:{source_id}:{bot['id']}"
                )
            ])

        keyboard_rows.append([
            InlineKeyboardButton(text="❌ Clear Forward", callback_data=f"sources:select_forward_bot:{source_id}:0")
        ])
        keyboard_rows.append([
            InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")
        ])

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))

    except Exception as e:
        logger.error(f"Error showing forward bot selection: {e}")
        await query.answer("❌ Error loading bots")


async def set_monitor_bot(service, query: types.CallbackQuery, source_id: int, bot_id: int):
    """Set or clear monitor bot for source"""
    try:
        # Get current source to preserve forward bot
        source = await service.source_model.get_by_id(source_id)
        if not source:
            await query.answer("❌ Source not found")
            return

        monitor_bot_id: Optional[int] = bot_id if bot_id != 0 else None
        current_forward_bot = source.get('default_forwarding_userbot_id')

        await service.source_model.update_source_bots(
            source_id,
            monitoring_userbot_id=monitor_bot_id,
            forwarding_userbot_id=current_forward_bot
        )

        action_text = "cleared" if monitor_bot_id is None else "set"
        await query.answer(f"✅ Monitor bot {action_text}!")
        await service.show_source_details(query, source_id)

    except Exception as e:
        logger.error(f"Error setting monitor bot: {e}")
        await query.answer("❌ Error updating monitor bot")


async def set_forward_bot(service, query: types.CallbackQuery, source_id: int, bot_id: int):
    """Set or clear forward bot for source"""
    try:
        # Get current source to preserve monitor bot
        source = await service.source_model.get_by_id(source_id)
        if not source:
            await query.answer("❌ Source not found")
            return

        forward_bot_id: Optional[int] = bot_id if bot_id != 0 else None
        current_monitor_bot = source.get('default_monitoring_userbot_id')

        await service.source_model.update_source_bots(
            source_id,
            monitoring_userbot_id=current_monitor_bot,
            forwarding_userbot_id=forward_bot_id
        )

        action_text = "cleared" if forward_bot_id is None else "set"
        await query.answer(f"✅ Forward bot {action_text}!")
        await service.show_source_details(query, source_id)

    except Exception as e:
        logger.error(f"Error setting forward bot: {e}")
        await query.answer("❌ Error updating forward bot")


async def clear_source_bots(service, query: types.CallbackQuery, source_id: int):
    """Clear both monitor and forward bots for source"""
    try:
        await service.source_model.update_source_bots(source_id, monitoring_userbot_id=None, forwarding_userbot_id=None)
        await query.answer("✅ Source bots cleared!")
        await service.show_source_details(query, source_id)

    except Exception as e:
        logger.error(f"Error clearing source bots: {e}")
        await query.answer("❌ Error clearing bots")
