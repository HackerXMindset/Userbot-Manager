from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Dict, Any
import logging
import time

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import GroupModel, BotModel, TargetModel
from app.config import settings

logger = logging.getLogger(__name__)

class GroupsHandler:
    """Handler for group management operations"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)
        self.target_model = TargetModel(db)
        self.cache = {}
        self.cache_time = {}
    
    def is_fresh(self, key, seconds=300):
        """Check if cache entry is fresh (default 5 minutes)"""
        return key in self.cache_time and time.time() - self.cache_time[key] < seconds
    
    async def get_cached_groups_with_stats(self):
        """Get groups with stats using caching"""
        if self.is_fresh("groups_with_stats"):
            return self.cache["groups_with_stats"]
        
        groups = await self.group_model.get_groups_with_stats()
        self.cache["groups_with_stats"] = groups
        self.cache_time["groups_with_stats"] = time.time()
        return groups
    
    async def get_cached_group_targets(self, group_id):
        """Get group targets with caching"""
        key = f"targets_{group_id}"
        if self.is_fresh(key):
            return self.cache[key]
        
        targets = await self.group_model.get_targets(group_id)
        self.cache[key] = targets
        self.cache_time[key] = time.time()
        return targets
    
    def clear_cache(self):
        """Clear all cached data"""
        self.cache.clear()
        self.cache_time.clear()
    
    async def show_groups_menu(self, query: types.CallbackQuery, page: int = 1):
        """Display groups management menu"""
        try:
            groups_list = await self.get_cached_groups_with_stats()
            page_size = 5
            total_pages = (len(groups_list) + page_size - 1) // page_size
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_groups = groups_list[start_index:end_index]

            text = f"<b>👥 Groups Management (Page {page}/{total_pages})</b>\n\n"
            
            if not groups_list:
                text += "No groups configured yet.\nClick 'Add Group' to start."
            else:
                for g in paginated_groups:
                    status = "✅" if g['enabled'] else "🔴"
                    bot_icon = "🤖" if g['userbot_id'] else "⚠️"
                    display_name = g.get('display_name') or g['title'] or f"Chat {g['tg_chat_id']}"
                    text += (
                        f"{status} <b>{display_name}</b>\n"
                        f"  ├ Quota: {g['daily_cap'] or '∞'}/day\n"
                        f"  ├ Targets: {g['targets_count']} | Schedules: {g['schedules_count']}\n"
                        f"  └ {bot_icon} {g['userbot_name'] if g['userbot_id'] else 'Userbot needed'}\n\n"
                    )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.groups_menu(
                    [dict(g) for g in paginated_groups],
                    page=page,
                    total_pages=total_pages
                )
            )
        except Exception as e:
            logger.error(f"Error showing groups menu: {e}")
            await query.answer("❌ Error loading groups")
    
    async def handle_group_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle group-related callbacks"""
        parts = query.data.split(':')
        
        # Handle pagination
        if parts[0] == 'groups_page':
            if parts[1] == 'page':
                page = int(parts[2])
                await self.show_groups_menu(query, page=page)
                return

        action = parts[1]
        
        if action == 'add':
            await self.start_add_group(query, state)
        elif action == 'view':
            group_id = int(parts[2])
            await self.show_group_details(query, group_id)
        elif action == 'toggle':
            group_id = int(parts[2])
            await self.toggle_group(query, group_id)
        elif action == 'delete':
            group_id = int(parts[2])
            await self.confirm_delete_group(query, group_id)
        elif action == 'assign':
            group_id = int(parts[2])
            page = int(parts[3]) if len(parts) > 3 else 0
            await self.show_userbot_assignment(query, group_id, page)
        elif action == 'schedules':
            group_id = int(parts[2])
            await self.show_group_schedules(query, group_id)
        elif action == 'stats':
            group_id = int(parts[2])
            await self.show_group_stats(query, group_id)
        elif action == 'set_name':
            group_id = int(parts[2])
            await self.start_set_group_name(query, group_id, state)
        # No alerts configuration actions anymore
    
    async def start_add_group(self, query: types.CallbackQuery, state: FSMContext):
        """Start the add group process"""
        await query.message.edit_text(
            "<b>➕ Add New Group</b>\n\n"
            "Send me the group/channel in one of these formats:\n"
            "• @username (for public groups)\n"
            "• -100xxxxxxxxx (chat ID)\n"
            "• t.me/username link\n\n"
            "Type /cancel to abort.",
            reply_markup=self.keyboards.cancel_button("menu:groups")
        )
        await state.set_state(ManagementStates.adding_group.state)
        await state.update_data(message_id=query.message.message_id)
    
    async def process_group_input(self, message: types.Message, state: FSMContext):
        """Process group addition input"""
        if message.text == '/cancel':
            await state.clear()
            return
        
        try:
            # Parse input
            text = message.text.strip()
            chat_id = None
            username = None
            
            if text.startswith('-100'):
                chat_id = int(text)
            elif text.startswith('@'):
                username = text[1:]
            elif 't.me/' in text:
                username = text.split('/')[-1]
            elif text.isdigit():
                chat_id = -int(text)
            else:
                username = text
            
            # Create group record
            if username:
                result = await self.group_model.create({
                    'tg_chat_id': 0,  # Will update when userbot resolves
                    'title': username,
                    'enabled': True,
                    'daily_cap': 0,
                    'cooldown_minutes': 0
                })
            else:
                result = await self.group_model.create({
                    'tg_chat_id': chat_id,
                    'title': None,
                    'enabled': True,
                    'daily_cap': 0,
                    'cooldown_minutes': 0
                })
            
            # Clear cache since we created new group
            self.clear_cache()
            
            # Auto-create target for this group
            target_chat_id = chat_id if chat_id else 0  # Use 0 for username-based groups until resolved
            await self.db.execute(
                "INSERT INTO targets (group_id, dest_chat_id, created_at) VALUES ($1, $2, NOW())",
                result['id'], target_chat_id
            )
            
            await message.answer(
                f"✅ Group added successfully!\n"
                f"ID: {result['id']}\n"
                f"Target auto-created for calls delivery.\n\n"
                f"Configure schedules and assign a userbot to start monitoring.",
                reply_markup=self.keyboards.group_details(dict(result))
            )
            
        except Exception as e:
            await message.answer(f"❌ Error adding group: {e}")
        
        finally:
            await state.clear()
    
    async def show_group_details(self, query: types.CallbackQuery, group_id: int):
        """Show detailed group information"""
        try:
            group = await self.db.fetchrow("""
                SELECT g.*,
                       COUNT(DISTINCT t.id) as targets_count,
                       COUNT(DISTINCT s.id) as schedules_count,
                       COALESCE(b.display_name, b.session_name) as userbot_name,
                       (SELECT COUNT(*) FROM token_call_history tch WHERE tch.target_chat_id = g.tg_chat_id AND DATE(tch.called_at) = CURRENT_DATE) as calls_today
                FROM groups g
                LEFT JOIN targets t ON t.group_id = g.id
                LEFT JOIN group_schedules s ON s.group_id = g.id
                LEFT JOIN userbot_assignments ua ON ua.group_id = g.id
                LEFT JOIN bots b ON b.id = ua.userbot_id
                WHERE g.id = $1
                GROUP BY g.id, b.session_name, b.display_name
            """, group_id)
            
            if not group:
                await query.answer("Group not found!")
                return
            
            status = "✅ Enabled" if group['enabled'] else "🔴 Disabled"
            
            display_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
            text = (
                f"<b>📋 Group Details</b>\n\n"
                f"<b>{display_name}</b>\n"
                f"Status: {status}\n\n"
                f"<b>Configuration:</b>\n"
                f"├ Daily Quota: {group['daily_cap'] or 'Unlimited'}\n"
                f"├ Targets: {group['targets_count']}\n"
                f"├ Schedules: {group['schedules_count']}\n"
                f"└ Userbot: {group['userbot_name'] or 'Not assigned'}\n\n"
                f"<b>Statistics:</b>\n"
                f"├ Calls Today: {group['calls_today']}\n"
                f"└ Chat ID: <code>{group['tg_chat_id']}</code>"
            )
            
            # Get the base keyboard
            keyboard_rows = self.keyboards.group_details(dict(group)).inline_keyboard
            
            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            )
            
        except Exception as e:
            logger.error(f"Error showing group details: {e}")
            await query.answer("❌ Error loading group details")
    
    async def toggle_group(self, query: types.CallbackQuery, group_id: int):
        """Toggle group enabled status"""
        try:
            new_status = await self.group_model.toggle_enabled(group_id)
            
            # Clear cache since we modified group status
            self.clear_cache()
            
            await self.show_group_details(query, group_id)
            await query.answer(f"Group {'enabled' if new_status else 'disabled'}!")
        except Exception as e:
            logger.error(f"Error toggling group: {e}")
            await query.answer("❌ Error updating group")
    
    async def show_userbot_assignment(self, query: types.CallbackQuery, group_id: int, page: int = 0):
        """Show userbot assignment options with pagination (3x3 grid)"""
        try:
            userbots = await self.bot_model.get_active_userbots()

            if not userbots:
                await query.message.edit_text(
                    "❌ No active userbots available.\nAdd a userbot first.",
                    reply_markup=self.keyboards.back_button(f"group:view:{group_id}")
                )
                return

            # Pagination settings
            items_per_page = 9
            columns = 3
            total_bots = len(userbots)
            total_pages = (total_bots + items_per_page - 1) // items_per_page

            # Ensure page is within bounds
            page = max(0, min(page, total_pages - 1))

            # Get bots for current page
            start_idx = page * items_per_page
            end_idx = start_idx + items_per_page
            page_bots = userbots[start_idx:end_idx]

            # Build keyboard with 3 columns
            keyboard = []
            row = []
            for bot in page_bots:
                bot_name = bot.get('display_name') or bot['session_name']
                # Truncate long names to fit 3 columns
                display_name = bot_name[:12] + "..." if len(bot_name) > 15 else bot_name

                row.append(InlineKeyboardButton(
                    text=f"🤖 {display_name}",
                    callback_data=f"assign:userbot:{group_id}:{bot['id']}"
                ))

                # Add row when we have 3 buttons
                if len(row) == columns:
                    keyboard.append(row)
                    row = []

            # Add remaining buttons if any
            if row:
                keyboard.append(row)

            # Navigation buttons
            nav_buttons = []
            if total_pages > 1:
                if page > 0:
                    nav_buttons.append(InlineKeyboardButton(
                        text="◀️ Prev",
                        callback_data=f"group:assign:{group_id}:{page - 1}"
                    ))

                nav_buttons.append(InlineKeyboardButton(
                    text=f"📄 {page + 1}/{total_pages}",
                    callback_data="noop"
                ))

                if page < total_pages - 1:
                    nav_buttons.append(InlineKeyboardButton(
                        text="Next ▶️",
                        callback_data=f"group:assign:{group_id}:{page + 1}"
                    ))

                keyboard.append(nav_buttons)

            # Back button
            keyboard.append([
                InlineKeyboardButton(text="🔙 Back", callback_data=f"group:view:{group_id}")
            ])

            await query.message.edit_text(
                "<b>🤖 Assign Userbot</b>\n\n"
                "Select a userbot to assign to this group:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
            )

        except Exception as e:
            logger.error(f"Error showing userbot assignment: {e}")
            await query.answer("❌ Error loading userbots")
    
    async def show_group_schedules(self, query: types.CallbackQuery, group_id: int):
        """Show schedules for a specific group"""
        try:
            # Get group info
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                await query.answer("❌ Group not found")
                return
            
            # Get schedules for this group
            schedules = await self.db.fetch("""
                SELECT * FROM group_schedules 
                WHERE group_id = $1 
                ORDER BY start_time
            """, group_id)
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            text = f"<b>📅 Schedules for {group_name}</b>\n\n"
            
            if not schedules:
                text += "No schedules configured for this group.\n\n"
                text += "Schedules determine when this group can send calls. "
                text += "Without schedules, the group can send calls 24/7."
            else:
                text += f"<b>Active Schedules ({len(schedules)}):</b>\n\n"
                for i, schedule in enumerate(schedules, 1):
                    days = self._format_weekdays(schedule['weekdays'])
                    max_calls = schedule['max_calls_in_window'] or '∞'
                    text += (
                        f"<b>{i}.</b> {schedule['start_time']} - {schedule['end_time']}\n"
                        f"   └ Days: {days} | Max calls: {max_calls}\n\n"
                    )
            
            # Build keyboard
            keyboard_rows = []
            
            # Add schedule button
            keyboard_rows.append([
                InlineKeyboardButton(text="➕ Add Schedule", callback_data=f"schedule:add:{group_id}")
            ])
            
            # Remove buttons for existing schedules
            if schedules:
                for schedule in schedules[:5]:  # Limit to 5 for UI space
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            text=f"🗑️ Delete {schedule['start_time']}-{schedule['end_time']}", 
                            callback_data=f"schedule:delete:{schedule['id']}"
                        )
                    ])
            
            # Back button
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{group_id}")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing group schedules: {e}")
            await query.answer("❌ Error loading schedules")
    
    async def show_group_stats(self, query: types.CallbackQuery, group_id: int):
        """Show statistics for a specific group"""
        try:
            # Get group info
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                await query.answer("❌ Group not found")
                return
            
            # Get comprehensive stats
            stats = await self.db.fetchrow("""
                SELECT
                    COUNT(DISTINCT s.id) as schedules_count,
                    COUNT(DISTINCT sc.id) as sources_count,
                    COUNT(DISTINCT t.id) as targets_count,
                    COUNT(CASE WHEN c.called_at >= CURRENT_DATE THEN 1 END) as calls_today,
                    COUNT(CASE WHEN c.called_at >= CURRENT_DATE - INTERVAL '7 days' THEN 1 END) as calls_this_week,
                    COUNT(c.id) as total_calls,
                    COALESCE(b.display_name, b.session_name) as userbot_name,
                    MAX(c.called_at) as last_call_time
                FROM groups g
                LEFT JOIN group_schedules s ON s.group_id = g.id
                LEFT JOIN source_chats sc ON sc.group_id = g.id
                LEFT JOIN targets t ON t.group_id = g.id
                LEFT JOIN token_call_history c ON c.target_chat_id = g.tg_chat_id
                LEFT JOIN userbot_assignments ua ON ua.group_id = g.id
                LEFT JOIN bots b ON b.id = ua.userbot_id
                WHERE g.id = $1
                GROUP BY g.id, b.session_name, b.display_name
            """, group_id)
            
            group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
            status = "✅ Enabled" if group['enabled'] else "🔴 Disabled"
            
            # Format last call time
            if stats['last_call_time']:
                last_call = stats['last_call_time'].strftime('%Y-%m-%d %H:%M')
            else:
                last_call = 'Never'
            
            text = f"<b>📊 Stats for {group_name}</b>\n\n"
            text += f"<b>Status:</b> {status}\n"
            text += f"<b>Userbot:</b> {stats['userbot_name'] or 'Not assigned'}\n\n"
            
            text += f"<b>Configuration:</b>\n"
            text += f"├ Schedules: {stats['schedules_count']}\n"
            text += f"├ Sources: {stats['sources_count']}\n"
            text += f"└ Targets: {stats['targets_count']}\n\n"
            
            text += f"<b>Call Activity:</b>\n"
            text += f"├ Today: {stats['calls_today']}\n"
            text += f"├ This Week: {stats['calls_this_week']}\n"
            text += f"├ All Time: {stats['total_calls']}\n"
            text += f"└ Last Call: {last_call}\n\n"
            
            text += f"<b>Group Details:</b>\n"
            text += f"└ Chat ID: <code>{group['tg_chat_id']}</code>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{group_id}")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing group stats: {e}")
            await query.answer("❌ Error loading statistics")
    
    async def confirm_delete_group(self, query: types.CallbackQuery, group_id: int):
        """Show delete confirmation for a group"""
        try:
            # Get group info
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                await query.answer("❌ Group not found")
                return
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            # Get counts for warning
            counts = await self.db.fetchrow("""
                SELECT 
                    COUNT(DISTINCT s.id) as schedules_count,
                    COUNT(DISTINCT sc.id) as sources_count,
                    COUNT(DISTINCT t.id) as targets_count,
                    COUNT(c.id) as total_calls
                FROM groups g
                LEFT JOIN group_schedules s ON s.group_id = g.id
                LEFT JOIN source_chats sc ON sc.group_id = g.id
                LEFT JOIN targets t ON t.group_id = g.id
                LEFT JOIN calls c ON c.group_id = g.id
                WHERE g.id = $1
            """, group_id)
            
            text = f"<b>🗑️ Delete Group</b>\n\n"
            text += f"<b>Group:</b> {group_name}\n"
            text += f"<b>Chat ID:</b> <code>{group['tg_chat_id']}</code>\n\n"
            
            text += f"⚠️ <b>This will permanently delete:</b>\n"
            text += f"├ {counts['schedules_count']} schedule(s)\n"
            text += f"├ {counts['sources_count']} source(s)\n" 
            text += f"├ {counts['targets_count']} target(s)\n"
            text += f"└ {counts['total_calls']} call record(s)\n\n"
            
            text += f"<b>This action cannot be undone!</b>\n"
            text += f"Are you sure you want to delete this group?"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"confirm_delete_group:{group_id}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"group:view:{group_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing delete confirmation: {e}")
            await query.answer("❌ Error loading delete confirmation")
    
    async def delete_group(self, query: types.CallbackQuery):
        """Actually delete the group and all related data"""
        try:
            # Parse callback data: confirm_delete_group:group_id
            group_id = int(query.data.split(':', 1)[1])
            
            # Get group info before deletion
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                await query.answer("❌ Group not found")
                return
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            # Delete all related data (foreign keys should handle this, but be explicit)
            async with self.db.acquire() as conn:
                async with conn.transaction():
                    # Delete schedules
                    await conn.execute("DELETE FROM group_schedules WHERE group_id = $1", group_id)
                    
                    # Delete targets  
                    await conn.execute("DELETE FROM targets WHERE group_id = $1", group_id)
                    
                    # Delete sources
                    await conn.execute("DELETE FROM source_chats WHERE group_id = $1", group_id)
                    
                    # Delete userbot assignments
                    await conn.execute("DELETE FROM userbot_assignments WHERE group_id = $1", group_id)

                    # Delete call records (using tg_chat_id since token_call_history uses target_chat_id)
                    await conn.execute("DELETE FROM token_call_history WHERE target_chat_id = $1", group['tg_chat_id'])

                    # Finally delete the group itself
                    await conn.execute("DELETE FROM groups WHERE id = $1", group_id)
            
            text = f"✅ <b>Group Deleted</b>\n\n"
            text += f"Successfully deleted: <b>{group_name}</b>\n"
            text += f"All associated data has been removed.\n\n"
            text += f"You can add a new group anytime from the groups menu."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="👥 Groups Menu", callback_data="menu:groups")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Group deleted successfully!")
            
        except Exception as e:
            logger.error(f"Error deleting group: {e}")
            await query.answer("❌ Error deleting group")
    
    def _format_weekdays(self, weekdays):
        """Format weekdays list to readable string"""
        if not weekdays:
            return "No days"
        
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        
        if len(weekdays) == 7:
            return "Daily"
        elif set(weekdays) == {1, 2, 3, 4, 5}:
            return "Weekdays" 
        elif set(weekdays) == {6, 7}:
            return "Weekends"
        else:
            return ", ".join([day_names[d-1] for d in sorted(weekdays)])
    
    async def start_set_group_name(self, query: types.CallbackQuery, group_id: int, state: FSMContext):
        """Start group name setting process"""
        try:
            group = await self.group_model.get_by_id(group_id)
            if not group:
                await query.answer("Group not found!")
                return
            
            current_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
            
            await query.message.edit_text(
                f"<b>✏️ Set Group Name</b>\n\n"
                f"Current name: <b>{current_name}</b>\n\n"
                f"Enter a new custom name for this group:\n\n"
                f"Type /cancel to abort.",
                reply_markup=self.keyboards.cancel_button(f"group:view:{group_id}")
            )
            
            await state.set_state(ManagementStates.group_set_name)
            await state.update_data(
                group_id=group_id,
                message_id=query.message.message_id
            )
            
        except Exception as e:
            logger.error(f"Error starting group name setting: {e}")
            await query.answer("❌ Error starting name setting")
    
    async def process_group_name_input(self, message: types.Message, state: FSMContext):
        """Process group name input"""
        if message.text == '/cancel':
            data = await state.get_data()
            group_id = data.get('group_id')
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
            group_id = data.get('group_id')
            
            if not group_id:
                await message.answer("❌ Session data lost. Please try again.")
                await state.clear()
                return
            
            # Update group name in database (direct SQL to avoid updated_at requirement)
            await self.db.execute(
                "UPDATE groups SET display_name = $1 WHERE id = $2",
                new_name, group_id
            )
            
            await message.answer(
                f"✅ <b>Group Name Updated Successfully!</b>\n\n"
                f"Group name set to: <b>{new_name}</b>"
            )
            
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error updating group name: {e}")
            await message.answer(f"❌ Error updating name: {str(e)}")
            await state.clear()
