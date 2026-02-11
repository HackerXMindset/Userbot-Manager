import json
import logging
from html import escape as html_escape
from dataclasses import dataclass
import textwrap
from typing import Any, Dict, List, Optional

from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


async def show_add_route_menu(service, query: types.CallbackQuery, source_id: int, page: int = 1):
    """Show available groups to route to with pagination."""
    try:
        source = await service.db.fetchrow(
            "SELECT name, title, display_name, source_chat_id FROM source_chats WHERE id = $1",
            source_id,
        )
        source_name = (
            (source.get("display_name") if source else None)
            or (source.get("name") if source else None)
            or (source.get("title") if source else None)
            or (f"ID: {source['source_chat_id']}" if source else f"Source {source_id}")
        )

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

        text = (
            f"<b>➕ Create Route</b>\n\n"
            f"<b>Source:</b> {source_name}\n"
            f"<b>Available Targets:</b> {len(available_groups)}\n"
        )

        text += "\nSelect a target group to connect this source. After you save the route, use <b>🎛️ Filters</b> to switch between token calls, keyword triggers, or forwarding every message.\n\n"
        text += f"<i>Showing page {page} of {max(total_pages, 1)}</i>\n"

        keyboard_rows = []

        if not available_groups:
            text += "No available groups to route to.\nAll groups already have routing rules from this source."
        else:
            text += "Select target group to route to:"

            for group in paginated_groups:
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                status_icon = "✅" if group['enabled'] else "❌"
                existing_sources = group.get("source_count") if hasattr(group, "get") else None
                suffix = f" • {existing_sources} sources" if existing_sources else ""

                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {group_name}{suffix}",
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




def _json_list(raw_value, default=None):
    if isinstance(raw_value, list):
        return list(raw_value)
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                return list(parsed)
        except Exception:
            return list(default or [])
    return list(default or [])


@dataclass
class RouteContext:
    id: int
    source_id: int
    source_chat_id: int
    source_name: str
    group_id: int
    group_chat_id: int
    group_name: str
    enabled: bool
    forwarding_mode: str
    allowed_chains: List[str]
    keyword_filters: List[str]
    rewrite_rules: List[Dict[str, str]]
    media_enabled: bool
    summary_enabled: bool
    monitor_bot_id: Optional[int]
    monitor_bot_name: Optional[str]
    forward_bot_id: Optional[int]
    forward_bot_name: Optional[str]


FORWARDING_MODE_LABELS = {
    'tokens': 'Token Calls',
    'keywords': 'Keyword Match',
    'everything': 'Forward Everything',
}

FORWARDING_MODE_DESCRIPTIONS = {
    'tokens': 'Detects contract addresses in the source and forwards calls only for supported blockchains.',
    'keywords': 'Forwards when a message contains any configured keyword (case-insensitive).',
    'everything': 'Every message is forwarded immediately. Filters and chains are ignored.',
}

CHAIN_BADGES = {
    'SOL': '🟣 SOL',
    'BNB': '🟡 BNB',
}


def _parse_rewrite_rules(raw_value: Any) -> List[Dict[str, str]]:
    values = _json_list(raw_value, default=[])
    normalized: List[Dict[str, str]] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        source_text = (value.get('source') or '').strip()
        target_text = (value.get('target') or '').strip()
        if source_text:
            normalized.append({'source': source_text, 'target': target_text})
    return normalized


def _format_chain_badges(chains: List[str]) -> str:
    if not chains:
        return '<i>None</i>'
    parts = [CHAIN_BADGES.get(chain.upper(), chain.upper()) for chain in chains]
    return ', '.join(parts)


def _mode_chip(mode: str, current: str) -> str:
    prefix = '✅' if mode == current else '☐'
    label = FORWARDING_MODE_LABELS.get(mode, mode.title())
    return f"{prefix} {label}"


