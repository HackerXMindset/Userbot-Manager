from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Dict, Any
import logging

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import GroupModel, BotModel
from app.config import settings

logger = logging.getLogger(__name__)

class GroupsHandler:
    """Handler for group management operations"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)
    
    async def show_groups_menu(self, query: types.CallbackQuery):
        """Display groups management menu"""
        try:
            groups_list = await self.group_model.get_groups_with_stats()
            
            text = "<b>👥 Groups Management</b>\n\n"
            
            if not groups_list:
                text += "No groups configured yet.\nClick 'Add Group' to start."
            else:
                for g in groups_list[:5]:  # Show first 5 in detail
                    status = "✅" if g['enabled'] else "🔴"
                    bot_icon = "🤖" if g['userbot_id'] else "⚠️"
                    text += (
                        f"{status} <b>{g['title'] or f'Chat {g['tg_chat_id']}'}</b>\n"
                        f"  ├ Quota: {g['daily_cap'] or '∞'}/day\n"
                        f"  ├ Cooldown: {g['cooldown_minutes']}min\n"
                        f"  ├ Targets: {g['targets_count']} | Schedules: {g['schedules_count']}\n"
                        f"  └ {bot_icon} Userbot {'assigned' if g['userbot_id'] else 'needed'}\n\n"
                    )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.groups_menu([dict(g) for g in groups_list])
            )
        except Exception as e:
            logger.error(f"Error showing groups menu: {e}")
            await query.answer("❌ Error loading groups")
    
    async def handle_group_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle group-related callbacks"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'add':
            await self.start_add_group(query, state)
        elif action == 'view':
            group_id = int(parts[2])
            await self.show_group_details(query, group_id)
        elif action == 'toggle':
            group_id = int(parts[2])
            await self.toggle_group(query, group_id)
        elif action == 'quota':
            group_id = int(parts[2])
            await self.show_quota_editor(query, group_id)
        elif action == 'cooldown':
            group_id = int(parts[2])
            await self.show_cooldown_editor(query, group_id)
        elif action == 'delete':
            group_id = int(parts[2])
            await self.confirm_delete_group(query, group_id)
        elif action == 'assign':
            group_id = int(parts[2])
            await self.show_userbot_assignment(query, group_id)
    
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
        await ManagementStates.adding_group.set()
        await state.update_data(message_id=query.message.message_id)
    
    async def process_group_input(self, message: types.Message, state: FSMContext):
        """Process group addition input"""
        if message.text == '/cancel':
            await state.finish()
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
                    'cooldown_minutes': 10
                })
            else:
                result = await self.group_model.create({
                    'tg_chat_id': chat_id,
                    'title': None,
                    'enabled': True,
                    'daily_cap': 0,
                    'cooldown_minutes': 10
                })
            
            await message.answer(
                f"✅ Group added successfully!\n"
                f"ID: {result['id']}\n\n"
                f"Configure schedules and assign a userbot to start monitoring.",
                reply_markup=self.keyboards.group_details(dict(result))
            )
            
        except Exception as e:
            await message.answer(f"❌ Error adding group: {e}")
        
        finally:
            await state.finish()
    
    async def show_group_details(self, query: types.CallbackQuery, group_id: int):
        """Show detailed group information"""
        try:
            group = await self.db.fetchrow("""
                SELECT g.*, 
                       COUNT(DISTINCT t.id) as targets_count,
                       COUNT(DISTINCT s.id) as schedules_count,
                       b.session_name as userbot_name,
                       (SELECT COUNT(*) FROM calls WHERE group_id = g.id AND sent_at > CURRENT_DATE) as calls_today
                FROM groups g
                LEFT JOIN targets t ON t.group_id = g.id
                LEFT JOIN group_schedules s ON s.group_id = g.id
                LEFT JOIN userbot_assignments ua ON ua.group_id = g.id
                LEFT JOIN bots b ON b.id = ua.userbot_id
                WHERE g.id = $1
                GROUP BY g.id, b.session_name
            """, group_id)
            
            if not group:
                await query.answer("Group not found!")
                return
            
            status = "✅ Enabled" if group['enabled'] else "🔴 Disabled"
            
            text = (
                f"<b>📋 Group Details</b>\n\n"
                f"<b>{group['title'] or f'Chat {group['tg_chat_id']}'}</b>\n"
                f"Status: {status}\n\n"
                f"<b>Configuration:</b>\n"
                f"├ Daily Quota: {group['daily_cap'] or 'Unlimited'}\n"
                f"├ Cooldown: {group['cooldown_minutes']} minutes\n"
                f"├ Targets: {group['targets_count']}\n"
                f"├ Schedules: {group['schedules_count']}\n"
                f"└ Userbot: {group['userbot_name'] or 'Not assigned'}\n\n"
                f"<b>Statistics:</b>\n"
                f"├ Calls Today: {group['calls_today']}\n"
                f"└ Chat ID: <code>{group['tg_chat_id']}</code>"
            )
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.group_details(dict(group))
            )
            
        except Exception as e:
            logger.error(f"Error showing group details: {e}")
            await query.answer("❌ Error loading group details")
    
    async def toggle_group(self, query: types.CallbackQuery, group_id: int):
        """Toggle group enabled status"""
        try:
            new_status = await self.group_model.toggle_enabled(group_id)
            await self.show_group_details(query, group_id)
            await query.answer(f"Group {'enabled' if new_status else 'disabled'}!")
        except Exception as e:
            logger.error(f"Error toggling group: {e}")
            await query.answer("❌ Error updating group")
    
    async def show_quota_editor(self, query: types.CallbackQuery, group_id: int):
        """Show quota editor"""
        try:
            current = await self.db.fetchval("SELECT daily_cap FROM groups WHERE id = $1", group_id)
            await query.message.edit_text(
                f"<b>📦 Set Daily Quota</b>\n\n"
                f"Current: {current or 'Unlimited'}\n"
                f"Enter new daily cap (0 for unlimited):",
                reply_markup=self.keyboards.number_picker(f"quota:{group_id}", current or 0, 0, 1000)
            )
        except Exception as e:
            logger.error(f"Error showing quota editor: {e}")
            await query.answer("❌ Error loading quota settings")
    
    async def show_cooldown_editor(self, query: types.CallbackQuery, group_id: int):
        """Show cooldown editor"""
        try:
            current = await self.db.fetchval("SELECT cooldown_minutes FROM groups WHERE id = $1", group_id)
            await query.message.edit_text(
                f"<b>⏱ Set Cooldown</b>\n\n"
                f"Current: {current} minutes\n"
                f"Minimum time between calls in this group:",
                reply_markup=self.keyboards.number_picker(f"cooldown:{group_id}", current, 0, 60)
            )
        except Exception as e:
            logger.error(f"Error showing cooldown editor: {e}")
            await query.answer("❌ Error loading cooldown settings")
    
    async def show_userbot_assignment(self, query: types.CallbackQuery, group_id: int):
        """Show userbot assignment options"""
        try:
            userbots = await self.bot_model.get_active_userbots()
            
            if not userbots:
                await query.message.edit_text(
                    "❌ No active userbots available.\nAdd a userbot first.",
                    reply_markup=self.keyboards.back_button(f"group:view:{group_id}")
                )
                return
            
            keyboard = []
            for bot in userbots[:10]:
                keyboard.append([
                    InlineKeyboardButton(
                        text=f"🤖 {bot['session_name']}",
                        callback_data=f"assign:userbot:{group_id}:{bot['id']}"
                    )
                ])
            
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