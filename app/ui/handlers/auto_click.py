from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models.auto_button_click import AutoButtonClickRuleModel
from app.models.group import GroupModel

logger = logging.getLogger(__name__)

class AutoClickHandler:
    """Handler for auto click management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.rule_model = AutoButtonClickRuleModel(db)
        self.group_model = GroupModel(db)
    
    async def show_auto_click_menu(self, query: types.CallbackQuery):
        """Display auto click management menu"""
        try:
            rules = await self.rule_model.get_all_rules()
            text = f"<b>🖱️ Auto Click Rules ({len(rules)})</b>\n\n"
            text += "Manage rules for automatically clicking buttons in bot replies."
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.auto_click_menu(rules)
            )
        except Exception as e:
            logger.error(f"Error showing auto click menu: {e}")
            await query.answer("❌ Error loading auto click rules")

    async def handle_auto_click_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle auto click related callbacks"""
        parts = query.data.split(':')
        action = parts[1]
        
        if action == 'list':
            await self.show_auto_click_menu(query)
        elif action == 'add':
            await self.start_add_rule(query, state)
        elif action == 'view':
            rule_id = int(parts[2])
            await self.show_rule_details(query, rule_id)
        elif action == 'toggle':
            rule_id = int(parts[2])
            await self.toggle_rule(query, rule_id)
        elif action == 'delete':
            rule_id = int(parts[2])
            await self.delete_rule(query, rule_id)

    async def start_add_rule(self, query: types.CallbackQuery, state: FSMContext):
        """Start the add rule wizard"""
        await state.clear()
        targets = await self.group_model.get_targets_with_group_info()
        if not targets:
            await query.answer("❌ No target groups found. Add groups and targets first.", show_alert=True)
            return

        text = "<b>➕ Add Auto Click Rule (1/3)</b>\n\nSelect the <b>Target Group</b> where the userbot posts messages:"
        
        keyboard = []
        for target in targets:
            dest_name = target['dest_group_display_name'] or target['dest_group_title'] or target['dest_chat_id']
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{dest_name}",
                    callback_data=f"auto_click_wizard:target:{target['dest_chat_id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="auto_click:list")])
        
        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.set_state(ManagementStates.adding_auto_click_rule_target)

    async def wizard_process_target_group(self, query: types.CallbackQuery, state: FSMContext):
        target_chat_id = int(query.data.split(':')[2])
        await state.update_data(target_chat_id=target_chat_id)
        
        text = "<b>➕ Add Auto Click Rule (2/3)</b>\n\nEnter the User ID of the bot that will reply:"
        await query.message.edit_text(text, reply_markup=self.keyboards.cancel_button("auto_click:list"))
        await state.set_state(ManagementStates.adding_auto_click_rule_bot_id)

    async def wizard_process_bot_id(self, message: types.Message, state: FSMContext):
        try:
            bot_id = int(message.text)
            await state.update_data(bot_id=bot_id)
            text = "<b>➕ Add Auto Click Rule (3/3)</b>\n\nEnter the exact text of the button to click:"
            await message.answer(text)
            await state.set_state(ManagementStates.adding_auto_click_rule_button_text)
        except ValueError:
            await message.reply("Invalid User ID. Please enter a number.")

    async def wizard_process_button_text(self, message: types.Message, state: FSMContext):
        button_text = message.text
        await state.update_data(button_text=button_text)
        
        data = await state.get_data()
        
        await self.rule_model.create({
            'target_chat_id': data['target_chat_id'],
            'bot_id': data['bot_id'],
            'button_text': data['button_text'],
        })
        
        await message.answer("✅ Auto Click Rule saved successfully!")
        await state.clear()
        # HACK: Need a way to get back to the menu query
        # For now, just send a new message with the menu
        # await self.show_auto_click_menu(message) 

    async def show_rule_details(self, query: types.CallbackQuery, rule_id: int):
        rule = await self.rule_model.get_by_id(rule_id)
        if not rule:
            await query.answer("Rule not found.")
            return

        status = "✅ Enabled" if rule['enabled'] else "❌ Disabled"
        text = f"<b>🖱️ Auto Click Rule Details</b>\n\n"
        text += f"<b>Status:</b> {status}\n"
        text += f"<b>Target Chat:</b> <code>{rule['target_chat_id']}</code>\n"
        text += f"<b>Bot ID:</b> <code>{rule['bot_id']}</code>\n"
        text += f"<b>Button Text:</b> \"{rule['button_text']}\""

        await query.message.edit_text(text, reply_markup=self.keyboards.auto_click_rule_details(rule))

    async def toggle_rule(self, query: types.CallbackQuery, rule_id: int):
        rule = await self.rule_model.get_by_id(rule_id)
        if not rule:
            await query.answer("Rule not found.")
            return
        
        new_status = not rule['enabled']
        await self.rule_model.update(rule_id, {'enabled': new_status})
        await query.answer(f"Rule {'enabled' if new_status else 'disabled'}.")
        await self.show_rule_details(query, rule_id)

    async def delete_rule(self, query: types.CallbackQuery, rule_id: int):
        await self.rule_model.delete(rule_id)
        await query.answer("Rule deleted.")
        await self.show_auto_click_menu(query)

# A helper method is needed in GroupModel to get targets with group info
# I will add this to app/models/group.py
# async def get_targets_with_group_info(self) -> List[asyncpg.Record]:
#     query = """
#         SELECT t.*, g.title as group_title
#         FROM targets t
#         JOIN groups g ON g.id = t.group_id
#         ORDER BY g.title, t.dest_chat_id
#     """
#     return await self.db.fetch(query)
