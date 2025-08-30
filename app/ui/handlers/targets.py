from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.ui.keyboards import Keyboards
from app.models import GroupModel

logger = logging.getLogger(__name__)

class TargetsHandler:
    """Handler for target management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
    
    async def handle_target_action(self, query: types.CallbackQuery):
        """Handle target actions"""
        parts = query.data.split(':', 2)
        action = parts[1]
        
        if action == 'add':
            await self.start_add_target(query)
        elif action == 'delete':
            if len(parts) > 2:
                target_id = int(parts[2])
                await self.delete_target(query, target_id)
            else:
                await self.show_delete_target_list(query)
        else:
            await self.show_targets_menu(query)
    
    async def show_targets_menu(self, query: types.CallbackQuery):
        """Show targets overview"""
        try:
            # Get targets with group info
            targets = await self.db.fetch("""
                SELECT t.*, g.title as group_title, g.tg_chat_id as group_chat_id
                FROM targets t
                JOIN groups g ON g.id = t.group_id
                ORDER BY g.title, t.dest_chat_id
            """)
            
            text = "<b>🎯 Targets Overview</b>\n\n"
            
            if not targets:
                text += "No targets configured.\nTargets are the channels where calls are sent."
            else:
                current_group = None
                for target in targets:
                    group_name = target['group_title'] or f"Chat {target['group_chat_id']}"
                    if current_group != group_name:
                        text += f"\n<b>{group_name}</b>\n"
                        current_group = group_name
                    
                    text += f"• Target: <code>{target['dest_chat_id']}</code>\n"
            
            keyboard_rows = []
            if targets:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➕ Add Target", callback_data="targets:add"),
                    InlineKeyboardButton(text="🗑️ Delete Target", callback_data="targets:delete")
                ])
            else:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➕ Add Target", callback_data="targets:add")
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:targets")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            try:
                await query.message.edit_text(text, reply_markup=keyboard)
            except Exception as edit_error:
                if "message is not modified" in str(edit_error):
                    # Message content is identical, just answer the callback
                    await query.answer()
                else:
                    raise edit_error
            
        except Exception as e:
            logger.error(f"Error showing targets menu: {e}")
            await query.answer("❌ Error loading targets")

    async def start_add_target(self, query: types.CallbackQuery):
        """Start adding a target"""
        try:
            # Get available groups
            groups = await self.group_model.get_groups_with_stats()
            
            if not groups:
                await query.answer("❌ No groups available. Add groups first.")
                return
            
            text = "<b>➕ Add Target</b>\n\n"
            text += "Select a group to add a target to:"
            
            keyboard_rows = []
            for group in groups:
                group_name = group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=group_name,
                        callback_data=f"target_group:{group['id']}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:targets")
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
            logger.error(f"Error starting add target: {e}")
            await query.answer("❌ Error starting target setup")
    
    async def show_delete_target_list(self, query: types.CallbackQuery):
        """Show list of targets for deletion"""
        try:
            # Get targets with group info
            targets = await self.db.fetch("""
                SELECT t.*, g.title as group_title, g.tg_chat_id as group_chat_id
                FROM targets t
                JOIN groups g ON g.id = t.group_id
                ORDER BY g.title, t.dest_chat_id
            """)
            
            if not targets:
                await query.answer("❌ No targets to delete")
                return
            
            text = "<b>🗑️ Delete Target</b>\n\n"
            text += "Select a target to delete:"
            
            keyboard_rows = []
            current_group = None
            for target in targets:
                group_name = target['group_title'] or f"Chat {target['group_chat_id']}"
                if current_group != group_name:
                    # Add group header if we have targets
                    if keyboard_rows:
                        keyboard_rows.append([InlineKeyboardButton(text=" ", callback_data="ignore")])
                    current_group = group_name
                
                button_text = f"{group_name} → {target['dest_chat_id']}"
                if len(button_text) > 40:
                    button_text = button_text[:37] + "..."
                
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=button_text,
                        callback_data=f"targets:delete:{target['id']}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:targets")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing delete target list: {e}")
            await query.answer("❌ Error loading targets for deletion")
    
    async def delete_target(self, query: types.CallbackQuery, target_id: int):
        """Delete a specific target"""
        try:
            # Get target info before deletion
            target = await self.db.fetchrow("""
                SELECT t.*, g.title as group_title, g.tg_chat_id as group_chat_id
                FROM targets t
                JOIN groups g ON g.id = t.group_id
                WHERE t.id = $1
            """, target_id)
            
            if not target:
                await query.answer("❌ Target not found")
                return
            
            # Delete the target
            result = await self.db.execute(
                "DELETE FROM targets WHERE id = $1", target_id
            )
            
            group_name = target['group_title'] or f"Chat {target['group_chat_id']}"
            
            text = f"✅ <b>Target Deleted</b>\n\n"
            text += f"Group: {group_name}\n"
            text += f"Target Chat ID: <code>{target['dest_chat_id']}</code>\n\n"
            text += "This target will no longer receive call messages."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 View Targets", callback_data="menu:targets")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Target deleted successfully")
            
        except Exception as e:
            logger.error(f"Error deleting target: {e}")
            await query.answer("❌ Error deleting target")