def _mode_button_row(ctx: 'RouteContext') -> List[InlineKeyboardButton]:
    """Build the forwarding mode chip selector row."""
    return [
        InlineKeyboardButton(
            text=_mode_chip('tokens', ctx.forwarding_mode),
            callback_data=f"sources:set_route_mode:{ctx.id}:tokens",
        ),
        InlineKeyboardButton(
            text=_mode_chip('keywords', ctx.forwarding_mode),
            callback_data=f"sources:set_route_mode:{ctx.id}:keywords",
        ),
        InlineKeyboardButton(
            text=_mode_chip('everything', ctx.forwarding_mode),
            callback_data=f"sources:set_route_mode:{ctx.id}:everything",
        ),
    ]


def _shared_route_rows(ctx: 'RouteContext', include_overview: bool = True) -> List[List[InlineKeyboardButton]]:
    """Common control rows reused across overview and focused editors."""
    rows: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text='⛓️ Chains', callback_data=f"sources:route:{ctx.id}:chains"),
            InlineKeyboardButton(text='📝 Keywords', callback_data=f"sources:route:{ctx.id}:keywords"),
        ],
        [
            InlineKeyboardButton(text='🔁 Rewrites', callback_data=f"sources:route:{ctx.id}:rewrites"),
            InlineKeyboardButton(
                text='🧾 Summary ON' if ctx.summary_enabled else '🧾 Summary OFF',
                callback_data=f"sources:route:{ctx.id}:summary:{0 if ctx.summary_enabled else 1}",
            ),
        ],
        [
            InlineKeyboardButton(
                text='📸 Media ON' if ctx.media_enabled else '📸 Media OFF',
                callback_data=f"sources:route:{ctx.id}:media:{0 if ctx.media_enabled else 1}",
            ),
        ],
        [
            InlineKeyboardButton(
                text='🔒 Disable Route' if ctx.enabled else '🔓 Enable Route',
                callback_data=f"sources:route:{ctx.id}:toggle",
            ),
            InlineKeyboardButton(
                text='🤖 Assign Bots',
                callback_data=f"sources:assign_route_bots:{ctx.source_id}:{ctx.group_id}",
            ),
        ],
        [
            InlineKeyboardButton(
                text='🗑️ Remove Route',
                callback_data=f"sources:remove_route:{ctx.source_id}:{ctx.group_id}",
            ),
        ],
    ]
    if include_overview:
        rows.append([
            InlineKeyboardButton(text='🎛 Overview', callback_data=f"sources:route:{ctx.id}:overview"),
        ])
    rows.append([
        InlineKeyboardButton(text='◀ Routing', callback_data='sources:routing'),
        InlineKeyboardButton(text='⚙️ Source', callback_data=f"sources:source_details:{ctx.source_id}"),
    ])
    rows.append([
        InlineKeyboardButton(text='🏠 Main Menu', callback_data='menu:main'),
    ])
    return rows


def _debug_route_context(prefix: str, ctx: 'RouteContext') -> None:
    logger.info(
        "[ROUTING_UI] %s id=%s source_id=%s target_id=%s mode=%s enabled=%s "
        "chains=%s keywords=%d rewrites=%d summary=%s media=%s monitor=%s forward=%s",
        prefix,
        ctx.id,
        ctx.source_id,
        ctx.group_id,
        ctx.forwarding_mode,
        ctx.enabled,
        ctx.allowed_chains,
        len(ctx.keyword_filters),
        len(ctx.rewrite_rules),
        ctx.summary_enabled,
        ctx.media_enabled,
        ctx.monitor_bot_name,
        ctx.forward_bot_name,
    )



async def _edit_with_logging(query: types.CallbackQuery, text: str, keyboard: InlineKeyboardMarkup, context: str) -> None:
    """Safely edit the callback message while capturing diagnostics."""
    try:
        await query.message.edit_text(text, reply_markup=keyboard)
    except Exception as exc:
        logger.error("[ROUTING_UI] edit_text_failed context=%s chat_id=%s message_id=%s exc=%s", context, getattr(getattr(query.message, 'chat', None), 'id', None), getattr(query.message, 'message_id', None), exc, exc_info=True)
        raise

