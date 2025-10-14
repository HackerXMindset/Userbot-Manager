import logging
from typing import Optional

from aiogram import types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def show_add_route_menu(service, query: types.CallbackQuery, source_id: int, page: int = 1):
    """Show available groups to route to with pagination."""
    try:
        # Get source info
        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        if not source:
            await query.answer("❌ Source not found")
            return

        # Get all groups (with caching)
        groups = await service.get_cached_groups()

        # Get existing routing rules to exclude them
        existing_routes = await service.source_model.get_routing_rules(source_id)
        existing_group_ids = {route['target_group_id'] for route in existing_routes}

        # Filter out groups that already have routes
        available_groups = [g for g in groups if g['id'] not in existing_group_ids]

        source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"

        # Pagination
        page_size = 9
        total_pages = (len(available_groups) + page_size - 1) // page_size
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
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                status_icon = "✅" if group['enabled'] else "❌"

                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {group_name}",
                        callback_data=f"sources:create_route:{source_id}:{group['id']}"
                    )
                ])

        if total_pages > 1:
            # Use a unique prefix for this pagination
            pagination_buttons = service.keyboards.pagination(f"add_route_page:{source_id}", page, total_pages)
            keyboard_rows.append(pagination_buttons)

        keyboard_rows.append([
            InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")
        ])

        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        await query.message.edit_text(text, reply_markup=keyboard)
        await query.answer()

    except Exception as e:
        logger.error(f"Error showing add route menu: {e}", exc_info=True)
        await query.answer("❌ Error loading available routes")


