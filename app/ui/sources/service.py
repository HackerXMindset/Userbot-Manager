from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging
import time
import json
from typing import Optional, List

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import GroupModel
from app.models.source_chat import SourceChatModel
from app.ui.sources import blockchain, detail, menu, routing, selection, users

logger = logging.getLogger(__name__)

class SourceService:
    """Handler for source chat management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
        self.source_model = SourceChatModel(db)
        self.cache = {}
        self.cache_time = {}
    
    def is_fresh(self, key, seconds=300):
        """Check if cache entry is fresh (default 5 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    async def get_cached_sources(self):
        """Get sources with caching"""
        if self.is_fresh("sources"):
            return self.cache["sources"]
        
        sources = await self.source_model.get_all_sources()
        self.cache["sources"] = sources
        self.cache_time["sources"] = time.time()
        return sources
    
    async def get_cached_groups(self):
        """Get groups with caching"""
        if self.is_fresh("groups"):
            return self.cache["groups"]
        
        groups = await self.group_model.get_groups_with_stats()
        self.cache["groups"] = groups
        self.cache_time["groups"] = time.time()
        return groups
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_time.clear()

    async def handle_source_group_selection(self, query: types.CallbackQuery, state: FSMContext):
        return await selection.handle_source_group_selection(self, query, state)

    async def handle_source_type_selection(self, query: types.CallbackQuery, state: FSMContext):
        return await selection.handle_source_type_selection(self, query, state)

    async def handle_global_source_type_selection(self, query: types.CallbackQuery, state: FSMContext):
        return await selection.handle_global_source_type_selection(self, query, state)

    async def handle_source_edit(self, query: types.CallbackQuery):
        return await selection.handle_source_edit(self, query)

    async def show_sources_menu(self, query: types.CallbackQuery):
        return await menu.show_sources_menu(self, query)

    async def handle_sources_action(self, query: types.CallbackQuery, state: FSMContext = None):
        """Handle sources actions"""
        logger.debug(f"handle_sources_action received callback: {query.data}")
        parts = query.data.split(':')

        # Handle routing blockchain editing
        if parts[0] == 'routing':
            logger.info(f"[BLOCKCHAIN_DEBUG] Routing callback received: {query.data}")
            logger.info(f"[BLOCKCHAIN_DEBUG] Parts split: {parts}")
            try:
                action = parts[1]
                logger.info(f"[BLOCKCHAIN_DEBUG] Action: {action}")

                if action == 'edit_chains':
                    rule_id = int(parts[2])
                    logger.info(f"[BLOCKCHAIN_DEBUG] edit_chains - rule_id={rule_id}")
                    await self.show_blockchain_selector(query, rule_id, state=state)

                elif action == 'blockchain':
                    logger.info(f"[BLOCKCHAIN_DEBUG] blockchain action - parts[2]={parts[2]}")
                    if parts[2].startswith('toggle_'):
                        chain = parts[2].split('_')[1].upper()  # toggle_sol -> SOL
                        rule_id = int(parts[3]) if parts[3] != 'new' else None
                        logger.info(f"[BLOCKCHAIN_DEBUG] toggle - chain={chain}, rule_id={rule_id}")
                        if rule_id:
                            await self.toggle_blockchain(query, rule_id, chain, state=state)
                        else:
                            logger.warning(f"[BLOCKCHAIN_DEBUG] rule_id is None, cannot toggle")
                    else:
                        logger.warning(f"[BLOCKCHAIN_DEBUG] parts[2] does not start with 'toggle_': {parts[2]}")

                elif action == 'blockchain_confirm':
                    rule_id = int(parts[2]) if parts[2] != 'new' else None
                    logger.info(f"[BLOCKCHAIN_DEBUG] blockchain_confirm - rule_id={rule_id}")
                    if rule_id:
                        await self.confirm_blockchain_selection(query, rule_id, state=state)
                    else:
                        logger.warning(f"[BLOCKCHAIN_DEBUG] rule_id is None, cannot confirm")

                elif action == 'view':
                    # Back button from blockchain selector
                    rule_id = int(parts[2])
                    if state:
                        data = await state.get_data()
                        return_route_id = data.get('route_filters_return')
                        if return_route_id == rule_id:
                            logger.info(f"[BLOCKCHAIN_DEBUG] view - returning to filters for rule {rule_id}")
                            await state.update_data(route_filters_return=None)
                            await self.show_route_filters(query, rule_id, state)
                            return

                    logger.info(f"[BLOCKCHAIN_DEBUG] view - redirecting to source details for rule {rule_id}")
                    rule = await self.db.fetchrow("SELECT source_chat_id FROM routing_rules WHERE id = $1", rule_id)
                    if rule:
                        await self.show_source_details(query, rule['source_chat_id'])
                    else:
                        await query.answer("❌ Rule not found")

                else:
                    logger.warning(f"[BLOCKCHAIN_DEBUG] Unknown routing action: {action}")

            except Exception as e:
                logger.error(f"[BLOCKCHAIN_DEBUG] ❌ ERROR in routing handler: {e}", exc_info=True)
                await query.answer(f"❌ Error: {str(e)}", show_alert=True)
            return

        # Handle pagination for manage_global
        if parts[0] == 'sources_manage_page':
            if parts[1] == 'page':
                page = int(parts[2])
                await self.show_manage_global_sources(query, page=page)
            return

        # Handle pagination for add_route
        if parts[0] == 'add_route_page':
            logger.debug(f"Handling 'add_route_page' pagination. Parts: {parts}")
            try:
                source_id = int(parts[1])
                if parts[2] == 'page':
                    if len(parts) > 3 and parts[3].isdigit():
                        page = int(parts[3])
                        logger.debug(f"Calling show_add_route_menu for source {source_id}, page {page}")
                        await self.show_add_route_menu(query, source_id, page=page)
                    else:
                        logger.debug("Pagination info button clicked. Doing nothing.")
                        await query.answer()
                else:
                    logger.warning(f"Unknown 'add_route_page' action: {parts}")
            except Exception as e:
                logger.error(f"Error in 'add_route_page' handler: {e}", exc_info=True)
                await query.answer("❌ Error processing page change.")
            return

        action = parts[1]
        if action == 'route':
            try:
                route_id = int(parts[2])
            except (IndexError, ValueError):
                logger.warning('[ROUTING_UI] Invalid route reference user=%s data=%s', query.from_user.id if query.from_user else None, query.data)
                await query.answer("❌ Invalid route reference", show_alert=True)
                return

            subaction = parts[3] if len(parts) > 3 else 'overview'
            logger.info('[ROUTING_UI] route_action route_id=%s subaction=%s data=%s', route_id, subaction, query.data)

            if subaction == 'overview':
                await self.open_route_filters(query, route_id, state)
            elif subaction == 'toggle':
                await routing.toggle_route_enabled(self, query, route_id, state)
            elif subaction == 'chains':
                if len(parts) > 4 and parts[4] == 'toggle' and len(parts) > 5:
                    await routing.toggle_route_chain(self, query, route_id, parts[5], state)
                else:
                    await routing.show_route_chain_editor(self, query, route_id, state)
            elif subaction == 'keywords':
                if len(parts) > 4:
                    action_tail = parts[4]
                    if action_tail == 'add':
                        await routing.prompt_route_keywords(self, query, route_id, state)
                    elif action_tail == 'remove' and len(parts) > 5:
                        await routing.remove_route_keyword(self, query, route_id, int(parts[5]), state)
                    elif action_tail == 'clear':
                        await routing.clear_route_keywords(self, query, route_id, state)
                    else:
                        await routing.show_route_keywords_editor(self, query, route_id, state)
                else:
                    await routing.show_route_keywords_editor(self, query, route_id, state)
            elif subaction == 'rewrites':
                if len(parts) > 4:
                    action_tail = parts[4]
                    if action_tail == 'add':
                        await routing.prompt_route_rewrites(self, query, route_id, state)
                    elif action_tail == 'remove' and len(parts) > 5:
                        await routing.remove_route_rewrite(self, query, route_id, int(parts[5]), state)
                    elif action_tail == 'clear':
                        await routing.clear_route_rewrites(self, query, route_id, state)
                    else:
                        await routing.show_route_rewrite_editor(self, query, route_id, state)
                else:
                    await routing.show_route_rewrite_editor(self, query, route_id, state)
            elif subaction == 'summary' and len(parts) > 4:
                await routing.toggle_route_summary(self, query, route_id, parts[4] == '1', state)
            elif subaction == 'media' and len(parts) > 4:
                await routing.toggle_route_media(self, query, route_id, parts[4] == '1', state)
            else:
                await self.open_route_filters(query, route_id, state)
            # Legacy handlers kept for backwards compatibility
            return
        elif action == 'assign_route_bots':
            source_id, group_id = int(parts[2]), int(parts[3])
            await self.show_userbot_selection(query, source_id, group_id)
            return
        
        if action == 'add_global':
            await self.start_add_global_source(query, state)
        elif action == 'manage_global':
            await self.show_manage_global_sources(query, page=1)
        elif action == 'routing':
            # Handle pagination format: sources:routing:page:2
            if len(parts) > 2 and parts[2] == 'page':
                page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
            else:
                # Handle direct format: sources:routing:2 (backward compat)
                page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
            await self.show_routing_menu(query, page=page)
        elif action == 'source_details':
            source_id = int(parts[2])
            await self.show_source_details(query, source_id)
        elif action == 'add_route':
            source_id = int(parts[2])
            await self.show_add_route_menu(query, source_id, page=1)
        elif action == 'create_route':
            source_id, group_id = int(parts[2]), int(parts[3])
            await self.show_userbot_selection(query, source_id, group_id)
        elif action == 'route_filters':
            route_id = int(parts[2])
            await self.open_route_filters(query, route_id, state)
        elif action == 'set_route_mode':
            route_id = int(parts[2])
            mode = parts[3]
            await self.set_route_forwarding_mode(query, route_id, mode, state)
        elif action == 'route_keywords_prompt':
            route_id = int(parts[2])
            await self.prompt_route_keywords(query, route_id, state)
        elif action == 'route_keywords_remove':
            route_id, index = int(parts[2]), int(parts[3])
            await self.remove_route_keyword(query, route_id, index, state)
        elif action == 'route_keywords_clear':
            route_id = int(parts[2])
            await self.clear_route_keywords(query, route_id, state)
        elif action == 'route_filter_chains':
            route_id = int(parts[2])
            await self.show_route_blockchain_editor(query, route_id, state)
        elif action == 'route_summary_toggle':
            route_id = int(parts[2])
            enabled_flag = parts[3]
            await self.toggle_route_summary(query, route_id, enabled_flag == '1', state)
        elif action == 'route_media_toggle':
            route_id = int(parts[2])
            enabled_flag = parts[3]
            await self.toggle_route_media(query, route_id, enabled_flag == '1', state)
        # Legacy handlers kept for backwards compatibility
        elif action == 'route_rewrite_prompt':
            route_id = int(parts[2])
            await self.prompt_route_rewrites(query, route_id, state)
        elif action == 'route_rewrite_remove':
            route_id, index = int(parts[2]), int(parts[3])
            await self.remove_route_rewrite(query, route_id, index, state)
        elif action == 'route_rewrite_clear':
            route_id = int(parts[2])
            await self.clear_route_rewrites(query, route_id, state)
        elif action == 'select_role':
            source_id, group_id, role, monitor_bot_id, forward_bot_id = int(parts[2]), int(parts[3]), parts[4], int(parts[5]), int(parts[6])
            await self.show_bot_picker(query, source_id, group_id, role, monitor_bot_id, forward_bot_id)
        elif action == 'route_filters':
            route_id = int(parts[2])
            await self.open_route_filters(query, route_id, state)
        elif action == 'set_bot':
            source_id, group_id, monitor_bot_id, forward_bot_id = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
            await self.show_userbot_selection(query, source_id, group_id, monitor_bot_id if monitor_bot_id != 0 else None, forward_bot_id if forward_bot_id != 0 else None)
        elif action == 'auto_assign':
            source_id, group_id = int(parts[2]), int(parts[3])
            await self.handle_auto_assign(query, source_id, group_id)
        elif action == 'finalize_route':
            source_id, group_id, monitoring_id, forwarding_id = int(parts[2]), int(parts[3]), parts[4], parts[5]
            monitoring_userbot_id = int(monitoring_id) if monitoring_id != 'None' else None
            forwarding_userbot_id = int(forwarding_id) if forwarding_id != 'None' else None
            await self.create_routing_rule(query, source_id, group_id, monitoring_userbot_id, forwarding_userbot_id)
        elif action == 'remove_route':
            source_id, group_id = int(parts[2]), int(parts[3])
            await self.remove_routing_rule(query, source_id, group_id)
        elif action == 'toggle':
            source_id = int(parts[2])
            await self.toggle_source(query, source_id)
        elif action == 'users':
            source_id = int(parts[2])
            await self.manage_source_users(query, source_id)
        elif action == 'add_user':
            source_id = int(parts[2])
            await self.start_add_user(query, source_id, state)
        elif action == 'remove_user':
            source_id, user_id = int(parts[2]), int(parts[3])
            await self.remove_user_from_source(query, source_id, user_id)
        elif action == 'delete':
            source_id = int(parts[2])
            await self.delete_source(query, source_id)
        elif action == 'confirm_delete':
            source_id = int(parts[2])
            await self.confirm_delete_source(query, source_id)
        elif action == 'set_name':
            source_id = int(parts[2])
            await self.start_set_source_name(query, source_id, state)
        elif action == 'clear_cache':
            self.clear_cache()
            await query.answer("✅ Cache cleared!")
            await self.show_sources_menu(query)
        elif action == 'set_monitor':
            source_id = int(parts[2])
            await self.show_monitor_bot_selection(query, source_id)
        elif action == 'set_forward':
            source_id = int(parts[2])
            await self.show_forward_bot_selection(query, source_id)
        elif action == 'clear_bots':
            source_id = int(parts[2])
            await self.clear_source_bots(query, source_id)
        elif action == 'select_monitor_bot':
            source_id, bot_id = int(parts[2]), int(parts[3])
            await self.set_monitor_bot(query, source_id, bot_id)
        elif action == 'select_forward_bot':
            source_id, bot_id = int(parts[2]), int(parts[3])
            await self.set_forward_bot(query, source_id, bot_id)
        else:
            await self.show_sources_menu(query)
    
    async def start_add_global_source(self, query: types.CallbackQuery, state: FSMContext):
        """Start adding a global source - show type selection"""
        return await detail.start_add_global_source(self, query, state)
    
    async def show_manage_global_sources(self, query: types.CallbackQuery, page: int = 1):
        return await menu.show_manage_global_sources(self, query, page)

    async def show_routing_menu(self, query: types.CallbackQuery, page: int = 1):
        return await menu.show_routing_menu(self, query, page)
    
    async def show_source_details(self, query: types.CallbackQuery, source_id: int):
        """Show detailed source information and routing management"""
        return await detail.show_source_details(self, query, source_id)
    
    async def show_add_route_menu(self, query: types.CallbackQuery, source_id: int, page: int = 1):
        """Show available groups to route to with pagination."""
        return await routing.show_add_route_menu(self, query, source_id, page=page)

    async def show_userbot_selection(self, query: types.CallbackQuery, source_id: int, group_id: int, monitor_bot_id: Optional[int] = None, forward_bot_id: Optional[int] = None):
        """Show userbot assignment UI for a route."""
        return await routing.show_userbot_selection(self, query, source_id, group_id, monitor_bot_id, forward_bot_id)

    async def show_route_filters(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Display forwarding filters for a routing rule."""
        return await routing.show_route_filters(self, query, route_id, state)

    async def open_route_filters(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Open the most relevant filter editor for a routing rule."""
        try:
            route = await self.db.fetchrow(
                """
                SELECT forwarding_mode,
                       allowed_chains,
                       keyword_filters
                FROM routing_rules
                WHERE id = $1
                """,
                route_id,
            )
            if not route:
                await query.answer("❌ Route not found", show_alert=True)
                return

            mode = (route.get('forwarding_mode') or 'tokens').lower()

            if mode == 'tokens':
                if state:
                    await state.update_data(route_filters_return=route_id)
                await self.show_route_blockchain_editor(query, route_id, state)
            elif mode == 'keywords':
                # Pass along keyword context to the editor so chips render correctly.
                await routing.show_route_keywords_editor(self, query, route_id, state)
            else:
                await self.show_route_filters(query, route_id, state)
        except Exception as exc:
            logger.error("[ROUTING_UI] open_route_filters_failed route_id=%s exc=%s", route_id, exc, exc_info=True)
            await query.answer("❌ Error opening filters", show_alert=True)

    async def set_route_forwarding_mode(self, query: types.CallbackQuery, route_id: int, mode: str, state: FSMContext):
        """Update forwarding mode for a routing rule."""
        return await routing.set_route_forwarding_mode(self, query, route_id, mode, state)

    async def prompt_route_keywords(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Prompt operator to enter keywords for a routing rule."""
        return await routing.prompt_route_keywords(self, query, route_id, state)

    async def prompt_route_rewrites(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Prompt operator to enter rewrite rules for a routing rule."""
        return await routing.prompt_route_rewrites(self, query, route_id, state)

    async def remove_route_keyword(self, query: types.CallbackQuery, route_id: int, index: int, state: FSMContext):
        """Remove a keyword from a routing rule."""
        return await routing.remove_route_keyword(self, query, route_id, index, state)

    async def clear_route_keywords(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Clear all keywords for a routing rule."""
        return await routing.clear_route_keywords(self, query, route_id, state)

    async def remove_route_rewrite(self, query: types.CallbackQuery, route_id: int, index: int, state: FSMContext):
        """Remove a rewrite rule from a routing rule."""
        return await routing.remove_route_rewrite(self, query, route_id, index, state)

    async def clear_route_rewrites(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Clear all rewrite rules for a routing rule."""
        return await routing.clear_route_rewrites(self, query, route_id, state)

    async def show_route_blockchain_editor(self, query: types.CallbackQuery, route_id: int, state: FSMContext):
        """Open blockchain selector for a routing rule returning to filters."""
        return await routing.show_route_blockchain_editor(self, query, route_id, state)

    async def process_route_keywords_input(self, message: types.Message, state: FSMContext):
        """Handle keyword list input from operator."""
        return await routing.process_route_keywords_input(self, message, state)

    async def process_route_rewrite_input(self, message: types.Message, state: FSMContext):
        """Handle rewrite rule input from operator."""
        return await routing.process_route_rewrite_input(self, message, state)

    async def toggle_route_summary(self, query: types.CallbackQuery, route_id: int, enabled: bool, state: FSMContext):
        """Toggle summary reply option for a routing rule."""
        return await routing.toggle_route_summary(self, query, route_id, enabled, state)

    async def toggle_route_media(self, query: types.CallbackQuery, route_id: int, enabled: bool, state: FSMContext):
        """Toggle media forwarding option for a routing rule."""
        return await routing.toggle_route_media(self, query, route_id, enabled, state)

    async def show_bot_picker(self, query: types.CallbackQuery, source_id: int, group_id: int, role: str, monitor_bot_id: int, forward_bot_id: int):
        """Show a list of userbots to choose for a role."""
        return await routing.show_bot_picker(self, query, source_id, group_id, role, monitor_bot_id, forward_bot_id)

    async def handle_auto_assign(self, query: types.CallbackQuery, source_id: int, group_id: int):
        """Handle auto-assignment of both monitoring and forwarding to first available userbot"""
        return await routing.handle_auto_assign(self, query, source_id, group_id)

    async def create_routing_rule(self, query: types.CallbackQuery, source_id: int, group_id: int,
                                 monitoring_userbot_id: int = None, forwarding_userbot_id: int = None):
        """Create a new routing rule with optional userbot assignments"""
        return await routing.create_routing_rule(
            self,
            query,
            source_id,
            group_id,
            monitoring_userbot_id,
            forwarding_userbot_id,
        )
    
    async def remove_routing_rule(self, query: types.CallbackQuery, source_id: int, group_id: int):
        """Remove a routing rule"""
        return await routing.remove_routing_rule(self, query, source_id, group_id)
    
    async def toggle_source(self, query: types.CallbackQuery, source_id: int):
        """Toggle source enabled/disabled status"""
        try:
            new_status = await self.source_model.toggle_enabled(source_id)
            
            # Clear cache since we modified source status
            self.clear_cache()
            
            status_text = "enabled" if new_status else "disabled"
            await query.answer(f"✅ Source {status_text}")
            
            # Refresh the source details view
            await self.show_source_details(query, source_id)
            
        except Exception as e:
            logger.error(f"Error toggling source: {e}")
            await query.answer("❌ Error toggling source status")
    
    async def start_add_user(self, query: types.CallbackQuery, source_id: int, state: FSMContext):
        """Start adding user to source"""
        return await users.start_add_user(self, query, source_id, state)
    
    async def start_add_source(self, query: types.CallbackQuery):
        """Start adding a source - select group"""
        return await detail.start_add_source(self, query)
    
    async def show_manage_sources(self, query: types.CallbackQuery):
        """Show source management - select group"""
        return await detail.show_manage_sources(self, query)
    
    async def show_group_sources(self, query: types.CallbackQuery, group_id: int):
        """Show sources for a specific group"""
        return await detail.show_group_sources(self, query, group_id)
    
    async def process_source_input(self, message: types.Message, state: FSMContext):
        """Process source chat ID input"""
        try:
            data = await state.get_data()
            source_type = data.get('source_type')
            group_id = data.get('group_id')  # Optional for global sources
            
            if not source_type:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return
            
            # Parse chat ID
            try:
                source_chat_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid chat ID. Please enter a valid number.")
                return
            
            # Validate ID format based on selected source type
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
            
            # Add source to database
            if group_id:
                # Old flow: group-specific source
                source = await self.source_model.add_source(
                    source_chat_id=source_chat_id,
                    source_type=source_type,
                    name=title,
                    title=title
                )
                # Create routing rule for the selected group
                await self.source_model.add_routing_rule(source['id'], group_id)
            else:
                # New flow: global source
                source = await self.source_model.add_source(
                    source_chat_id=source_chat_id,
                    source_type=source_type,
                    name=title,
                    title=title
                )
            
            # Clear cache since we added new source
            self.clear_cache()
            
            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            text = f"✅ <b>{type_emojis.get(source_type, '')} {source_type.title()} Source Added</b>\n\n"
            text += f"Chat/User ID: <code>{source_chat_id}</code>\n"
            text += f"Type: {source_type.title()}\n\n"
            
            keyboard_rows = []
            
            if group_id:
                # Old flow - source was added with routing to specific group
                if source_type == 'group':
                    text += "Since this is a group, you can configure which users are allowed to trigger forwards.\n"
                    keyboard_rows.append([
                        InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source['id']}")
                    ])
                elif source_type == 'channel':
                    text += "This channel will forward all token addresses posted."
                elif source_type == 'dm':
                    text += "This DM source will forward all token addresses from this user."
                
                keyboard_rows.extend([
                    [InlineKeyboardButton(text="📋 View Sources", callback_data=f"sources:select_group:{group_id}")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
                ])
            else:
                # New flow - global source added
                text += f"Source added to global pool!\n\n"
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
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await message.reply(text, reply_markup=keyboard)
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error processing source input: {e}")
            await message.reply("❌ Error adding source")
            await state.clear()
    
    async def _lookup_user_info(self, user_id: int) -> dict:
        """Lookup user information from Telegram using an available userbot session"""
        return await users._lookup_user_info(self, user_id)

    async def process_user_input(self, message: types.Message, state: FSMContext):
        """Process user ID input for source filtering"""
        return await users.process_user_input(self, message, state)
    
    async def manage_source_users(self, query: types.CallbackQuery, source_id: int):
        """Show user management for a source"""
        return await users.manage_source_users(self, query, source_id)
    
    async def remove_user_from_source(self, query: types.CallbackQuery, source_id: int, user_id: int):
        """Remove user from source"""
        return await users.remove_user_from_source(self, query, source_id, user_id)
    
    async def delete_source(self, query: types.CallbackQuery, source_id: int):
        """Show delete source confirmation"""
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            if not source:
                await query.answer("❌ Source not found")
                return
            
            routes = await self.source_model.get_routing_rules(source_id)
            
            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            type_emoji = type_emojis.get(source['source_type'], '📡')
            name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            
            text = f"<b>⚠️ Delete {type_emoji} Source</b>\n\n"
            text += f"<b>Source:</b> {name}\n"
            text += f"<b>Type:</b> {source['source_type'].title()}\n"
            text += f"<b>Chat/User ID:</b> <code>{source['source_chat_id']}</code>\n\n"
            
            if routes:
                text += f"<b>⚠️ This will also remove {len(routes)} routing rule(s):</b>\n"
                for route in routes[:3]:  # Show first 3 routes
                    group_name = route['group_title'] or f"Chat {route['tg_chat_id']}"
                    text += f"• → {group_name}\n"
                if len(routes) > 3:
                    text += f"• ... and {len(routes) - 3} more\n"
                text += "\n"
            
            text += "❗ <b>This action cannot be undone!</b>\n"
            text += "Are you sure you want to delete this source?"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🗑️ Yes, Delete", callback_data=f"sources:confirm_delete:{source_id}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"sources:source_details:{source_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing delete confirmation: {e}")
            await query.answer("❌ Error loading delete confirmation")
    
    async def confirm_delete_source(self, query: types.CallbackQuery, source_id: int):
        """Confirm and execute source deletion"""
        try:
            # Get source info for confirmation message
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            if not source:
                await query.answer("❌ Source not found")
                return
            
            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            type_emoji = type_emojis.get(source['source_type'], '📡')
            name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            
            # Delete routing rules first (foreign key constraints)
            await self.db.execute("DELETE FROM routing_rules WHERE source_chat_id = $1", source_id)
            
            # Delete source users 
            await self.db.execute("DELETE FROM source_chat_users WHERE source_chat_id = $1", source_id)
            
            # Finally delete the source
            success = await self.source_model.remove_source(source_id)
            
            # Clear cache since we deleted source
            self.clear_cache()
            
            if success:
                text = f"✅ <b>{type_emoji} Source Deleted</b>\n\n"
                text += f"<b>Source:</b> {name}\n"
                text += f"<b>Type:</b> {source['source_type'].title()}\n\n"
                text += "The source and all its routing rules have been permanently removed."
                
                await query.answer("✅ Source deleted successfully")
            else:
                text = f"❌ <b>Delete Failed</b>\n\n"
                text += f"Could not delete source: {name}\n"
                text += "The source may have already been removed or is in use."
                
                await query.answer("❌ Failed to delete source")
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error deleting source: {e}")
            await query.answer("❌ Error deleting source")
    
    async def start_set_source_name(self, query: types.CallbackQuery, source_id: int, state: FSMContext):
        """Start source name setting process"""
        return await detail.start_set_source_name(self, query, source_id, state)
    
    async def process_source_name_input(self, message: types.Message, state: FSMContext):
        """Process source name input"""
        return await detail.process_source_name_input(self, message, state)

    async def show_monitor_bot_selection(self, query: types.CallbackQuery, source_id: int):
        """Show available bots for monitor bot selection"""
        return await detail.show_monitor_bot_selection(self, query, source_id)

    async def show_forward_bot_selection(self, query: types.CallbackQuery, source_id: int):
        """Show available bots for forward bot selection"""
        return await detail.show_forward_bot_selection(self, query, source_id)

    async def set_monitor_bot(self, query: types.CallbackQuery, source_id: int, bot_id: int):
        """Set or clear monitor bot for source"""
        return await detail.set_monitor_bot(self, query, source_id, bot_id)

    async def set_forward_bot(self, query: types.CallbackQuery, source_id: int, bot_id: int):
        """Set or clear forward bot for source"""
        return await detail.set_forward_bot(self, query, source_id, bot_id)

    async def clear_source_bots(self, query: types.CallbackQuery, source_id: int):
        """Clear both monitor and forward bots for source"""
        return await detail.clear_source_bots(self, query, source_id)

    async def show_blockchain_selector(self, query: types.CallbackQuery, rule_id: int, current_chains: List[str] = None, state: FSMContext = None):
        """Show blockchain selector for routing rule"""
        return await blockchain.show_blockchain_selector(self, query, rule_id, current_chains, state)

    async def toggle_blockchain(self, query: types.CallbackQuery, rule_id: int, chain: str, state: FSMContext = None):
        """Toggle blockchain selection"""
        return await blockchain.toggle_blockchain(self, query, rule_id, chain, state)

    async def confirm_blockchain_selection(self, query: types.CallbackQuery, rule_id: int, state: FSMContext = None):
        """Confirm and save blockchain selection"""
        return await blockchain.confirm_blockchain_selection(self, query, rule_id, state)