async def _store_view_state(state: Optional[FSMContext], route_id: int, message: types.Message, view: str) -> None:
    if not state:
        return
    data = {
        'route_id': route_id,
        'chat_id': message.chat.id,
        'message_id': message.message_id,
        'view': view,
    }
    await state.update_data(route_view=data)
    logger.info('[ROUTING_UI] stored_view route_id=%s view=%s chat_id=%s message_id=%s', route_id, view, message.chat.id if message and message.chat else None, message.message_id if message else None)


def _render_route_overview(ctx: RouteContext) -> str:
    status_badge = '🟢 Enabled' if ctx.enabled else '🔴 Disabled'
    mode_label = FORWARDING_MODE_LABELS.get(ctx.forwarding_mode, ctx.forwarding_mode.title())
    lines = [
        '<b>🎯 Route Overview</b>',
        '',
        status_badge,
        f"<b>{html_escape(ctx.source_name)}</b> → <b>{html_escape(ctx.group_name)}</b>",
        f"Route ID: <code>{ctx.id}</code>",
        '',
        f"<b>Forwarding Mode:</b> {mode_label}",
        FORWARDING_MODE_DESCRIPTIONS.get(ctx.forwarding_mode, ''),
    ]

    if ctx.forwarding_mode == 'tokens':
        lines.append(f"<b>Chains:</b> {_format_chain_badges(ctx.allowed_chains)}")
    elif ctx.forwarding_mode == 'keywords':
        if ctx.keyword_filters:
            keywords = ', '.join(f"<code>{html_escape(kw)}</code>" for kw in ctx.keyword_filters)
            lines.append(f"<b>Keywords:</b> {keywords}")
        else:
            lines.append("<b>Keywords:</b> <i>None configured</i>")

    if ctx.rewrite_rules:
        preview = []
        for rule in ctx.rewrite_rules[:3]:
            source_text = html_escape(rule['source'])
            target_text = html_escape(rule['target']) if rule['target'] else '(removed)'
            preview.append(f"• <code>{source_text}</code> → <code>{target_text}</code>")
        lines.append('')
        lines.append('<b>Text Replacements:</b>')
        lines.extend(preview)
        if len(ctx.rewrite_rules) > 3:
            lines.append(f"• … ({len(ctx.rewrite_rules) - 3} more)")
    else:
        lines.append('')
        lines.append('<b>Text Replacements:</b> <i>None configured</i>')

    summary_badge = '🧾 Summary replies are enabled.' if ctx.summary_enabled else 'Summary replies are disabled.'
    lines.append('')
    lines.append(summary_badge)
    media_badge = '📸 Media attachments forward with messages.' if ctx.media_enabled else '🚫 Media attachments are skipped.'
    lines.append(media_badge)

    monitor_label = ctx.monitor_bot_name or 'Not set'
    forward_label = ctx.forward_bot_name or 'Not set'
    lines.append('')
    lines.append(f"👁️ Monitor Bot: {html_escape(monitor_label)}")
    lines.append(f"📤 Forward Bot: {html_escape(forward_label)}")

    return '\n'.join(line for line in lines if line is not None)