async def show_userbot_selection(service, query: types.CallbackQuery, source_id: int, group_id: int, monitor_bot_id: Optional[int] = None, forward_bot_id: Optional[int] = None):
    """Show userbot assignment UI for a route."""
    try:
        from app.models.bot import BotModel
        bot_model = BotModel(service.db)

        # Get existing route to pre-fill selections
        route = await service.db.fetchrow("SELECT * FROM routing_rules WHERE source_chat_id = $1 AND target_group_id = $2", source_id, group_id)
        if route:
            if monitor_bot_id is None:
                monitor_bot_id = route.get('monitoring_userbot_id')
            if forward_bot_id is None:
                forward_bot_id = route.get('forwarding_userbot_id')

        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        group = await service.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)

        # Fall back to source-level bot assignments if routing-level ones aren't set
        if monitor_bot_id is None and source:
            monitor_bot_id = source.get('default_monitoring_userbot_id')
        if forward_bot_id is None and source:
            forward_bot_id = source.get('default_forwarding_userbot_id')

        source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
        group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

        # Get names for selected bots
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

        keyboard_rows = []

        # Buttons to change selection
        keyboard_rows.append([
            InlineKeyboardButton(text="👁️ Set Monitor", callback_data=f"sources:select_role:{source_id}:{group_id}:monitor:{monitor_bot_id or 0}:{forward_bot_id or 0}"),
            InlineKeyboardButton(text="📤 Set Forward", callback_data=f"sources:select_role:{source_id}:{group_id}:forward:{monitor_bot_id or 0}:{forward_bot_id or 0}")
        ])

        # Save button
        if monitor_bot_id or forward_bot_id:
            keyboard_rows.append([
                InlineKeyboardButton(text="✅ Save Assignment", callback_data=f"sources:finalize_route:{source_id}:{group_id}:{monitor_bot_id or 'None'}:{forward_bot_id or 'None'}")
            ])

        keyboard_rows.extend([
            [InlineKeyboardButton(text="⭐ Auto-assign Both", callback_data=f"sources:auto_assign:{source_id}:{group_id}")],
            [InlineKeyboardButton(text="➡️ Create Without Assignment", callback_data=f"sources:finalize_route:{source_id}:{group_id}:None:None")],
            [InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")]
        ])

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
    except Exception as e:
        logger.error(f"Error in show_userbot_selection: {e}", exc_info=True)
        await query.answer("❌ Error loading userbot assignment UI")


async def show_bot_picker(service, query: types.CallbackQuery, source_id: int, group_id: int, role: str, monitor_bot_id: int, forward_bot_id: int):
    """Show a list of userbots to choose for a role."""
    try:
        from app.models.bot import BotModel
        bot_model = BotModel(service.db)
        userbots = await bot_model.get_active_userbots()

        text = f"<b>Select {role.title()} Bot</b>"

        keyboard_rows = []
        for bot in userbots:
            bot_name = bot.get('display_name') or bot['session_name']

            new_monitor_id = bot['id'] if role == 'monitor' else monitor_bot_id
            new_forward_id = bot['id'] if role == 'forward' else forward_bot_id

            keyboard_rows.append([
                InlineKeyboardButton(text=bot_name, callback_data=f"sources:set_bot:{source_id}:{group_id}:{new_monitor_id}:{new_forward_id}")
            ])

        # Unset button
        new_monitor_id = 0 if role == 'monitor' else monitor_bot_id
        new_forward_id = 0 if role == 'forward' else forward_bot_id
        keyboard_rows.append([
            InlineKeyboardButton(text="🚫 Unset", callback_data=f"sources:set_bot:{source_id}:{group_id}:{new_monitor_id}:{new_forward_id}")
        ])

        # Back button
        keyboard_rows.append([
            InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:set_bot:{source_id}:{group_id}:{monitor_bot_id}:{forward_bot_id}")
        ])

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
    except Exception as e:
        logger.error(f"Error in show_bot_picker: {e}", exc_info=True)
        await query.answer("❌ Error loading bot list")


async def handle_auto_assign(service, query: types.CallbackQuery, source_id: int, group_id: int):
    """Handle auto-assignment of both monitoring and forwarding to first available userbot"""
    try:
        from app.models.bot import BotModel
        bot_model = BotModel(service.db)
        userbots = await bot_model.get_active_userbots()

        if not userbots:
            await query.answer("❌ No active userbots available")
            return

        # Use first available userbot for both roles
        first_bot = userbots[0]
        await create_routing_rule(service, query, source_id, group_id, first_bot['id'], first_bot['id'])

    except Exception as e:
        logger.error(f"Error handling auto assign: {e}")
        await query.answer("❌ Error auto-assigning userbots")


async def create_routing_rule(service, query: types.CallbackQuery, source_id: int, group_id: int,
                              monitoring_userbot_id: Optional[int] = None, forwarding_userbot_id: Optional[int] = None):
    """Create a new routing rule with optional userbot assignments"""
    try:
        # Get source and group info
        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        group = await service.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)

        if not source or not group:
            await query.answer("❌ Source or group not found")
            return

        # Create the routing rule with userbot assignments
        await service.source_model.add_routing_rule(source_id, group_id, monitoring_userbot_id, forwarding_userbot_id)

        # Clear cache since we added new routing rule
        service.clear_cache()

        source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
        group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

        text = f"✅ <b>Routing Rule Created</b>\n\n"
        text += f"<b>Source:</b> {source_name}\n"
        text += f"<b>Target:</b> {group_name}\n\n"

        # Show userbot assignments if any
        if monitoring_userbot_id or forwarding_userbot_id:
            text += "<b>Userbot Assignments:</b>\n"
            if monitoring_userbot_id:
                monitor_bot = await service.db.fetchrow("SELECT session_name FROM bots WHERE id = $1", monitoring_userbot_id)
                text += f"• Monitor: {monitor_bot['session_name'] if monitor_bot else 'Unknown'}\n"
            if forwarding_userbot_id:
                forward_bot = await service.db.fetchrow("SELECT session_name FROM bots WHERE id = $1", forwarding_userbot_id)
                text += f"• Forward: {forward_bot['session_name'] if forward_bot else 'Unknown'}\n"
            text += "\n"

        text += "Tokens detected in this source will now be forwarded to the target group."

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="➕ Add Another Route", callback_data=f"sources:add_route:{source_id}"),
                InlineKeyboardButton(text="⚙️ Source Details", callback_data=f"sources:source_details:{source_id}")
            ],
            [InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)
        await query.answer("✅ Route created successfully")

    except Exception as e:
        logger.error(f"Error creating routing rule: {e}")
        await query.answer("❌ Error creating routing rule")


async def remove_routing_rule(service, query: types.CallbackQuery, source_id: int, group_id: int):
    """Remove a routing rule"""
    try:
        # Get source and group info for confirmation message
        source = await service.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
        group = await service.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)

        if not source or not group:
            await query.answer("❌ Source or group not found")
            return

        # Remove the routing rule
        success = await service.source_model.remove_routing_rule(source_id, group_id)

        # Clear cache since we removed routing rule
        service.clear_cache()

        source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
        group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"

        if success:
            text = f"✅ <b>Routing Rule Removed</b>\n\n"
            text += f"<b>Source:</b> {source_name}\n"
            text += f"<b>Target:</b> {group_name}\n\n"
            text += "This source will no longer forward tokens to this target."

            await query.answer("✅ Route removed successfully")
        else:
            text = f"❌ <b>Route Removal Failed</b>\n\n"
            text += f"Could not remove route from {source_name} to {group_name}.\n"
            text += "The route may have already been removed."

            await query.answer("❌ Failed to remove route")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚙️ Source Details", callback_data=f"sources:source_details:{source_id}")],
            [InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error removing routing rule: {e}")
        await query.answer("❌ Error removing routing rule")
