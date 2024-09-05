from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging
import time

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import GroupModel
from app.models.source_chat import SourceChatModel

logger = logging.getLogger(__name__)

class SourcesHandler:
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
    
    async def show_sources_menu(self, query: types.CallbackQuery):
        """Show global sources overview"""
        try:
            # Get all sources globally (with caching)
            sources = await self.get_cached_sources()
            
            text = "<b>📡 Global Sources</b>\n\n"
            text += "Source chats monitor for token addresses and route them to targets.\n\n"
            
            if not sources:
                text += "No sources configured yet."
            else:
                for source in sources[:8]:  # Show max 8 sources
                    type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
                    status = "✅" if source['enabled'] else "❌"
                    type_emoji = type_emojis.get(source['source_type'], '📡')
                    name = source.get('display_name') or source.get('group_display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
                    route_count = source['route_count'] or 0
                    
                    text += f"{status} {type_emoji} <b>{name}</b>\n"
                    text += f"   Routes: {route_count} targets\n\n"
            
            keyboard_rows = [
                [
                    InlineKeyboardButton(text="➕ Add Source", callback_data="sources:add_global"),
                    InlineKeyboardButton(text="🔄 Routing", callback_data="sources:routing")
                ]
            ]
            
            if sources:
                keyboard_rows.append([
                    InlineKeyboardButton(text="📋 Manage Sources", callback_data="sources:manage_global")
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:sources")],
                [InlineKeyboardButton(text="🗑️ Clear Cache", callback_data="sources:clear_cache")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            try:
                await query.message.edit_text(text, reply_markup=keyboard)
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    await query.answer()
                else:
                    raise edit_error
            
        except Exception as e:
            logger.error(f"Error showing sources menu: {e}")
            await query.answer("❌ Error loading sources")

    async def handle_sources_action(self, query: types.CallbackQuery, state: FSMContext = None):
        """Handle sources actions"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'add_global':
            await self.start_add_global_source(query, state)
        elif action == 'manage_global':
            await self.show_manage_global_sources(query)
        elif action == 'routing':
            await self.show_routing_menu(query)
        elif action == 'source_details':
            source_id = int(parts[2])
            await self.show_source_details(query, source_id)
        elif action == 'add_route':
            source_id = int(parts[2])
            await self.show_add_route_menu(query, source_id)
        elif action == 'create_route':
            source_id, group_id = int(parts[2]), int(parts[3])
            await self.create_routing_rule(query, source_id, group_id)
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
        else:
            await self.show_sources_menu(query)
    
    async def start_add_global_source(self, query: types.CallbackQuery, state: FSMContext):
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
    
    async def show_manage_global_sources(self, query: types.CallbackQuery):
        """Show all sources for management"""
        try:
            sources = await self.get_cached_sources()
            
            text = "<b>📋 Manage Global Sources</b>\n\n"
            
            if not sources:
                text += "No sources configured yet."
            else:
                text += "Click a source to view details and manage routing:\n\n"
                
            keyboard_rows = []
            for source in sources:
                type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
                status = "✅" if source['enabled'] else "❌"
                type_emoji = type_emojis.get(source['source_type'], '📡')
                name = source.get('display_name') or source.get('group_display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
                
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status} {type_emoji} {name}",
                        callback_data=f"sources:source_details:{source['id']}"
                    )
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing manage sources: {e}")
            await query.answer("❌ Error loading sources")
    
    async def show_routing_menu(self, query: types.CallbackQuery):
        """Show routing rules overview"""
        try:
            text = "<b>🔄 Routing Rules</b>\n\n"
            text += "Manage how sources route to target groups.\n\n"
            text += "Select a source to manage its routing:"
            
            sources = await self.get_cached_sources()
            keyboard_rows = []
            
            for source in sources:
                type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
                type_emoji = type_emojis.get(source['source_type'], '📡')
                name = source.get('display_name') or source.get('group_display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
                route_count = source['route_count'] or 0
                
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{type_emoji} {name} ({route_count} routes)",
                        callback_data=f"sources:source_details:{source['id']}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:sources")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing routing menu: {e}")
            await query.answer("❌ Error loading routing")
    
    async def show_source_details(self, query: types.CallbackQuery, source_id: int):
        """Show detailed source information and routing management"""
        try:
            # Get source details
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            if not source:
                await query.answer("❌ Source not found")
                return
            
            # Get routing rules
            routes = await self.source_model.get_routing_rules(source_id)
            
            type_emojis = {'channel': '📢', 'group': '👥', 'dm': '💬'}
            status = "✅ Enabled" if source['enabled'] else "❌ Disabled"
            type_emoji = type_emojis.get(source['source_type'], '📡')
            name = source.get('display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            
            text = f"<b>⚙️ {type_emoji} Source Details</b>\n\n"
            text += f"<b>Name:</b> {name}\n"
            text += f"<b>Chat/User ID:</b> <code>{source['source_chat_id']}</code>\n"
            text += f"<b>Type:</b> {source['source_type'].title()}\n"
            text += f"<b>Status:</b> {status}\n\n"
            
            if routes:
                text += f"<b>🔄 Routing Rules ({len(routes)}):</b>\n"
                for route in routes:
                    route_status = "✅" if route['enabled'] else "❌"
                    group_name = route['group_title'] or f"Chat {route['tg_chat_id']}"
                    text += f"{route_status} → <b>{group_name}</b>\n"
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
            
            # Add remove route buttons for existing routes
            for route in routes:
                group_name = (route['group_title'] or f"Chat {route['tg_chat_id']}")[:25]
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"🗑️ Remove → {group_name}",
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
    
    async def show_add_route_menu(self, query: types.CallbackQuery, source_id: int):
        """Show available groups to route to"""
        try:
            # Get source info
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            if not source:
                await query.answer("❌ Source not found")
                return
            
            # Get all groups (with caching)
            groups = await self.get_cached_groups()
            
            # Get existing routing rules to exclude them
            existing_routes = await self.source_model.get_routing_rules(source_id)
            existing_group_ids = {route['target_group_id'] for route in existing_routes}
            
            # Filter out groups that already have routes
            available_groups = [g for g in groups if g['id'] not in existing_group_ids]
            
            source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            text = f"<b>➕ Add Route for {source_name}</b>\n\n"
            
            if not available_groups:
                text += "No available groups to route to.\nAll groups already have routing rules from this source."
                keyboard_rows = [
                    [InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")]
                ]
            else:
                text += "Select target group to route to:"
                keyboard_rows = []
                
                for group in available_groups:
                    group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                    status_icon = "✅" if group['enabled'] else "❌"
                    
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            text=f"{status_icon} {group_name}",
                            callback_data=f"sources:create_route:{source_id}:{group['id']}"
                        )
                    ])
                
                keyboard_rows.append([
                    InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")
                ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing add route menu: {e}")
            await query.answer("❌ Error loading available routes")
    
    async def create_routing_rule(self, query: types.CallbackQuery, source_id: int, group_id: int):
        """Create a new routing rule"""
        try:
            # Get source and group info
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            
            if not source or not group:
                await query.answer("❌ Source or group not found")
                return
            
            # Create the routing rule
            route = await self.source_model.add_routing_rule(source_id, group_id)
            
            # Clear cache since we added new routing rule
            self.clear_cache()
            
            source_name = source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = f"✅ <b>Routing Rule Created</b>\n\n"
            text += f"<b>Source:</b> {source_name}\n"
            text += f"<b>Target:</b> {group_name}\n\n"
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
    
    async def remove_routing_rule(self, query: types.CallbackQuery, source_id: int, group_id: int):
        """Remove a routing rule"""
        try:
            # Get source and group info for confirmation message
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            
            if not source or not group:
                await query.answer("❌ Source or group not found")
                return
            
            # Remove the routing rule
            success = await self.source_model.remove_routing_rule(source_id, group_id)
            
            # Clear cache since we removed routing rule
            self.clear_cache()
            
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
        try:
            source = await self.db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            title = source['title'] or f"ID: {source['source_chat_id']}"
            
            # Set source ID in state
            await state.set_data({'source_id': source_id})
            await state.set_state(ManagementStates.adding_source_user_id)
            
            text = f"<b>👥 Add User to {title}</b>\n\n"
            text += "Please enter the Telegram user ID of the person whose messages should trigger token forwards from this group.\n\n"
            text += "Example: <code>123456789</code>\n\n"
            text += "💡 <i>You can get user IDs by forwarding their message to @userinfobot</i>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"sources:users:{source_id}")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error starting add user: {e}")
            await query.answer("❌ Error starting user setup")
    
    async def start_add_source(self, query: types.CallbackQuery):
        """Start adding a source - select group"""
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
    
    async def show_manage_sources(self, query: types.CallbackQuery):
        """Show source management - select group"""
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
    
    async def show_group_sources(self, query: types.CallbackQuery, group_id: int):
        """Show sources for a specific group"""
        try:
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            sources = await self.source_model.get_by_group(group_id)
            
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
        try:
            # Get an active userbot to use for user lookup
            from app.models import BotModel
            bot_model = BotModel(self.db)
            userbots = await bot_model.get_active_userbots()
            
            if not userbots:
                return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}
            
            # Use the first active userbot for lookup
            userbot = userbots[0]
            session_string = userbot.get('session_string')
            
            if not session_string:
                return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}
            
            # Create temporary client for user lookup
            from telethon import TelegramClient
            from telethon.sessions import StringSession
            from app.config import settings
            
            client = TelegramClient(
                StringSession(session_string),
                settings.api_id,
                settings.api_hash
            )
            
            await client.connect()
            
            try:
                # Get user entity
                user_entity = await client.get_entity(user_id)
                
                return {
                    "user_id": user_id,
                    "username": user_entity.username,
                    "first_name": user_entity.first_name or "Unknown",
                    "last_name": user_entity.last_name
                }
                
            except Exception as lookup_error:
                logger.debug(f"Could not lookup user {user_id}: {lookup_error}")
                return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}
                
            finally:
                await client.disconnect()
                
        except Exception as e:
            logger.error(f"Error in user lookup: {e}")
            return {"user_id": user_id, "username": None, "first_name": f"User {user_id}", "last_name": None}

    async def process_user_input(self, message: types.Message, state: FSMContext):
        """Process user ID input for source filtering"""
        try:
            data = await state.get_data()
            source_id = data.get('source_id')
            
            if not source_id:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return
            
            # Parse user ID
            try:
                user_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid user ID. Please enter a valid number.")
                return
            
            # Lookup real user info from Telegram
            user_info = await self._lookup_user_info(user_id)
            
            # Add user to source with real info
            await self.source_model.add_user_to_source(
                source_id=source_id,
                user_id=user_id,
                username=user_info["username"],
                first_name=user_info["first_name"]
            )
            
            # Show user info in success message
            display_name = user_info["first_name"]
            if user_info["username"]:
                display_name = f"{user_info['first_name']} (@{user_info['username']})"
            elif user_info["first_name"] == "Unknown":
                display_name = f"User {user_id}"
            
            text = f"✅ <b>User Added</b>\n\n"
            text += f"Name: {display_name}\n"
            text += f"User ID: <code>{user_id}</code>\n"
            text += f"This user can now trigger token forwards from this source."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source_id}")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await message.reply(text, reply_markup=keyboard)
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error processing user input: {e}")
            await message.reply("❌ Error adding user")
            await state.clear()
    
    async def manage_source_users(self, query: types.CallbackQuery, source_id: int):
        """Show user management for a source"""
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
                            callback_data=f"sources:remove_user:{source_id}:{user['user_id']}"
                        )
                    ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error managing source users: {e}")
            await query.answer("❌ Error loading users")
    
    async def remove_user_from_source(self, query: types.CallbackQuery, source_id: int, user_id: int):
        """Remove user from source"""
        try:
            success = await self.source_model.remove_user_from_source(source_id, user_id)
            
            if success:
                await query.answer("✅ User removed")
                await self.manage_source_users(query, source_id)
            else:
                await query.answer("❌ Failed to remove user")
                
        except Exception as e:
            logger.error(f"Error removing user: {e}")
            await query.answer("❌ Error removing user")
    
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
        try:
            source = await self.source_model.get_by_id(source_id)
            if not source:
                await query.answer("Source not found!")
                return
            
            current_name = source.get('display_name') or source['name'] or source['title'] or f"Source {source['source_chat_id']}"
            
            await query.message.edit_text(
                f"<b>✏️ Set Source Name</b>\n\n"
                f"Current name: <b>{current_name}</b>\n\n"
                f"Enter a new custom name for this source:\n\n"
                f"Type /cancel to abort.",
                reply_markup=self.keyboards.cancel_button(f"sources:source_details:{source_id}")
            )
            
            await state.set_state(ManagementStates.source_set_name)
            await state.update_data(
                source_id=source_id,
                message_id=query.message.message_id
            )
            
        except Exception as e:
            logger.error(f"Error starting source name setting: {e}")
            await query.answer("❌ Error starting name setting")
    
    async def process_source_name_input(self, message: types.Message, state: FSMContext):
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
            await self.db.execute(
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
                text = f"❌ <b>Delete Error</b>\n\n"
                text += f"Failed to delete source due to an error:\n<code>{str(e)}</code>\n\n"
                text += "Please try again or contact support."
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Back", callback_data=f"sources:source_details:{source_id}")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
                ])
                
                await query.message.edit_text(text, reply_markup=keyboard)
            except:
                pass