def _overview_keyboard(ctx: RouteContext) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    rows.append(_mode_button_row(ctx))
    rows.extend(_shared_route_rows(ctx, include_overview=False))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _render_keywords_view(ctx: RouteContext) -> tuple[str, InlineKeyboardMarkup]:
    lines = ['<b>📝 Keyword Filters</b>', '']
    if ctx.keyword_filters:
        for idx, keyword in enumerate(ctx.keyword_filters, 1):
            lines.append(f"{idx}. <code>{html_escape(keyword)}</code>")
    else:
        lines.append('<i>No keywords configured.</i>')
    lines.append('')
    lines.append('Messages forward when at least one keyword appears in the text (case-insensitive).')

    buttons: List[List[InlineKeyboardButton]] = []
    buttons.append(_mode_button_row(ctx))
    buttons.append([InlineKeyboardButton(text='➕ Add Keywords', callback_data=f"sources:route:{ctx.id}:keywords:add")])

    for index, keyword in enumerate(ctx.keyword_filters):
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {keyword}",
                callback_data=f"sources:route:{ctx.id}:keywords:remove:{index}",
            ),
        ])

    if ctx.keyword_filters:
        buttons.append([
            InlineKeyboardButton(text='🧹 Clear All', callback_data=f"sources:route:{ctx.id}:keywords:clear")
        ])

    buttons.extend(_shared_route_rows(ctx, include_overview=True))

    return '\n'.join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def _render_rewrites_view(ctx: RouteContext) -> tuple[str, InlineKeyboardMarkup]:
    lines = ['<b>🔁 Text Replacements</b>', '']
    if ctx.rewrite_rules:
        for idx, rule in enumerate(ctx.rewrite_rules, 1):
            source_text = html_escape(rule['source'])
            target_text = html_escape(rule['target']) if rule['target'] else '(removed)'
            lines.append(f"{idx}. <code>{source_text}</code> → <code>{target_text}</code>")
    else:
        lines.append('<i>No replacements configured.</i>')
    lines.append('')
    lines.append('Replacements run before forwarding. Leave the right side empty to remove the text entirely.')

    buttons: List[List[InlineKeyboardButton]] = []
    buttons.append(_mode_button_row(ctx))
    buttons.append([InlineKeyboardButton(text='➕ Add Replacement', callback_data=f"sources:route:{ctx.id}:rewrites:add")])

    for index, rule in enumerate(ctx.rewrite_rules):
        preview = rule['source']
        if len(preview) > 18:
            preview = preview[:17] + '…'
        buttons.append([
            InlineKeyboardButton(
                text=f"❌ {preview}",
                callback_data=f"sources:route:{ctx.id}:rewrites:remove:{index}",
            ),
        ])

    if ctx.rewrite_rules:
        buttons.append([
            InlineKeyboardButton(text='🧹 Clear All', callback_data=f"sources:route:{ctx.id}:rewrites:clear")
        ])

    buttons.extend(_shared_route_rows(ctx, include_overview=True))

    return '\n'.join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


def _render_chain_view(ctx: RouteContext) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        '<b>⛓️ Allowed Blockchains</b>',
        '',
        'Select the chains that should forward token calls for this route. At least one chain must be active.',
        '',
        f"Current selection: {_format_chain_badges(ctx.allowed_chains)}",
        '',
        'Use the forwarding chips and navigation buttons below to switch modes or adjust other filters.',
    ]

    buttons: List[List[InlineKeyboardButton]] = []
    buttons.append(_mode_button_row(ctx))
    for chain_code, chain_label in CHAIN_BADGES.items():
        selected = chain_code in ctx.allowed_chains
        prefix = '✅' if selected else '☐'
        buttons.append([
            InlineKeyboardButton(
                text=f"{prefix} {chain_label}",
                callback_data=f"sources:route:{ctx.id}:chains:toggle:{chain_code}",
            )
        ])

    buttons.extend(_shared_route_rows(ctx, include_overview=True))

    return '\n'.join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


