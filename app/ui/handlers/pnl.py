"PNL Forwarding UI Handler - Manages the button-based wizard for creating PNL forwarding rules."

import logging
import traceback
from aiogram import types
from aiogram.fsm.context import FSMContext
from typing import Dict, Any, List

from app.models import PnlForwardingRuleModel, GroupModel, BotModel
from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)

class PnlHandler:
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.pnl_model = PnlForwardingRuleModel(db)
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)

    async def handle_pnl_action(self, query: types.CallbackQuery, state: FSMContext):
        try:
            action = query.data.split(':')[1]
            logger.debug(f'Handling PNL action: {action}')

            if action == 'list':
                await self.show_rules_list(query)
            elif action == 'add':
                await self.start_add_rule_wizard(query, state)
            elif action == 'view':
                rule_id = int(query.data.split(':')[2])
                await self.show_rule_details(query, rule_id)
            elif action == 'toggle':
                rule_id = int(query.data.split(':')[2])
                await self.toggle_rule_enabled(query, rule_id)
            elif action == 'delete':
                rule_id = int(query.data.split(':')[2])
                await self.confirm_delete_rule(query, rule_id)
            elif action == 'confirm_delete':
                rule_id = int(query.data.split(':')[2])
                await self.delete_rule(query, rule_id)
            elif action == 'manage_command_users':
                rule_id = int(query.data.split(':')[2])
                await self.edit_command_users(query, state, rule_id)
            elif action == 'manage_reply_users':
                rule_id = int(query.data.split(':')[2])
                await self.edit_reply_users(query, state, rule_id)
            elif action == 'set_fwd_bot':
                rule_id = int(query.data.split(':')[2])
                await self.show_forwarding_bot_selection(query, state, rule_id)
            # Wizard actions
            elif action == 'wizard_source_group':
                await self.wizard_process_source_group(query, state)
            elif action == 'wizard_add_monitored':
                await self.wizard_prompt_for_user_id(query, state, 'monitored')
            elif action == 'wizard_remove_monitored':
                user_id = int(query.data.split(':')[2])
                await self.wizard_remove_user(query, state, 'monitored', user_id)
            elif action == 'wizard_next_to_fwd_bot':
                await self.wizard_show_forwarding_bot_selection(query, state)
            elif action == 'wizard_fwd_bot':
                await self.wizard_process_forwarding_bot(query, state)
            elif action == 'wizard_next_to_destination':
                await self.wizard_prompt_for_destination(query, state)
            elif action == 'wizard_add_replying':
                await self.wizard_prompt_for_user_id(query, state, 'replying')
            elif action == 'wizard_remove_replying':
                user_id = int(query.data.split(':')[2])
                await self.wizard_remove_user(query, state, 'replying', user_id)
            elif action == 'wizard_next_to_summary':
                await self.wizard_show_summary(query, state)
            elif action == 'wizard_save':
                await self.save_rule(query, state)
            else:
                logger.warning(f'Unknown PNL action: {action}')
                await query.answer('❌ Unknown action', show_alert=True)
        except Exception as e:
            logger.error(f'Error in handle_pnl_action: {e}\n{traceback.format_exc()}')
            await query.answer('❌ An error occurred. Please try again.', show_alert=True)

    async def show_rules_list(self, query: types.CallbackQuery):
        logger.debug('Showing PNL rules list')
        try:
            rules_records = await self.pnl_model.get_all_with_details()
            rules = []
            for record in rules_records:
                rule_dict = dict(record)
                dest_info = await self._get_entity_info(query, rule_dict['destination_channel_id'])
                rule_dict['destination_channel_title'] = dest_info['title']
                rules.append(rule_dict)
            
            keyboard = self.keyboards.pnl_rules_list(rules)
            text = f'<b>💸 PNL Forwarding Rules ({len(rules)})</b>\n\nManage rules for forwarding replies to /pnl commands.'
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer()
        except Exception as e:
            logger.error(f'Error in show_rules_list: {e}\n{traceback.format_exc()}')
            await query.answer('❌ An error occurred. Please try again.', show_alert=True)

    async def show_rule_details(self, query: types.CallbackQuery, rule_id: int):
        logger.debug(f'Showing details for PNL rule {rule_id}')
        try:
            rule = await self.pnl_model.get_by_id(rule_id)
            if not rule: 
                logger.warning(f'Rule {rule_id} not found')
                return await query.answer('Rule not found.')
            
            source_group = {'title': rule['source_group_title']}
            
            dest_channel_info = await self._get_entity_info(query, rule['destination_channel_id'])
            fwd_bot = await self.bot_model.get_by_id(rule['forwarding_userbot_id'])
            text = self.keyboards.pnl_rule_details_text(rule, source_group, dest_channel_info, fwd_bot)
            keyboard = self.keyboards.pnl_rule_details_menu(rule)
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer()
        except Exception as e:
            logger.error(f'Error in show_rule_details: {e}\n{traceback.format_exc()}')
            await query.answer('❌ An error occurred. Please try again.', show_alert=True)

    async def toggle_rule_enabled(self, query: types.CallbackQuery, rule_id: int):
        logger.debug(f'Toggling PNL rule {rule_id}')
        try:
            new_status = await self.pnl_model.toggle_enabled(rule_id)
            await query.answer(f'✅ Rule has been {"enabled" if new_status else "disabled"}.')
            await self.show_rule_details(query, rule_id)
        except Exception as e:
            logger.error(f'Error in toggle_rule_enabled: {e}\n{traceback.format_exc()}')
            await query.answer('❌ An error occurred. Please try again.', show_alert=True)

    async def confirm_delete_rule(self, query: types.CallbackQuery, rule_id: int):
        logger.debug(f'Confirming deletion for PNL rule {rule_id}')
        try:
            rule = await self.pnl_model.get_by_id(rule_id)
            if not rule:
                return await query.answer('Rule not found.')
            
            text = f"<b>🗑️ Confirm Deletion</b>\n\nAre you sure you want to delete the PNL rule for source group {rule['source_group_id']}?"
            keyboard = self.keyboards.pnl_confirm_delete(rule_id)
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer()
        except Exception as e:
            logger.error(f'Error in confirm_delete_rule: {e}\n{traceback.format_exc()}')
            await query.answer('❌ An error occurred. Please try again.', show_alert=True)

    async def delete_rule(self, query: types.CallbackQuery, rule_id: int):
        logger.debug(f'Deleting PNL rule {rule_id}')
        try:
            await self.pnl_model.delete(rule_id)
            await query.message.edit_text('✅ PNL Forwarding Rule deleted successfully!')
            await self.show_rules_list(query)
        except Exception as e:
            logger.error(f'Error in delete_rule: {e}\n{traceback.format_exc()}')
            await query.answer('❌ An error occurred. Please try again.', show_alert=True)

    async def show_forwarding_bot_selection(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        rule = await self.pnl_model.get_by_id(rule_id)
        if not rule:
            return await query.answer("Rule not found.")
        await state.set_data({'rule_id': rule_id})
        await self.wizard_show_forwarding_bot_selection(query, state)

    async def edit_command_users(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        rule = await self.pnl_model.get_by_id(rule_id)
        if not rule:
            return await query.answer("Rule not found.")
        await state.set_data({'monitored_users': rule.get('allowed_pnl_command_user_ids', []) or [], 'rule_id': rule_id})
        await self.wizard_show_monitored_users_menu(query, state)

    async def edit_reply_users(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        rule = await self.pnl_model.get_by_id(rule_id)
        if not rule:
            return await query.answer("Rule not found.")
        await state.set_data({'replying_users': rule.get('allowed_reply_user_ids', []) or [], 'rule_id': rule_id})
        await self.wizard_show_replying_users_menu(query, state)

    async def start_add_rule_wizard(self, query: types.CallbackQuery, state: FSMContext):
        await state.clear()
        groups = await self.group_model.get_enabled_groups()
        if not groups:
            return await query.answer('❌ No groups available. Please add a group first.', show_alert=True)
        text = '<b>➕ Add PNL Rule (1/6)</b>\n\nSelect the <b>Source Group</b> where the /pnl command will be monitored:'
        keyboard = self.keyboards.pnl_select_source_group_keyboard(groups)
        await query.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(ManagementStates.pnl_add_rule_source_group)

    async def wizard_process_source_group(self, query: types.CallbackQuery, state: FSMContext):
        group_id = int(query.data.split(':')[2])
        await state.update_data(source_group_id=group_id)
        await self.wizard_show_monitored_users_menu(query, state)

    async def wizard_show_monitored_users_menu(self, query_or_message: types.Message | types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        monitored_users = data.get('monitored_users', [])
        text = f'<b>➕ Add PNL Rule (2/6)</b>\n\nWhose /pnl commands should be tracked?'
        text += '\n\n<b>Monitored Users:</b>\n' + (', '.join(map(str, monitored_users)) if monitored_users else 'Anyone')
        keyboard = self.keyboards.pnl_manage_users_keyboard(monitored_users, 'monitored', rule_id=data.get('rule_id'))
        if isinstance(query_or_message, types.Message):
            await query_or_message.answer(text, reply_markup=keyboard)
        else:
            await query_or_message.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(ManagementStates.pnl_add_rule_monitored_users)

    async def wizard_prompt_for_user_id(self, query: types.CallbackQuery, state: FSMContext, user_type: str):
        await query.message.edit_text(f'Enter User ID(s) to add (comma-separated):')
        await state.update_data(user_type=user_type)
        if user_type == 'monitored':
            await state.set_state(ManagementStates.pnl_add_monitored_user_id)
        else:
            await state.set_state(ManagementStates.pnl_add_replying_user_id)

    async def wizard_process_user_id_input(self, message: types.Message, state: FSMContext):
        try:
            user_ids = [int(uid.strip()) for uid in message.text.split(',')]
            data = await state.get_data()
            user_type = data.get('user_type')
            current_users = data.get(f'{user_type}_users', [])
            current_users.extend(user_ids)
            await state.update_data({f'{user_type}_users': list(set(current_users))})
            await message.delete()
            if user_type == 'monitored':
                await self.wizard_show_monitored_users_menu(message, state)
            else:
                await self.wizard_show_replying_users_menu(message, state)
        except ValueError:
            await message.answer('Invalid User ID(s). Please enter number(s) separated by commas.')

    async def wizard_remove_user(self, query: types.CallbackQuery, state: FSMContext, user_type: str, user_id: int):
        data = await state.get_data()
        current_users = data.get(f'{user_type}_users', [])
        if user_id in current_users:
            current_users.remove(user_id)
        await state.update_data({f'{user_type}_users': current_users})

        # Immediately update the database
        rule_id = data.get('rule_id')
        if rule_id:
            update_data = {}
            if user_type == 'monitored':
                update_data['allowed_pnl_command_user_ids'] = current_users
            else:
                update_data['allowed_reply_user_ids'] = current_users
            await self.pnl_model.update(rule_id, update_data)

        if user_type == 'monitored':
            await self.wizard_show_monitored_users_menu(query, state)
        else:
            await self.wizard_show_replying_users_menu(query, state)

    async def wizard_show_forwarding_bot_selection(self, query: types.CallbackQuery, state: FSMContext):
        userbots = await self.bot_model.get_active_userbots()
        text = '<b>➕ Add PNL Rule (3/6)</b>\n\nSelect the <b>Userbot</b> that will forward the reply:'
        keyboard = self.keyboards.pnl_select_forwarding_bot_keyboard(userbots)
        await query.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(ManagementStates.pnl_add_rule_forwarding_bot)

    async def wizard_process_forwarding_bot(self, query: types.CallbackQuery, state: FSMContext):
        bot_id = int(query.data.split(':')[2])
        await state.update_data(forwarding_userbot_id=bot_id)
        data = await state.get_data()
        if data.get('rule_id'):
            # If editing, save and return to details
            await self.pnl_model.update(data['rule_id'], {'forwarding_userbot_id': bot_id})
            await state.clear()
            await self.show_rule_details(query, data['rule_id'])
        else:
            # If creating, continue wizard
            await self.wizard_prompt_for_destination(query, state)

    async def wizard_prompt_for_destination(self, query: types.CallbackQuery, state: FSMContext):
        await query.message.edit_text('<b>➕ Add PNL Rule (4/6)</b>\n\nEnter the ID of the <b>Destination Channel</b>:')
        await state.set_state(ManagementStates.pnl_add_rule_destination)

    async def wizard_process_destination_input(self, message: types.Message, state: FSMContext):
        try:
            channel_id = int(message.text)
            await state.update_data(destination_channel_id=channel_id)
            await message.delete()
            await self.wizard_show_replying_users_menu(message, state)
        except ValueError:
            await message.answer('Invalid Channel ID. Please enter a number.')

    async def wizard_show_replying_users_menu(self, query_or_message: types.Message | types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        replying_users = data.get('replying_users', [])
        text = f'<b>➕ Add PNL Rule (5/6)</b>\n\nWhose replies should be forwarded?'
        text += '\n\n<b>Replying Users:</b>\n' + (', '.join(map(str, replying_users)) if replying_users else 'Anyone')
        keyboard = self.keyboards.pnl_manage_users_keyboard(replying_users, 'replying', rule_id=data.get('rule_id'))
        if isinstance(query_or_message, types.Message):
            await query_or_message.answer(text, reply_markup=keyboard)
        else:
            await query_or_message.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(ManagementStates.pnl_add_rule_replying_users)

    async def wizard_show_summary(self, query: types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        source_group = await self.group_model.get_by_id(data.get('source_group_id'))
        fwd_bot = await self.bot_model.get_by_id(data.get('forwarding_userbot_id'))
        dest_channel_info = await self._get_entity_info(query, data.get('destination_channel_id'))

        text = f'<b>➕ Add PNL Rule (6/6) - Summary</b>\n\n'
        text += f'<b>Source Group:</b> {source_group['title']}\n'
        text += f'<b>Monitored Users:</b> {data.get('monitored_users', []) or 'Anyone'}\n'
        text += f'<b>Forwarding Bot:</b> {fwd_bot['display_name']}\n'
        text += f'<b>Destination Channel:</b> {dest_channel_info['title']}\n'
        text += f'<b>Replying Users:</b> {data.get('replying_users', []) or 'Anyone'}'

        keyboard = self.keyboards.pnl_rule_summary_keyboard()
        await query.message.edit_text(text, reply_markup=keyboard)
        await state.set_state(ManagementStates.pnl_add_rule_summary)

    async def save_rule(self, query: types.CallbackQuery, state: FSMContext):
        data = await state.get_data()
        rule_id = data.get('rule_id')
        if rule_id:
            # Update existing rule
            update_data = {}
            if 'monitored_users' in data:
                update_data['allowed_pnl_command_user_ids'] = data['monitored_users']
            if 'replying_users' in data:
                update_data['allowed_reply_user_ids'] = data['replying_users']
            
            if update_data:
                await self.pnl_model.update(rule_id, update_data)
        else:
            # Create new rule
            await self.pnl_model.create_rule(
                source_group_id=data['source_group_id'],
                destination_channel_id=data['destination_channel_id'],
                allowed_pnl_command_user_ids=data.get('monitored_users', []),
                allowed_reply_user_ids=data.get('replying_users', []),
                forwarding_userbot_id=data['forwarding_userbot_id']
            )
        await state.clear()
        await query.message.edit_text('✅ PNL Forwarding Rule saved successfully!')
        await self.show_rules_list(query)

    async def _get_entity_info(self, query_or_message, entity_id: int) -> Dict[str, Any]:
        bot = query_or_message.bot if hasattr(query_or_message, 'bot') else query_or_message.bot
        try:
            chat = await bot.get_chat(entity_id)
            return {'id': chat.id, 'title': chat.title or chat.full_name}
        except Exception:
            return {'id': entity_id, 'title': f'ID: {entity_id}'}
