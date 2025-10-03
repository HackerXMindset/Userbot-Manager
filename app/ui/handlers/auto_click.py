from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import json

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models.auto_button_click import AutoButtonClickRuleModel
from app.models.group import GroupModel
from app.models import BotModel

logger = logging.getLogger(__name__)

class AutoClickHandler:
    """Handler for auto click management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.rule_model = AutoButtonClickRuleModel(db)
        self.group_model = GroupModel(db)
        self.bot_model = BotModel(db)
    
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
        logger.debug(f"[DEBUG] handle_auto_click_action triggered with data: {query.data}")
        parts = query.data.split(':')
        action = parts[1]
        rule_id = int(parts[2]) if len(parts) > 2 else None
        logger.debug(f"[DEBUG] Parsed action: {action}, rule_id: {rule_id}")

        if action == 'list':
            await self.show_auto_click_menu(query)
        elif action == 'add':
            await self.start_add_rule(query, state)
        elif action == 'add_dynamic':
            await self.start_add_dynamic_rule(query, state)
        elif action == 'view':
            logger.debug(f"[DEBUG] Entering action 'view' for rule_id: {rule_id}")
            await self.show_rule_details(query, rule_id)
        elif action == 'toggle':
            await self.toggle_rule(query, rule_id)
        elif action == 'delete':
            await self.delete_rule(query, rule_id)
        elif action == 'edit_name':
            await self.start_edit_name(query, rule_id, state)
        elif action == 'edit_user':
            await self.start_edit_dynamic_user(query, rule_id, state)
        elif action == 'edit_buttons':
            await self.start_edit_dynamic_buttons(query, rule_id, state)
        elif action == 'edit_userbots':
            await self.start_edit_dynamic_userbots(query, rule_id, state)

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

    async def show_rule_details(self, query: types.CallbackQuery, rule_id: int):
        try:
            logger.debug(f"[AUTO_CLICK_DEBUG] === show_rule_details START === rule_id: {rule_id}")

            # Fetch rule
            rule = await self.rule_model.get_by_id(rule_id)
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule fetched: {rule}")

            if not rule:
                logger.error(f"[AUTO_CLICK_DEBUG] Rule {rule_id} not found in database")
                await query.answer("❌ Rule not found.", show_alert=True)
                return

            logger.debug(f"[AUTO_CLICK_DEBUG] Rule keys: {rule.keys()}")
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule type from DB: {type(rule)}")

            # Basic fields
            status = "✅ Enabled" if rule['enabled'] else "❌ Disabled"
            rule_type = rule.get('rule_type', 'static')
            rule_name = rule.get('name')
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule type: {rule_type}, Status: {status}, Name: {rule_name}")

            # Show name in title if available
            if rule_name:
                text = f"<b>{rule_name}</b> (ID: {rule_id})\n\n"
            else:
                text = f"<b>Rule Details (ID: {rule_id})</b>\n\n"

            if rule_type == 'dynamic':
                logger.debug(f"[AUTO_CLICK_DEBUG] Processing DYNAMIC rule")
                text += f"<b>Type:</b> 🔄 Dynamic Click\n"
                text += f"<b>Status:</b> {status}\n"
                text += f"<b>Target Chat:</b> <code>{rule['target_chat_id']}</code>\n"
                text += f"<b>Monitored User:</b> <code>{rule['user_id']}</code>\n"

                # Handle clicking_userbot_ids
                clicking_userbot_ids_raw = rule.get('clicking_userbot_ids', [])
                logger.debug(f"[AUTO_CLICK_DEBUG] clicking_userbot_ids_raw: {clicking_userbot_ids_raw}, type: {type(clicking_userbot_ids_raw)}")

                clicking_userbot_ids = []
                if clicking_userbot_ids_raw:
                    # Handle if it's a JSON string
                    if isinstance(clicking_userbot_ids_raw, str):
                        try:
                            import json
                            clicking_userbot_ids = json.loads(clicking_userbot_ids_raw)
                            logger.debug(f"[AUTO_CLICK_DEBUG] Parsed clicking_userbot_ids from JSON string: {clicking_userbot_ids}")
                        except json.JSONDecodeError as e:
                            logger.error(f"[AUTO_CLICK_DEBUG] Failed to parse clicking_userbot_ids: {e}")
                            clicking_userbot_ids = []
                    elif isinstance(clicking_userbot_ids_raw, list):
                        clicking_userbot_ids = clicking_userbot_ids_raw
                        logger.debug(f"[AUTO_CLICK_DEBUG] clicking_userbot_ids already a list: {clicking_userbot_ids}")
                    else:
                        logger.error(f"[AUTO_CLICK_DEBUG] Unexpected type for clicking_userbot_ids: {type(clicking_userbot_ids_raw)}")

                if clicking_userbot_ids:
                    logger.debug(f"[AUTO_CLICK_DEBUG] Fetching bots for IDs: {clicking_userbot_ids}")
                    try:
                        bots = await self.bot_model.get_bots_by_ids(clicking_userbot_ids)
                        logger.debug(f"[AUTO_CLICK_DEBUG] Bots fetched: {bots}")
                        bot_names = [b.get('display_name', f"ID: {b['id']}") for b in bots]
                        text += "<b>Clicking Userbots:</b>\n"
                        for name in bot_names:
                            text += f"  • {name}\n"
                    except Exception as bot_error:
                        logger.error(f"[AUTO_CLICK_DEBUG] Error fetching bots: {bot_error}", exc_info=True)
                        text += f"<b>Clicking Userbots:</b> Error loading (IDs: {clicking_userbot_ids})\n"
                else:
                    text += "<b>Clicking Userbots:</b> None\n"

                # Handle button_texts
                button_texts_raw = rule.get('button_texts', [])
                logger.debug(f"[AUTO_CLICK_DEBUG] button_texts_raw: {button_texts_raw}, type: {type(button_texts_raw)}")

                button_texts = []
                if button_texts_raw:
                    # Handle if it's a JSON string
                    if isinstance(button_texts_raw, str):
                        try:
                            import json
                            button_texts = json.loads(button_texts_raw)
                            logger.debug(f"[AUTO_CLICK_DEBUG] Parsed button_texts from JSON string: {button_texts}")
                        except json.JSONDecodeError as e:
                            logger.error(f"[AUTO_CLICK_DEBUG] Failed to parse button_texts: {e}")
                            button_texts = []
                    elif isinstance(button_texts_raw, list):
                        button_texts = button_texts_raw
                        logger.debug(f"[AUTO_CLICK_DEBUG] button_texts already a list: {button_texts}")
                    else:
                        logger.error(f"[AUTO_CLICK_DEBUG] Unexpected type for button_texts: {type(button_texts_raw)}")

                if button_texts:
                    text += f"<b>Button Texts:</b>\n"
                    for btn_text in button_texts:
                        text += f"  • \"{btn_text}\"\n"
                else:
                    text += f"<b>Button Texts:</b> None\n"

            else:
                logger.debug(f"[AUTO_CLICK_DEBUG] Processing STATIC rule")
                text += f"<b>Type:</b> 📍 Static Click\n"
                text += f"<b>Status:</b> {status}\n"
                text += f"<b>Target Chat:</b> <code>{rule['target_chat_id']}</code>\n"
                text += f"<b>Replying Bot:</b> <code>{rule['bot_id']}</code>\n"
                text += f"<b>Button Text:</b> \"{rule['button_text']}\""

            logger.debug(f"[AUTO_CLICK_DEBUG] Text prepared successfully, length: {len(text)}")
            logger.debug(f"[AUTO_CLICK_DEBUG] Calling keyboards.auto_click_rule_details...")

            keyboard = self.keyboards.auto_click_rule_details(rule)
            logger.debug(f"[AUTO_CLICK_DEBUG] Keyboard created successfully")

            await query.message.edit_text(text, reply_markup=keyboard)
            logger.debug(f"[AUTO_CLICK_DEBUG] === show_rule_details SUCCESS ===")

        except Exception as e:
            logger.error(f"[AUTO_CLICK_DEBUG] ❌ EXCEPTION in show_rule_details for rule {rule_id}: {e}", exc_info=True)
            try:
                await query.answer(f"❌ Error loading rule: {str(e)[:100]}", show_alert=True)
            except:
                pass

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

    # Dynamic Click Wizard Methods
    async def start_add_dynamic_rule(self, query: types.CallbackQuery, state: FSMContext):
        """Start the add dynamic rule wizard"""
        await state.clear()
        targets = await self.group_model.get_targets_with_group_info()
        if not targets:
            await query.answer("❌ No target groups found. Add groups and targets first.", show_alert=True)
            return

        text = "<b>➕ Add Dynamic Click Rule (1/4)</b>\n\nSelect the <b>Target Group</b> where you want to monitor messages:"

        keyboard = []
        for target in targets:
            dest_name = target['dest_group_display_name'] or target['dest_group_title'] or target['dest_chat_id']
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{dest_name}",
                    callback_data=f"auto_click_dynamic_wizard:target:{target['dest_chat_id']}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="❌ Cancel", callback_data="auto_click:list")])

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
        await state.set_state(ManagementStates.adding_dynamic_click_rule_target)

    async def wizard_process_dynamic_target(self, query: types.CallbackQuery, state: FSMContext):
        """Process dynamic rule target selection"""
        target_chat_id = int(query.data.split(':')[2])
        await state.update_data(target_chat_id=target_chat_id)

        text = "<b>➕ Add Dynamic Click Rule (2/4)</b>\n\nEnter the <b>User ID</b> whose messages you want to monitor:"
        await query.message.edit_text(text, reply_markup=self.keyboards.cancel_button("auto_click:list"))
        await state.set_state(ManagementStates.adding_dynamic_click_rule_user_id)

    async def wizard_process_dynamic_user_id(self, message: types.Message, state: FSMContext):
        """Process dynamic rule user ID input"""
        try:
            user_id = int(message.text)
            await state.update_data(user_id=user_id)
            text = "<b>➕ Add Dynamic Click Rule (3/4)</b>\n\nEnter the button texts separated by commas:\n<i>Example: Buy, Sell, Chart</i>"
            await message.answer(text)
            await state.set_state(ManagementStates.adding_dynamic_click_rule_buttons)
        except ValueError:
            await message.reply("Invalid User ID. Please enter a number.")

    async def wizard_process_dynamic_buttons(self, message: types.Message, state: FSMContext):
        """Process dynamic rule button texts input and show userbot multi-selection"""
        button_text_input = message.text
        button_texts = [btn.strip() for btn in button_text_input.split(',') if btn.strip()]

        if not button_texts:
            await message.reply("No valid button texts found. Please enter at least one button text.")
            return

        # Initialize state for multi-selection
        await state.update_data(button_texts=button_texts, selected_userbots=[])

        userbots = await self.bot_model.get_active_userbots()
        if not userbots:
            await message.answer(
                "❌ No userbots found. Please add a userbot first.",
                reply_markup=self.keyboards.back_button("auto_click:list")
            )
            await state.clear()
            return

        text = f"<b>➕ Add Dynamic Click Rule (4/4)</b>\n\nSelect which userbot(s) will click the buttons:\n\n<b>Buttons to click:</b>\n"
        for btn in button_texts:
            text += f"  • \"{btn}\"\n"

        await message.answer(text, reply_markup=self.keyboards.dynamic_click_select_userbot_keyboard(userbots, []))
        await state.set_state(ManagementStates.adding_dynamic_click_rule_userbot)

    async def wizard_toggle_dynamic_userbot(self, query: types.CallbackQuery, state: FSMContext):
        """Handle toggling a userbot in the multi-selection wizard"""
        try:
            bot_id_to_toggle = int(query.data.split(':')[2])
            
            data = await state.get_data()
            selected_ids = data.get('selected_userbots', [])
            
            if bot_id_to_toggle in selected_ids:
                selected_ids.remove(bot_id_to_toggle)
            else:
                selected_ids.append(bot_id_to_toggle)
            
            await state.update_data(selected_userbots=selected_ids)
            
            userbots = await self.bot_model.get_active_userbots()
            await query.message.edit_reply_markup(
                reply_markup=self.keyboards.dynamic_click_select_userbot_keyboard(userbots, selected_ids)
            )
            await query.answer()

        except Exception as e:
            logger.error(f"Error toggling dynamic userbot selection: {e}", exc_info=True)
            await query.answer("❌ An error occurred.", show_alert=True)

    async def wizard_save_dynamic_rule(self, query: types.CallbackQuery, state: FSMContext):
        """Save the dynamic click rule after confirming userbot selection."""
        logger.debug(f"[DEBUG] wizard_save_dynamic_rule triggered with data: {query.data}")
        try:
            data = await state.get_data()
            logger.debug(f"[DEBUG] State data retrieved: {data}")

            clicking_userbot_ids = data.get('selected_userbots', [])
            if not clicking_userbot_ids:
                await query.answer("Please select at least one userbot.", show_alert=True)
                return

            # For consistency with the model, we'll name the key clicking_userbot_ids
            await state.update_data(clicking_userbot_ids=clicking_userbot_ids)
            final_data = await state.get_data()

            if not all(k in final_data for k in ['target_chat_id', 'user_id', 'button_texts', 'clicking_userbot_ids']):
                logger.error(f"[DEBUG] Missing data in state. Cannot create rule. Data: {final_data}")
                await query.message.edit_text("❌ An error occurred due to missing state data. Please try again.")
                await state.clear()
                return

            await self.rule_model.create_dynamic_rule(final_data)
            logger.debug(f"[DEBUG] Successfully created dynamic rule in DB.")

            await query.message.edit_text("✅ Dynamic Click Rule saved successfully!")
            await state.clear()
            logger.debug(f"[DEBUG] State cleared, wizard finished.")
        except Exception as e:
            logger.error(f"[DEBUG] Exception in wizard_save_dynamic_rule: {e}", exc_info=True)
            await query.answer("❌ An unexpected error occurred.", show_alert=True)

    async def start_edit_dynamic_user(self, query: types.CallbackQuery, rule_id: int, state: FSMContext):
        """Start the wizard to edit a dynamic rule's monitored user ID."""
        await state.set_data({'rule_id': rule_id})
        await query.message.edit_text(
            "Please enter the new User ID to monitor:",
            reply_markup=self.keyboards.cancel_button(f"auto_click:view:{rule_id}")
        )
        await state.set_state(ManagementStates.editing_dynamic_click_rule_user_id)

    async def process_edit_dynamic_user(self, message: types.Message, state: FSMContext):
        """Process the new user ID for a dynamic rule."""
        try:
            new_user_id = int(message.text)
            data = await state.get_data()
            rule_id = data['rule_id']

            await self.rule_model.update(rule_id, {'user_id': new_user_id})
            await message.reply("✅ Monitored User ID updated successfully.")

        except (ValueError, TypeError):
            await message.reply("Invalid User ID. Please enter a number.")
        except Exception as e:
            logger.error(f"Error updating dynamic user: {e}", exc_info=True)
            await message.answer("❌ An error occurred while updating the rule.")
        finally:
            await state.clear()
            # Because we can't easily get the original query to call show_rule_details,
            # we will just leave the user to navigate back manually for now.

    async def start_edit_dynamic_buttons(self, query: types.CallbackQuery, rule_id: int, state: FSMContext):
        """Start the wizard to edit a dynamic rule's button texts."""
        await state.set_data({'rule_id': rule_id})
        await query.message.edit_text(
            "Please enter the new button texts, separated by commas:",
            reply_markup=self.keyboards.cancel_button(f"auto_click:view:{rule_id}")
        )
        await state.set_state(ManagementStates.editing_dynamic_click_rule_buttons)

    async def process_edit_dynamic_buttons(self, message: types.Message, state: FSMContext):
        """Process the new button texts for a dynamic rule."""
        try:
            logger.debug(f"[AUTO_CLICK_DEBUG] process_edit_dynamic_buttons START")

            button_text_input = message.text
            logger.debug(f"[AUTO_CLICK_DEBUG] Input text received: '{button_text_input}'")

            button_texts = [btn.strip() for btn in button_text_input.split(',') if btn.strip()]
            logger.debug(f"[AUTO_CLICK_DEBUG] Parsed button texts: {button_texts}")

            if not button_texts:
                logger.warning(f"[AUTO_CLICK_DEBUG] No valid button texts found")
                await message.reply("No valid button texts found. Please enter at least one button text.")
                return

            data = await state.get_data()
            rule_id = data['rule_id']
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule ID from state: {rule_id}")

            # Ensure list is stored as a JSON string
            json_str = json.dumps(button_texts)
            logger.debug(f"[AUTO_CLICK_DEBUG] JSON string to save: '{json_str}'")

            await self.rule_model.update(rule_id, {'button_texts': json_str})
            logger.debug(f"[AUTO_CLICK_DEBUG] Update successful")

            await message.reply("✅ Button texts updated successfully.")

        except Exception as e:
            logger.error(f"[AUTO_CLICK_DEBUG] ❌ EXCEPTION in process_edit_dynamic_buttons: {e}", exc_info=True)
            await message.answer("❌ An error occurred while updating the rule.")
        finally:
            await state.clear()

    async def start_edit_dynamic_userbots(self, query: types.CallbackQuery, rule_id: int, state: FSMContext):
        """Start the wizard to edit the assigned userbots for a dynamic rule."""
        try:
            logger.debug(f"[AUTO_CLICK_DEBUG] start_edit_dynamic_userbots START - rule_id: {rule_id}")

            rule = await self.rule_model.get_by_id(rule_id)
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule fetched: {rule}")

            if not rule:
                logger.error(f"[AUTO_CLICK_DEBUG] Rule {rule_id} not found")
                await query.answer("Rule not found.", show_alert=True)
                return

            current_bot_ids_raw = rule.get('clicking_userbot_ids', [])
            logger.debug(f"[AUTO_CLICK_DEBUG] current_bot_ids_raw: {current_bot_ids_raw}, type: {type(current_bot_ids_raw)}")

            # Handle if it's a JSON string
            current_bot_ids = []
            if current_bot_ids_raw:
                if isinstance(current_bot_ids_raw, str):
                    try:
                        current_bot_ids = json.loads(current_bot_ids_raw)
                        logger.debug(f"[AUTO_CLICK_DEBUG] Parsed from JSON string: {current_bot_ids}")
                    except json.JSONDecodeError as e:
                        logger.error(f"[AUTO_CLICK_DEBUG] Failed to parse current_bot_ids: {e}")
                        current_bot_ids = []
                elif isinstance(current_bot_ids_raw, list):
                    current_bot_ids = current_bot_ids_raw
                    logger.debug(f"[AUTO_CLICK_DEBUG] Already a list: {current_bot_ids}")

            logger.debug(f"[AUTO_CLICK_DEBUG] Setting state with rule_id={rule_id}, current_bot_ids={current_bot_ids}")
            await state.set_data({'rule_id': rule_id, 'selected_userbots': current_bot_ids})

            logger.debug(f"[AUTO_CLICK_DEBUG] Fetching active userbots...")
            userbots = await self.bot_model.get_active_userbots()
            logger.debug(f"[AUTO_CLICK_DEBUG] Active userbots count: {len(userbots) if userbots else 0}")

            if not userbots:
                logger.warning(f"[AUTO_CLICK_DEBUG] No active userbots found")
                await query.message.edit_text(
                    "❌ No active userbots found.",
                    reply_markup=self.keyboards.back_button(f"auto_click:view:{rule_id}")
                )
                return

            text = "<b>✏️ Edit Clicking Userbots</b>\n\nSelect which userbot(s) will click the buttons:"
            logger.debug(f"[AUTO_CLICK_DEBUG] Creating keyboard with {len(userbots)} userbots, selected: {current_bot_ids}")

            keyboard = self.keyboards.dynamic_click_select_userbot_keyboard(userbots, current_bot_ids)
            logger.debug(f"[AUTO_CLICK_DEBUG] Keyboard created")

            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.editing_dynamic_click_rule_userbots)
            logger.debug(f"[AUTO_CLICK_DEBUG] start_edit_dynamic_userbots SUCCESS")

        except Exception as e:
            logger.error(f"[AUTO_CLICK_DEBUG] ❌ EXCEPTION in start_edit_dynamic_userbots: {e}", exc_info=True)
            try:
                await query.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)
            except:
                pass

    async def process_edit_dynamic_userbots(self, query: types.CallbackQuery, state: FSMContext):
        """Process the updated userbot selection and save it."""
        try:
            logger.debug(f"[AUTO_CLICK_DEBUG] process_edit_dynamic_userbots START")

            data = await state.get_data()
            logger.debug(f"[AUTO_CLICK_DEBUG] State data: {data}")

            rule_id = data['rule_id']
            selected_ids = data.get('selected_userbots', [])
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule ID: {rule_id}, Selected IDs: {selected_ids}")

            if not selected_ids:
                logger.warning(f"[AUTO_CLICK_DEBUG] No userbots selected")
                await query.answer("Please select at least one userbot.", show_alert=True)
                return

            # Ensure list is stored as a JSON string
            json_str = json.dumps(selected_ids)
            logger.debug(f"[AUTO_CLICK_DEBUG] JSON string to save: '{json_str}'")

            await self.rule_model.update(rule_id, {'clicking_userbot_ids': json_str})
            logger.debug(f"[AUTO_CLICK_DEBUG] Update successful")

            await query.answer("✅ Clicking Userbots updated successfully.")

        except Exception as e:
            logger.error(f"[AUTO_CLICK_DEBUG] ❌ EXCEPTION in process_edit_dynamic_userbots: {e}", exc_info=True)
            await query.answer("❌ An error occurred.", show_alert=True)
        finally:
            await state.clear()
            await self.show_rule_details(query, data.get('rule_id'))

    async def start_edit_name(self, query: types.CallbackQuery, rule_id: int, state: FSMContext):
        """Start the wizard to edit the rule name."""
        try:
            logger.debug(f"[AUTO_CLICK_DEBUG] start_edit_name START - rule_id: {rule_id}")

            await state.set_data({'rule_id': rule_id})

            text = "<b>✏️ Edit Rule Name</b>\n\nEnter a custom name for this rule (or type 'clear' to remove the name):"
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.cancel_button(f"auto_click:view:{rule_id}")
            )
            await state.set_state(ManagementStates.editing_auto_click_rule_name)
            logger.debug(f"[AUTO_CLICK_DEBUG] start_edit_name SUCCESS")

        except Exception as e:
            logger.error(f"[AUTO_CLICK_DEBUG] ❌ EXCEPTION in start_edit_name: {e}", exc_info=True)
            try:
                await query.answer(f"❌ Error: {str(e)[:100]}", show_alert=True)
            except:
                pass

    async def process_edit_name(self, message: types.Message, state: FSMContext):
        """Process the new name for a rule."""
        try:
            logger.debug(f"[AUTO_CLICK_DEBUG] process_edit_name START")

            name_input = message.text.strip()
            logger.debug(f"[AUTO_CLICK_DEBUG] Name input received: '{name_input}'")

            data = await state.get_data()
            rule_id = data['rule_id']
            logger.debug(f"[AUTO_CLICK_DEBUG] Rule ID from state: {rule_id}")

            # Handle "clear" command to remove name
            if name_input.lower() == 'clear':
                await self.rule_model.update(rule_id, {'name': None})
                logger.debug(f"[AUTO_CLICK_DEBUG] Name cleared successfully")
                await message.reply("✅ Rule name removed successfully.")
            else:
                # Limit name length
                if len(name_input) > 50:
                    await message.reply("❌ Name too long. Please keep it under 50 characters.")
                    return

                await self.rule_model.update(rule_id, {'name': name_input})
                logger.debug(f"[AUTO_CLICK_DEBUG] Name updated successfully")
                await message.reply("✅ Rule name updated successfully.")

        except Exception as e:
            logger.error(f"[AUTO_CLICK_DEBUG] ❌ EXCEPTION in process_edit_name: {e}", exc_info=True)
            await message.answer("❌ An error occurred while updating the rule name.")
        finally:
            await state.clear()

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