async def _load_route_context(service, route_id: int) -> RouteContext:
    row = await service.db.fetchrow(
        """
        SELECT
            rr.*,
            s.source_chat_id AS src_chat_id,
            COALESCE(s.display_name, s.title, s.name) AS source_label,
            g.tg_chat_id AS grp_chat_id,
            COALESCE(g.display_name, g.title) AS group_label,
            COALESCE(mb.display_name, mb.session_name) AS monitor_label,
            COALESCE(fb.display_name, fb.session_name) AS forward_label
        FROM routing_rules rr
        JOIN source_chats s ON s.id = rr.source_chat_id
        JOIN groups g ON g.id = rr.target_group_id
        LEFT JOIN bots mb ON mb.id = rr.monitoring_userbot_id
        LEFT JOIN bots fb ON fb.id = rr.forwarding_userbot_id
        WHERE rr.id = $1
        """,
        route_id,
    )
    if not row:
        raise ValueError("Route not found")

    allowed_chains = [chain.upper() for chain in _json_list(row.get('allowed_chains'), ['SOL'])]
    if not allowed_chains:
        allowed_chains = ['SOL']

    keyword_filters = [kw.strip().lower() for kw in _json_list(row.get('keyword_filters'), []) if kw]
    rewrite_rules = _parse_rewrite_rules(row.get('forward_rewrite_rules'))

    ctx = RouteContext(
        id=row['id'],
        source_id=row['source_chat_id'],
        source_chat_id=row['src_chat_id'],
        source_name=row.get('source_label') or f"Source {row['src_chat_id']}",
        group_id=row['target_group_id'],
        group_chat_id=row['grp_chat_id'],
        group_name=row.get('group_label') or f"Chat {row['grp_chat_id']}",
        enabled=bool(row.get('enabled', True)),
        forwarding_mode=(row.get('forwarding_mode') or 'tokens').lower(),
        allowed_chains=allowed_chains,
        keyword_filters=keyword_filters,
        rewrite_rules=rewrite_rules,
        media_enabled=bool(row.get('forward_media', True)),
        summary_enabled=bool(row.get('forward_summary')), 
        monitor_bot_id=row.get('monitoring_userbot_id'),
        monitor_bot_name=row.get('monitor_label'),
        forward_bot_id=row.get('forwarding_userbot_id'),
        forward_bot_name=row.get('forward_label'),
    )
    _debug_route_context("load_context", ctx)
    return ctx


async def show_route_filters(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    """Display a concise overview of the route configuration."""
    message = getattr(query, 'message', None)
    chat_id = getattr(getattr(message, 'chat', None), 'id', None)
    message_id = getattr(message, 'message_id', None)
    logger.info('[ROUTING_UI] show_route_filters route_id=%s callback=%s chat_id=%s message_id=%s', route_id, query.data, chat_id, message_id)
    try:
        ctx = await _load_route_context(service, route_id)
    except ValueError:
        logger.warning('[ROUTING_UI] Route %s not found during overview load', route_id)
        await query.answer('❌ Route not found', show_alert=True)
        return
    except Exception as exc:  # pragma: no cover - defensive
        logger.error('Failed to load route context: %s', exc, exc_info=True)
        await query.answer('❌ Failed to load route', show_alert=True)
        return

    _debug_route_context('overview', ctx)
    text = _render_route_overview(ctx)
    keyboard = _overview_keyboard(ctx)
    await _edit_with_logging(query, text, keyboard, 'overview')
    await _store_view_state(state, route_id, query.message, 'overview')
    await query.answer()


async def set_route_forwarding_mode(service, query: types.CallbackQuery, route_id: int, mode: str, state: FSMContext):
    """Update the forwarding mode for the route and refresh the overview."""
    logger.info('[ROUTING_UI] set_route_forwarding_mode route_id=%s mode=%s', route_id, mode)
    try:
        ctx = await _load_route_context(service, route_id)
        await service.source_model.update_routing_rule_forwarding(route_id, mode, ctx.keyword_filters)
        await query.answer('✅ Forwarding mode updated')
        await show_route_filters(service, query, route_id, state)
    except ValueError as validation_error:
        await query.answer(f"❌ {validation_error}", show_alert=True)
    except Exception as exc:
        logger.error('Error updating forwarding mode: %s', exc, exc_info=True)
        await query.answer('❌ Failed to update mode', show_alert=True)


async def show_route_chain_editor(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    """Present the chain selector UI."""
    try:
        ctx = await _load_route_context(service, route_id)
    except ValueError:
        logger.warning('[ROUTING_UI] Chain editor route %s not found', route_id)
        await query.answer('❌ Route not found', show_alert=True)
        return
    _debug_route_context('chain_editor', ctx)
    text, keyboard = _render_chain_view(ctx)
    try:
        await query.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as exc:
        if 'message is not modified' in str(exc):
            await query.answer()
            return
        raise
    await _store_view_state(state, route_id, query.message, 'chains')
    await query.answer()


async def toggle_route_chain(service, query: types.CallbackQuery, route_id: int, chain: str, state: FSMContext):
    """Toggle a blockchain entry for the route."""
    logger.info('[ROUTING_UI] toggle_route_chain route_id=%s chain=%s', route_id, chain)
    try:
        ctx = await _load_route_context(service, route_id)
        chain = chain.upper()
        new_chains = list(ctx.allowed_chains)
        if chain in new_chains:
            if len(new_chains) == 1:
                await query.answer('⚠️ At least one chain is required', show_alert=True)
                return
            new_chains.remove(chain)
        else:
            new_chains.append(chain)
        logger.info('[ROUTING_UI] toggle_result route_id=%s chains=%s', route_id, new_chains)
        await service.source_model.update_routing_rule_chains(route_id, new_chains)
        await query.answer('✅ Chains updated')
        await show_route_chain_editor(service, query, route_id, state)
    except Exception as exc:
        logger.error('Failed to toggle chain: %s', exc, exc_info=True)
        await query.answer('❌ Failed to update chains', show_alert=True)


async def show_route_keywords_editor(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    try:
        ctx = await _load_route_context(service, route_id)
    except ValueError:
        logger.warning('[ROUTING_UI] Keyword editor route %s not found', route_id)
        await query.answer('❌ Route not found', show_alert=True)
        return
    _debug_route_context('keyword_editor', ctx)
    text, keyboard = _render_keywords_view(ctx)
    await query.message.edit_text(text, reply_markup=keyboard)
    await _store_view_state(state, route_id, query.message, 'keywords')
    await query.answer()


async def prompt_route_keywords(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    logger.info('[ROUTING_UI] prompt_route_keywords route_id=%s', route_id)
    instruction = textwrap.dedent(
        """
        <b>➕ Add Keyword Filters</b>

        Send keywords separated by commas or new lines. Example:
        <code>alpha
        pump
        launch</code>

        Type <code>cancel</code> to abort.
        """
    ).strip()

    await query.message.edit_text(
        instruction,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text='◀ Back', callback_data=f"sources:route:{route_id}:keywords")]]
        ),
    )
    if state:
        await _store_view_state(state, route_id, query.message, 'keywords_input')
        await state.set_state(ManagementStates.route_keywords_input)
        await state.update_data(route_input_context={'route_id': route_id, 'return_view': 'keywords'})
    await query.answer()


