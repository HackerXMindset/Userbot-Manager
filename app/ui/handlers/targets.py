from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
import logging

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models import GroupModel

logger = logging.getLogger(__name__)

class TargetsHandler:
    """Handler for target management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.group_model = GroupModel(db)
    
    async def handle_target_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle target actions"""
        parts = query.data.split(':', 2)
        action = parts[1]
        
        if action == 'add':
            await self.start_add_target(query, state)
        elif action == 'select_group':
            group_id = int(parts[2])
            await self.prompt_for_target_chat_id(query, state, group_id)
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
            # Get all targets with group information
            targets = await self.db.fetch("""
                SELECT t.*, g.title as group_title, g.tg_chat_id as group_tg_chat_id
                FROM targets t
                LEFT JOIN groups g ON g.id = t.group_id
                ORDER BY g.title, t.dest_chat_id
            """)
            
            text = "<b>🎯 Targets Overview</b>\n\n"
            
            if not targets:
                text += "No targets configured.\nTargets are the channels where calls are sent."
            else:
                text += f"<b>Available Targets ({len(targets)}):</b>\n\n"
                for i, target in enumerate(targets, 1):
                    group_name = target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"
                    text += f"{i}. <code>{target['dest_chat_id']}</code>\n"
                    text += f"   └ Group: {group_name}\n\n"
            
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

    async def start_add_target(self, query: types.CallbackQuery, state: FSMContext):
        """Start adding a target - first select which group"""
        try:
            # Get available groups
            groups = await self.db.fetch("SELECT * FROM groups WHERE enabled = true ORDER BY title")
            
            if not groups:
                await query.answer("❌ No groups available. Create a group first.")
                return
            
            text = (
                "<b>➕ Add Target</b>\n\n"
                "First, select which group this target belongs to:"
            )
            
            keyboard_rows = []
            for group in groups:
                group_name = group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"👥 {group_name}", 
                        callback_data=f"targets:select_group:{group['id']}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:targets")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error starting add target: {e}")
            await query.answer("❌ Error starting target setup")
    
    async def prompt_for_target_chat_id(self, query: types.CallbackQuery, state: FSMContext, group_id: int):
        """Prompt for target chat ID after group selection"""
        try:
            # Get group details
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = (
                f"<b>➕ Add Target for {group_name}</b>\n\n"
                "Now enter the target chat ID where calls should be sent.\n\n"
                "<b>Examples:</b>\n"
                "• Channel: -1001234567890\n"
                "• Group: -1001234567890\n"
                "• Your private chat ID\n\n"
                "Type /cancel to abort."
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back", callback_data="targets:add")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.adding_target.state)
            await state.update_data(message_id=query.message.message_id, group_id=group_id)
            
        except Exception as e:
            logger.error(f"Error prompting for target chat ID: {e}")
            await query.answer("❌ Error setting up target input")
    
    async def show_delete_target_list(self, query: types.CallbackQuery):
        """Show list of targets for deletion"""
        try:
            # Get all targets with group information
            targets = await self.db.fetch("""
                SELECT t.*, g.title as group_title, g.tg_chat_id as group_tg_chat_id
                FROM targets t
                LEFT JOIN groups g ON g.id = t.group_id
                ORDER BY g.title, t.dest_chat_id
            """)
            
            if not targets:
                await query.answer("❌ No targets to delete")
                return
            
            text = "<b>🗑️ Delete Target</b>\n\n"
            text += "Select a target to delete:"
            
            keyboard_rows = []
            for target in targets:
                group_name = target['group_title'] or f"Chat {target['group_tg_chat_id']}" if target['group_tg_chat_id'] else "No Group"
                button_text = f"🗑️ {target['dest_chat_id']} ({group_name})"
                if len(button_text) > 35:
                    button_text = button_text[:32] + "..."
                
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
            target = await self.db.fetchrow(
                "SELECT * FROM targets WHERE id = $1", target_id
            )
            
            if not target:
                await query.answer("❌ Target not found")
                return
            
            # Delete the target
            result = await self.db.execute(
                "DELETE FROM targets WHERE id = $1", target_id
            )
            
            text = f"✅ <b>Target Deleted</b>\n\n"
            text += f"Target Chat ID: <code>{target['dest_chat_id']}</code>\n\n"
            text += "This target has been removed from the system."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 View Targets", callback_data="menu:targets")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Target deleted successfully")
            
        except Exception as e:
            logger.error(f"Error deleting target: {e}")
            await query.answer("❌ Error deleting target")

    async def process_target_input(self, message: types.Message, state: FSMContext):
        """Process target addition input"""
        if message.text == '/cancel':
            await state.clear()
            await message.answer(
                "Target addition cancelled.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 Targets Menu", callback_data="menu:targets")]
                ])
            )
            return
        
        try:
            # Get state data
            data = await state.get_data()
            group_id = data.get('group_id')
            
            if not group_id:
                await message.answer("❌ Error: No group selected. Please try again.")
                await state.clear()
                return
            
            # Parse input - should be a chat ID
            text = message.text.strip()
            
            # Try to convert to integer (chat ID)
            try:
                chat_id = int(text)
            except ValueError:
                await message.answer(
                    "❌ Invalid input. Please enter a valid chat ID (numbers only).\n\n"
                    "Example: -1001234567890"
                )
                return
            
            # Check if target already exists for this group
            existing = await self.db.fetchval(
                "SELECT id FROM targets WHERE group_id = $1 AND dest_chat_id = $2", 
                group_id, chat_id
            )
            
            if existing:
                await message.answer(
                    f"❌ Target <code>{chat_id}</code> already exists for this group!"
                )
                return
            
            # Get group info for confirmation
            group = await self.db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            # Add target to database with proper group association
            result = await self.db.fetchrow(
                "INSERT INTO targets (group_id, dest_chat_id, created_at) VALUES ($1, $2, NOW()) RETURNING *",
                group_id, chat_id
            )
            
            await message.answer(
                f"✅ <b>Target Added Successfully!</b>\n\n"
                f"Group: <b>{group_name}</b>\n"
                f"Target ID: {result['id']}\n"
                f"Chat ID: <code>{result['dest_chat_id']}</code>\n\n"
                f"This group can now forward calls to this target.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 View Targets", callback_data="menu:targets")],
                    [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
                ])
            )
            
        except Exception as e:
            logger.error(f"Error adding target: {e}")
            await message.answer(f"❌ Error adding target: {e}")
        
        finally:
            await state.clear()
