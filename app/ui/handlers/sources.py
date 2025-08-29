from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging

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
    
    async def show_sources_menu(self, query: types.CallbackQuery):
        """Show sources overview"""
        try:
            # Get all groups with their source counts
            groups = await self.group_model.get_groups_with_stats()
            
            text = "<b>📡 Source Chats Overview</b>\n\n"
            text += "Source chats are channels/groups that forward token addresses to your targets.\n\n"
            
            if not groups:
                text += "No groups configured. Add groups first."
            else:
                for group in groups:
                    sources = await self.source_model.get_by_group(group['id'])
                    source_count = len(sources)
                    group_name = group['title'] or f"Chat {group['tg_chat_id']}"
                    status = "✅" if group['enabled'] else "❌"
                    text += f"{status} <b>{group_name}</b>: {source_count} sources\n"
            
            keyboard_rows = []
            if groups:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➕ Add Source", callback_data="sources:add"),
                    InlineKeyboardButton(text="📋 Manage", callback_data="sources:manage")
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:sources")],
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
        
        if action == 'add':
            await self.start_add_source(query)
        elif action == 'manage':
            await self.show_manage_sources(query)
        elif action == 'select_group':
            group_id = int(parts[2])
            await self.show_group_sources(query, group_id)
        elif action == 'remove':
            source_id = int(parts[2])
            await self.confirm_remove_source(query, source_id)
        elif action == 'remove_confirm':
            source_id = int(parts[2])
            await self.remove_source(query, source_id)
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
        else:
            await self.show_sources_menu(query)
    
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
            groups = await self.group_model.get_groups_with_stats()
            
            if not groups:
                await query.answer("❌ No groups available. Add groups first.")
                return
            
            text = "<b>➕ Add Source Chat</b>\n\n"
            text += "Select which group this source should forward to:"
            
            keyboard_rows = []
            for group in groups:
                group_name = group['title'] or f"Chat {group['tg_chat_id']}"
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
            groups = await self.group_model.get_groups_with_stats()
            
            text = "<b>📋 Manage Sources</b>\n\n"
            text += "Select group to manage its sources:"
            
            keyboard_rows = []
            for group in groups:
                sources = await self.source_model.get_by_group(group['id'])
                group_name = group['title'] or f"Chat {group['tg_chat_id']}"
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
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
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
            group_id = data.get('group_id')
            
            if not group_id:
                await message.reply("❌ Session expired. Please start again.")
                await state.clear()
                return
            
            # Parse chat ID
            try:
                source_chat_id = int(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid chat ID. Please enter a valid number.")
                return
            
            # Try to detect if it's a channel or group by checking if it starts with -100
            if str(source_chat_id).startswith('-100'):
                # This could be either a channel or supergroup
                source_type = 'group'  # Default to group, user can change later
                title = f"Chat {source_chat_id}"
            else:
                # Regular group or channel
                source_type = 'channel'
                title = f"Channel {source_chat_id}"
            
            # Add source to database
            source = await self.source_model.add_source(
                group_id=group_id,
                source_chat_id=source_chat_id,
                source_type=source_type,
                title=title
            )
            
            text = f"✅ <b>Source Added</b>\n\n"
            text += f"Chat ID: <code>{source_chat_id}</code>\n"
            text += f"Type: {source_type.title()}\n\n"
            
            keyboard_rows = []
            
            if source_type == 'group':
                text += "Since this is a group, you can configure which users are allowed to trigger forwards.\n"
                keyboard_rows.append([
                    InlineKeyboardButton(text="👥 Manage Users", callback_data=f"sources:users:{source['id']}")
                ])
            else:
                text += "This channel will forward all token addresses posted."
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="📋 View Sources", callback_data=f"sources:select_group:{group_id}")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await message.reply(text, reply_markup=keyboard)
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error processing source input: {e}")
            await message.reply("❌ Error adding source")
            await state.clear()
    
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
            
            # Add user to source
            await self.source_model.add_user_to_source(
                source_id=source_id,
                user_id=user_id,
                username=f"User{user_id}",  # Placeholder
                first_name="Unknown"
            )
            
            text = f"✅ <b>User Added</b>\n\n"
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