async def _refresh_view_with_bot(service, bot, route_id: int, chat_id: int, message_id: int, view: str) -> str:
    logger.info('[ROUTING_UI] refresh_view route_id=%s view=%s chat_id=%s message_id=%s', route_id, view, chat_id, message_id)
    ctx = await _load_route_context(service, route_id)
    if view in {'keywords', 'keywords_input'}:
        text, keyboard = _render_keywords_view(ctx)
        view = 'keywords'
    elif view in {'rewrites', 'rewrites_input'}:
        text, keyboard = _render_rewrites_view(ctx)
        view = 'rewrites'
    else:
        text = _render_route_overview(ctx)
        keyboard = _overview_keyboard(ctx)
        view = 'overview'
    await bot.edit_message_text(text=text, chat_id=chat_id, message_id=message_id, reply_markup=keyboard)
    return view


async def process_route_keywords_input(service, message: types.Message, state: FSMContext):
    if not state:
        await message.answer('❌ Unexpected state. Reopen the keyword editor.')
        return

    data = await state.get_data()
    context = data.get('route_input_context') or {}
    view_ctx = data.get('route_view') or {}
    route_id = context.get('route_id')

    if not route_id:
        await message.answer('❌ Session expired. Reopen the keyword editor.')
        await state.clear()
        return

    user_input = (message.text or '').strip()
    target_view = context.get('return_view', 'overview')
    chat_id = view_ctx.get('chat_id')
    message_id = view_ctx.get('message_id')

    if user_input.lower() == 'cancel':
        logger.info('[ROUTING_UI] keyword edit cancelled route_id=%s', route_id)
        await message.answer('❌ Keyword update cancelled.')
        await state.clear()
        if chat_id and message_id:
            new_view = await _refresh_view_with_bot(service, message.bot, route_id, chat_id, message_id, target_view)
            await state.update_data(route_view={
                'route_id': route_id,
                'chat_id': chat_id,
                'message_id': message_id,
                'view': new_view,
            })
        return

    keywords: List[str] = []
    for line in user_input.splitlines():
        for part in line.split(','):
            cleaned = part.strip()
            if cleaned:
                keywords.append(cleaned)

    if not keywords:
        await message.answer('⚠️ Please provide at least one keyword or type cancel.')
        return

    logger.info('[ROUTING_UI] keyword edit applied route_id=%s keywords=%s', route_id, keywords)
    await service.source_model.set_routing_rule_keywords(route_id, keywords)
    await message.answer('✅ Keywords updated.')
    await state.clear()
    if chat_id and message_id:
        new_view = await _refresh_view_with_bot(service, message.bot, route_id, chat_id, message_id, 'keywords')
        await state.update_data(route_view={
            'route_id': route_id,
            'chat_id': chat_id,
            'message_id': message_id,
            'view': new_view,
        })
async def remove_route_keyword(service, query: types.CallbackQuery, route_id: int, index: int, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] remove_keyword route_id=%s index=%s', route_id, index)
        await service.source_model.remove_routing_rule_keyword(route_id, index)
        await query.answer('✅ Keyword removed')
        await show_route_keywords_editor(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error removing keyword: %s', exc, exc_info=True)
        await query.answer('❌ Failed to remove keyword', show_alert=True)


async def clear_route_keywords(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] clear_keywords route_id=%s', route_id)
        await service.source_model.set_routing_rule_keywords(route_id, [])
        await query.answer('✅ Keywords cleared')
        await show_route_keywords_editor(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error clearing keywords: %s', exc, exc_info=True)
        await query.answer('❌ Failed to clear keywords', show_alert=True)


async def show_route_rewrite_editor(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    try:
        ctx = await _load_route_context(service, route_id)
    except ValueError:
        logger.warning('[ROUTING_UI] Rewrite editor route %s not found', route_id)
        await query.answer('❌ Route not found', show_alert=True)
        return
    _debug_route_context('rewrite_editor', ctx)
    text, keyboard = _render_rewrites_view(ctx)
    await query.message.edit_text(text, reply_markup=keyboard)
    await _store_view_state(state, route_id, query.message, 'rewrites')
    await query.answer()


async def prompt_route_rewrites(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    logger.info('[ROUTING_UI] prompt_route_rewrites route_id=%s', route_id)
    instruction = textwrap.dedent(
        """
        <b>➕ Add Text Replacements</b>

        Send each replacement on a new line using <code>source => target</code>.
        Example:
        <code>@old_channel => @new_channel
        spam => </code>

        Type <code>cancel</code> to abort.
        """
    ).strip()

    await query.message.edit_text(
        instruction,
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text='◀ Back', callback_data=f"sources:route:{route_id}:rewrites")]]
        ),
    )
    if state:
        await _store_view_state(state, route_id, query.message, 'rewrites_input')
        await state.set_state(ManagementStates.route_rewrite_input)
        await state.update_data(route_input_context={'route_id': route_id, 'return_view': 'rewrites'})
    await query.answer()


async def process_route_rewrite_input(service, message: types.Message, state: FSMContext):
    if not state:
        await message.answer('❌ Unexpected state. Reopen the rewrite editor.')
        return

    data = await state.get_data()
    context = data.get('route_input_context') or {}
    view_ctx = data.get('route_view') or {}
    route_id = context.get('route_id')

    if not route_id:
        await message.answer('❌ Session expired. Reopen the rewrite editor.')
        await state.clear()
        return

    user_input = (message.text or '').strip()
    target_view = context.get('return_view', 'overview')
    chat_id = view_ctx.get('chat_id')
    message_id = view_ctx.get('message_id')

    if user_input.lower() == 'cancel':
        logger.info('[ROUTING_UI] rewrite edit cancelled route_id=%s', route_id)
        await message.answer('❌ Rewrite update cancelled.')
        await state.clear()
        if chat_id and message_id:
            new_view = await _refresh_view_with_bot(service, message.bot, route_id, chat_id, message_id, target_view)
            await state.update_data(route_view={
                'route_id': route_id,
                'chat_id': chat_id,
                'message_id': message_id,
                'view': new_view,
            })
        return

    rewrite_rules: List[Dict[str, str]] = []
    for line in user_input.splitlines():
        if '=>' in line:
            source_text, target_text = line.split('=>', 1)
        elif '->' in line:
            source_text, target_text = line.split('->', 1)
        else:
            source_text, target_text = line, ''
        source_text = source_text.strip()
        target_text = target_text.strip()
        if source_text:
            rewrite_rules.append({'source': source_text, 'target': target_text})

    if not rewrite_rules:
        await message.answer('⚠️ Provide at least one valid replacement or type cancel.')
        return

    logger.info('[ROUTING_UI] rewrite edit applied route_id=%s rules=%s', route_id, rewrite_rules)
    await service.source_model.set_routing_rule_rewrites(route_id, rewrite_rules)
    await message.answer('✅ Replacements updated.')
    await state.clear()
    if chat_id and message_id:
        new_view = await _refresh_view_with_bot(service, message.bot, route_id, chat_id, message_id, 'rewrites')
        await state.update_data(route_view={
            'route_id': route_id,
            'chat_id': chat_id,
            'message_id': message_id,
            'view': new_view,
        })
async def remove_route_rewrite(service, query: types.CallbackQuery, route_id: int, index: int, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] remove_rewrite route_id=%s index=%s', route_id, index)
        await service.source_model.remove_routing_rule_rewrite(route_id, index)
        await query.answer('✅ Replacement removed')
        await show_route_rewrite_editor(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error removing rewrite: %s', exc, exc_info=True)
        await query.answer('❌ Failed to remove replacement', show_alert=True)


async def clear_route_rewrites(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] clear_rewrites route_id=%s', route_id)
        await service.source_model.set_routing_rule_rewrites(route_id, [])
        await query.answer('✅ Replacements cleared')
        await show_route_rewrite_editor(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error clearing replacements: %s', exc, exc_info=True)
        await query.answer('❌ Failed to clear replacements', show_alert=True)


async def toggle_route_summary(service, query: types.CallbackQuery, route_id: int, enabled: bool, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] toggle_summary route_id=%s enabled=%s', route_id, enabled)
        await service.source_model.set_routing_rule_summary(route_id, enabled)
        await query.answer('✅ Summary updated')
        await show_route_filters(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error toggling summary: %s', exc, exc_info=True)
        await query.answer('❌ Failed to update summary', show_alert=True)


async def toggle_route_media(service, query: types.CallbackQuery, route_id: int, enabled: bool, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] toggle_media route_id=%s enabled=%s', route_id, enabled)
        await service.source_model.set_routing_rule_media(route_id, enabled)
        await query.answer('✅ Media forwarding updated')
        await show_route_filters(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error toggling media forwarding: %s', exc, exc_info=True)
        await query.answer('❌ Failed to update media setting', show_alert=True)


async def toggle_route_enabled(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    try:
        logger.info('[ROUTING_UI] toggle_route_enabled route_id=%s', route_id)
        await service.db.execute('UPDATE routing_rules SET enabled = NOT enabled WHERE id = $1', route_id)
        await query.answer('✅ Route status updated')
        await show_route_filters(service, query, route_id, state)
    except Exception as exc:
        logger.error('Error toggling route: %s', exc, exc_info=True)
        await query.answer('❌ Failed to toggle route', show_alert=True)


async def show_route_blockchain_editor(service, query: types.CallbackQuery, route_id: int, state: FSMContext):
    await show_route_chain_editor(service, query, route_id, state)
