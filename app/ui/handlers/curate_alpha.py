import logging
import json
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models.curated_alpha import CuratedAlphaRuleModel
from app.models.source_chat import SourceChatModel
from app.models.bot import BotModel

logger = logging.getLogger(__name__)

class CurateAlphaHandler:
    """Handler for Curated Alpha rule management"""

    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.rule_model = CuratedAlphaRuleModel(db)
        self.bot_model = BotModel(db)
        self.source_model = SourceChatModel(db)

    async def show_curate_alpha_menu(self, query: types.CallbackQuery):
        """Display the main Curated Alpha menu"""
        try:
            rules = await self.rule_model.get_all_rules()
            text = f"✨ <b>Curated Alpha Rules ({len(rules)})</b>\n\n"
            text += "Create rules to forward a token only after it appears in multiple, specific source chats."

            keyboard_rows = []
            for rule in rules:
                keyboard_rows.append([
                    InlineKeyboardButton(text=f"{rule['name']}", callback_data=f"curate_alpha:view:{rule['id']}")
                ])

            keyboard_rows.append([InlineKeyboardButton(text="➕ Add New Rule", callback_data="curate_alpha:add")])
            keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")])

            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
        except Exception as e:
            logger.error(f"Error showing curate alpha menu: {e}")
            await query.answer("❌ Error loading Curated Alpha rules")

    async def handle_curate_alpha_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle Curated Alpha related callbacks"""
        logger.debug(f"[CuratedAlpha] Received callback: {query.data}")
        parts = query.data.split(':')
        action = parts[1]
        rule_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None

        if action == 'list':
            await self.show_curate_alpha_menu(query)
        elif action == 'add':
            await self.wizard_start(query, state)
        elif action == 'view':
            await self.show_rule_details(query, rule_id)
        elif action == 'delete':
            await self.confirm_delete_rule(query, rule_id)
        elif action == 'confirm_delete':
            await self.delete_rule(query, rule_id)
        elif action.startswith('edit_'):
            await self.handle_edit_action(query, state, action, rule_id)
        # Wizard actions
        elif action == 'toggle_source':
            await self.wizard_toggle_source(query, state)
        elif action == 'save_edited_sources':
            await self.save_edited_sources(query, state)
        elif action == 'select_bot':
            await self.wizard_show_bot_selection(query, state)
        elif action == 'process_bot':
            await self.wizard_process_bot(query, state)
        elif action == 'set_mentions':
            await self.wizard_prompt_for_min_mentions(query, state)
        elif action == 'set_time':
            await self.wizard_set_time_window(query, state)
        elif action == 'toggle_pnl':
            await self.wizard_toggle_pnl(query, state)
        elif action == 'toggle_blockchain':
            await self.wizard_toggle_blockchain(query, state)
        elif action == 'summary':
            await self.wizard_show_summary(query, state)
        elif action == 'summary_back':
            await self.wizard_show_final_settings(query, state)
        elif action == 'save':
            await self.save_rule(query, state)
        elif action == 'save_edited_settings':
            await self.save_edited_settings(query, state)
        elif action == 'edit_toggle_chain':
            await self.edit_toggle_chain(query, state)
        elif action == 'save_chains':
            await self.save_edited_chains(query, state)

    async def handle_edit_action(self, query: types.CallbackQuery, state: FSMContext, action: str, rule_id: int):
        """Router for various edit actions."""
        if action == 'edit_name':
            await self.wizard_start_edit_name(query, state, rule_id)
        elif action == 'edit_sources':
            await self.wizard_start_edit_sources(query, state, rule_id)
        elif action == 'edit_chains':
            await self.wizard_start_edit_chains(query, state, rule_id)
        elif action == 'edit_bot':
            await self.wizard_start_edit_bot(query, state, rule_id)
        elif action == 'edit_dest':
            await self.wizard_start_edit_dest(query, state, rule_id)
        elif action == 'edit_settings':
            await self.wizard_start_edit_settings(query, state, rule_id)
        elif action == 'edit_mentions':
            await self.wizard_start_edit_mentions(query, state, rule_id)
        else:
            await query.answer("This edit function is not yet implemented.", show_alert=True)

    async def show_rule_details(self, query: types.CallbackQuery, rule_id: int):
        """Display the details of a specific rule."""
        try:
            rule = await self.rule_model.get_by_id(rule_id)
            if not rule:
                await query.answer("Rule not found.", show_alert=True)
                return await self.show_curate_alpha_menu(query)

            data = dict(rule)
            sources = await self.source_model.get_all_sources()
            selected_source_names = []
            if data.get('required_source_chat_ids'):
                selected_sources_data = [s for s in sources if s['source_chat_id'] in data['required_source_chat_ids']]
                for s in selected_sources_data:
                    name = s.get('display_name') or s.get('group_display_name') or s['name'] or s['title'] or f"ID: {s['source_chat_id']}"
                    selected_source_names.append(name)

            bot = await self.bot_model.get_by_id(data.get('forwarding_userbot_id'))
            bot_name = bot.get('display_name', bot['id']) if bot else "N/A"

            time_window_seconds = data.get('time_window_seconds', 86400)
            time_display = f"{time_window_seconds // 3600} hours" if time_window_seconds >= 3600 else f"{time_window_seconds // 60} minutes"

            required_mentions = data.get('required_mentions')
            if not required_mentions or required_mentions <= 0:
                mentions_display = f"All ({len(selected_source_names)})"
            else:
                mentions_display = f"{required_mentions} of {len(selected_source_names)}"

            blockchain_display = Keyboards.format_blockchain_emojis(data.get('allowed_chains', ['SOL']))

            text = (f"<b>✨ Rule: {data.get('name')}</b>\n\n"
                   f"<b>Required Sources ({mentions_display}):</b>\n - {'\n - '.join(selected_source_names)}\n"
                   f"<b>Blockchains:</b> {blockchain_display}\n"
                   f"<b>Forwarding Bot:</b> {bot_name}\n"
                   f"<b>Destination Chat ID:</b> `{data.get('destination_chat_id')}`\n"
                   f"<b>Time Window:</b> {time_display}\n"
                   f"<b>Forward PNL Alerts:</b> {'Yes' if data.get('forward_pnl_alerts') else 'No'}")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Edit Name", callback_data=f"curate_alpha:edit_name:{rule_id}"),
                    InlineKeyboardButton(text="🔄 Edit Sources", callback_data=f"curate_alpha:edit_sources:{rule_id}")
                ],
                [
                    InlineKeyboardButton(text="⛓️ Edit Chains", callback_data=f"curate_alpha:edit_chains:{rule_id}"),
                    InlineKeyboardButton(text="🤖 Edit Bot", callback_data=f"curate_alpha:edit_bot:{rule_id}")
                ],
                [
                    InlineKeyboardButton(text="🎯 Edit Destination", callback_data=f"curate_alpha:edit_dest:{rule_id}"),
                    InlineKeyboardButton(text="⏰ Edit Settings", callback_data=f"curate_alpha:edit_settings:{rule_id}")
                ],
                [
                    InlineKeyboardButton(text="🗑️ Delete Rule", callback_data=f"curate_alpha:delete:{rule_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back to List", callback_data="curate_alpha:list")]
            ])
            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error in show_rule_details: {e}", exc_info=True)
            await query.answer("❌ Failed to load rule details.", show_alert=True)

    async def confirm_delete_rule(self, query: types.CallbackQuery, rule_id: int):
        """Ask for confirmation before deleting a rule."""
        rule = await self.rule_model.get_by_id(rule_id)
        if not rule:
            return await query.answer("Rule not found.", show_alert=True)
        
        await query.message.edit_text(
            f"Are you sure you want to delete the rule '<b>{rule['name']}</b>'? This cannot be undone.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"curate_alpha:confirm_delete:{rule_id}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"curate_alpha:view:{rule_id}")
                ]
            ])
        )

    async def delete_rule(self, query: types.CallbackQuery, rule_id: int):
        """Delete a rule from the database."""
        await self.rule_model.delete(rule_id)
        await query.answer("Rule deleted successfully.", show_alert=True)
        await self.show_curate_alpha_menu(query)

    # --- WIZARD METHODS ---
    async def wizard_start(self, query: types.CallbackQuery, state: FSMContext):
        """Step 1: Start the wizard and ask for a rule name."""
        await state.clear()
        await query.message.edit_text(
            "<b>✨ Add Curated Alpha Rule (1/7)</b>\n\n" \
            "First, give this rule a descriptive name (e.g., 'Tier 1 Callers').",
            reply_markup=self.keyboards.cancel_button("curate_alpha:list")
        )
        await state.set_state(ManagementStates.curate_alpha_add_rule_name)

    async def wizard_process_name(self, message: types.Message, state: FSMContext):
        """Step 2: Process the name and show source selection."""
        await state.update_data(name=message.text.strip(), selected_sources=[], allowed_chains=['SOL'])
        await message.delete()
        await self.wizard_show_source_selection(message, state)

    async def wizard_show_source_selection(self, message_or_query, state: FSMContext):
        """Display the source selection screen for add or edit mode."""
        sources = await self.source_model.get_all_sources()
        
        if not sources:
            await state.clear()
            await message_or_query.answer("❌ No source chats found. Please add sources first.", show_alert=True)
            return

        data = await state.get_data()
        selected_sources = data.get('selected_sources', [])
        is_edit = data.get('edit_mode', False)
        rule_id = data.get('rule_id')

        text = f"<b>✨ {'Edit' if is_edit else 'Add'} Curated Alpha Rule (2/7)</b>\n\n" \
               f"Select at least two source chats that are required for this rule. Tap to select/deselect."

        keyboard_rows = []
        for source in sources:
            source_id = source['id']
            name = source.get('display_name') or source.get('group_display_name') or source['name'] or source['title'] or f"ID: {source['source_chat_id']}"
            status = "✅" if source_id in selected_sources else "❌"
            keyboard_rows.append([
                InlineKeyboardButton(
                    text=f"{status} {name}",
                    callback_data=f"curate_alpha:toggle_source:{source_id}"
                )
            ])
        
        if len(selected_sources) >= 2:
            if is_edit:
                keyboard_rows.append([
                    InlineKeyboardButton(text="✅ Save Changes", callback_data=f"curate_alpha:save_edited_sources:{rule_id}")
                ])
            else:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➡️ Continue", callback_data="curate_alpha:select_bot")
                ])

        keyboard_rows.append([InlineKeyboardButton(text="🔙 Cancel", callback_data=f"curate_alpha:{'view' if is_edit else 'list'}:{rule_id if is_edit else ''}")])
        
        markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        if isinstance(message_or_query, types.Message):
            await message_or_query.answer(text, reply_markup=markup)
        else: # Is a CallbackQuery
            await message_or_query.message.edit_text(text, reply_markup=markup)

        await state.set_state(ManagementStates.curate_alpha_select_sources)

    async def wizard_toggle_source(self, query: types.CallbackQuery, state: FSMContext):
        """Handle toggling a source in the selection screen."""
        source_id = int(query.data.split(':')[2])
        data = await state.get_data()
        selected_sources = data.get('selected_sources', [])

        if source_id in selected_sources:
            selected_sources.remove(source_id)
        else:
            selected_sources.append(source_id)
        
        await state.update_data(selected_sources=selected_sources)
        await self.wizard_show_source_selection(query, state)

    async def wizard_show_bot_selection(self, query: types.CallbackQuery, state: FSMContext):
        """Show userbot selection for add or edit mode."""
        data = await state.get_data()
        is_edit = data.get('edit_mode', False)
        rule_id = data.get('rule_id')

        if not is_edit and len(data.get('selected_sources', [])) < 2:
            await query.answer("Please select at least two sources first.", show_alert=True)
            return

        bots = await self.bot_model.get_active_userbots()
        if not bots:
            await query.answer("❌ No active userbots found. Please add one first.", show_alert=True)
            return

        text = f"<b>✨ {'Edit' if is_edit else 'Add'} Curated Alpha Rule (3/7)</b>\n\n" \
               f"Select the userbot that will forward the curated call."

        keyboard_rows = []
        for bot in bots:
            name = bot.get('display_name') or bot['session_name']
            keyboard_rows.append([
                InlineKeyboardButton(text=f"🤖 {name}", callback_data=f"curate_alpha:process_bot:{bot['id']}")
            ])
        
        back_cb = f"curate_alpha:view:{rule_id}" if is_edit else "curate_alpha:toggle_source:0"
        keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data=back_cb)])

        await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
        await state.set_state(ManagementStates.curate_alpha_select_forwarding_bot)

    async def wizard_process_bot(self, query: types.CallbackQuery, state: FSMContext):
        """Process bot selection for add or edit mode."""
        bot_id = int(query.data.split(':')[2])
        await state.update_data(forwarding_userbot_id=bot_id)
        data = await state.get_data()
        if data.get('edit_mode'):
            await self.rule_model.update(data['rule_id'], {'forwarding_userbot_id': bot_id})
            await state.clear()
            await self.show_rule_details(query, data['rule_id'])
        else:
            await self.wizard_prompt_for_destination(query, state)

    async def wizard_prompt_for_destination(self, query: types.CallbackQuery, state: FSMContext):
        """Ask for destination chat ID for add or edit mode."""
        data = await state.get_data()
        text = f"<b>✨ {'Edit' if data.get('edit_mode') else 'Add'} Curated Alpha Rule (4/7)</b>\n\n" \
               f"Enter the chat ID of the destination channel (e.g., -100123456789)."
        
        back_cb = f"curate_alpha:view:{data.get('rule_id')}" if data.get('edit_mode') else "curate_alpha:select_bot"
        await query.message.edit_text(
            text, 
            reply_markup=self.keyboards.cancel_button(back_cb)
        )
        await state.set_state(ManagementStates.curate_alpha_set_destination)

    async def wizard_process_destination(self, message: types.Message, state: FSMContext):
        """Process destination and move to next step."""
        try:
            destination_id = int(message.text.strip())
            data = await state.get_data()
            if data.get('edit_mode'):
                await self.rule_model.update(data['rule_id'], {'destination_chat_id': destination_id})
                await message.delete()
                await state.clear()
                # Create a dummy query to redraw the details view
                from aiogram.types.user import User
                from aiogram.types.chat import Chat
                dummy_user = User(id=message.from_user.id, is_bot=False, first_name=message.from_user.first_name)
                dummy_chat = Chat(id=message.chat.id, type="private")
                dummy_query = types.CallbackQuery(id="dummy", from_user=dummy_user, chat_instance="dummy", message=message)
                await self.show_rule_details(dummy_query, data['rule_id'])
            else:
                await state.update_data(destination_chat_id=destination_id)
                await message.delete()
                await self.wizard_prompt_for_min_mentions(message, state)
        except ValueError:
            await message.reply("Invalid Chat ID. Please enter a number.")

    async def wizard_prompt_for_min_mentions(self, message: types.Message, state: FSMContext):
        """Step 5: Ask for the minimum number of mentions."""
        data = await state.get_data()
        num_sources = len(data.get('selected_sources', []))
        # Set default to all sources
        await state.update_data(required_mentions=num_sources)

        text = f"<b>✨ Add Curated Alpha Rule (5/7)</b>\n\n" \
               f"You have selected {num_sources} source(s).\n\n" \
               f"Enter the <b>minimum number of mentions</b> required to trigger this rule. " \
               f"(from 1 to {num_sources}).\n\n" \
               f"Default is <b>{num_sources}</b> (requires all sources). Just press enter to use the default."

        await message.answer(
            text,
            reply_markup=self.keyboards.cancel_button("curate_alpha:list")
        )
        await state.set_state(ManagementStates.curate_alpha_set_min_mentions)

    async def wizard_process_min_mentions(self, message: types.Message, state: FSMContext):
        """Process the minimum mentions input."""
        data = await state.get_data()
        num_sources = len(data.get('selected_sources', []))
        is_edit = data.get('edit_mode', False)
        rule_id = data.get('rule_id')

        if not message.text.strip(): # User pressed enter for default
            required_mentions = num_sources
        else:
            try:
                required_mentions = int(message.text.strip())
                if not (1 <= required_mentions <= num_sources):
                    await message.reply(f"Please enter a number between 1 and {num_sources}.")
                    return
            except ValueError:
                await message.reply("Invalid number. Please enter a number.")
                return

        if is_edit:
            await self.rule_model.update(rule_id, {'required_mentions': required_mentions})
            await message.delete()
            await state.clear()
            # Create a dummy query to redraw the details view
            from aiogram.types.user import User
            from aiogram.types.chat import Chat
            dummy_user = User(id=message.from_user.id, is_bot=False, first_name=message.from_user.first_name)
            dummy_chat = Chat(id=message.chat.id, type="private")
            dummy_query = types.CallbackQuery(id="dummy", from_user=dummy_user, chat_instance="dummy", message=message)
            await self.show_rule_details(dummy_query, rule_id)
        else:
            await state.update_data(required_mentions=required_mentions)
            await message.delete()
            await self.wizard_show_final_settings(message, state)

    async def wizard_show_final_settings(self, message_or_query, state: FSMContext):
        """Show time window and PNL alert options for add or edit mode."""
        data = await state.get_data()
        is_edit = data.get('edit_mode', False)
        rule_id = data.get('rule_id')

        if is_edit and 'time_window_seconds' not in data:
            rule = await self.rule_model.get_by_id(rule_id)
            await state.update_data(
                time_window_seconds=rule['time_window_seconds'],
                forward_pnl_alerts=rule['forward_pnl_alerts'],
                required_mentions=rule.get('required_mentions'),
                allowed_chains=rule.get('allowed_chains', ['SOL'])
            )
            data = await state.get_data()

        time_window = data.get('time_window_seconds', 86400)
        pnl_alerts = data.get('forward_pnl_alerts', False)
        allowed_chains_raw = data.get('allowed_chains', ['SOL'])
        if isinstance(allowed_chains_raw, str):
            allowed_chains = json.loads(allowed_chains_raw)
        else:
            allowed_chains = allowed_chains_raw

        text = f"<b>✨ {'Edit' if is_edit else 'Add'} Curated Alpha Rule (6/7)</b>\n\n" \
               f"Configure the final settings."

        time_display = f"{time_window // 3600}h" if time_window >= 3600 else f"{time_window // 60}m"

        keyboard_rows = [
            [InlineKeyboardButton(text="-- Time Window --", callback_data="curate_alpha:noop")],
            [InlineKeyboardButton(text=f"Current: {time_display}", callback_data="curate_alpha:noop")],
            [
                InlineKeyboardButton(text="5m", callback_data="curate_alpha:set_time:300"),
                InlineKeyboardButton(text="10m", callback_data="curate_alpha:set_time:600"),
                InlineKeyboardButton(text="30m", callback_data="curate_alpha:set_time:1800"),
                InlineKeyboardButton(text="1h", callback_data="curate_alpha:set_time:3600"),
            ],
            [InlineKeyboardButton(text="-- Blockchains --", callback_data="curate_alpha:noop")],
            [
                InlineKeyboardButton(
                    text=f"{'✅' if 'SOL' in allowed_chains else '☐'} SOL",
                    callback_data="curate_alpha:toggle_blockchain:SOL"
                ),
                InlineKeyboardButton(
                    text=f"{'✅' if 'BNB' in allowed_chains else '☐'} BNB",
                    callback_data="curate_alpha:toggle_blockchain:BNB"
                )
            ],
            [InlineKeyboardButton(text="-- PNL Alerts --", callback_data="curate_alpha:noop")],
            [InlineKeyboardButton(text=f"{'✅' if pnl_alerts else '❌'} Forward /pnl Alerts", callback_data="curate_alpha:toggle_pnl")],
        ]

        if is_edit:
            keyboard_rows.insert(0, [InlineKeyboardButton(text="🔢 Edit Mentions", callback_data=f"curate_alpha:edit_mentions:{rule_id}")])
            keyboard_rows.append([InlineKeyboardButton(text="✅ Save Settings", callback_data=f"curate_alpha:save_edited_settings:{rule_id}")])
        else:
            keyboard_rows.append([InlineKeyboardButton(text="➡️ Continue to Summary", callback_data="curate_alpha:summary")])
        
        back_cb = f"curate_alpha:view:{rule_id}" if is_edit else f"curate_alpha:process_bot:{data.get('forwarding_userbot_id')}"
        keyboard_rows.append([InlineKeyboardButton(text="🔙 Back", callback_data=back_cb)])

        markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        if isinstance(message_or_query, types.Message):
            await message_or_query.answer(text, reply_markup=markup)
        else:
            await message_or_query.message.edit_text(text, reply_markup=markup)
        await state.set_state(ManagementStates.curate_alpha_set_time_window)

    async def wizard_set_time_window(self, query: types.CallbackQuery, state: FSMContext):
        """Handle time window selection."""
        seconds = int(query.data.split(':')[2])
        await state.update_data(time_window_seconds=seconds)
        await self.wizard_show_final_settings(query, state)

    async def wizard_toggle_pnl(self, query: types.CallbackQuery, state: FSMContext):
        """Handle PNL alert toggle."""
        data = await state.get_data()
        current_pnl = data.get('forward_pnl_alerts', False)
        await state.update_data(forward_pnl_alerts=not current_pnl)
        await self.wizard_show_final_settings(query, state)

    async def wizard_toggle_blockchain(self, query: types.CallbackQuery, state: FSMContext):
        """Toggle SOL/BNB in blockchain selector"""
        try:
            logger.debug(f"[BLOCKCHAIN_TOGGLE] Received callback: {query.data}")
            blockchain = query.data.split(':')[2]  # SOL or BNB
            logger.debug(f"[BLOCKCHAIN_TOGGLE] Blockchain to toggle: {blockchain}")

            data = await state.get_data()
            logger.debug(f"[BLOCKCHAIN_TOGGLE] Current state data: {data}")

            allowed_chains_raw = data.get('allowed_chains', ['SOL'])
            if isinstance(allowed_chains_raw, str):
                allowed_chains = json.loads(allowed_chains_raw)
            else:
                allowed_chains = allowed_chains_raw
            logger.debug(f"[BLOCKCHAIN_TOGGLE] Current allowed_chains: {allowed_chains}")

            if blockchain in allowed_chains:
                allowed_chains.remove(blockchain)
                logger.debug(f"[BLOCKCHAIN_TOGGLE] Removed {blockchain}, new list: {allowed_chains}")
            else:
                allowed_chains.append(blockchain)
                logger.debug(f"[BLOCKCHAIN_TOGGLE] Added {blockchain}, new list: {allowed_chains}")

            # Validation: cannot have zero chains
            if not allowed_chains:
                logger.debug(f"[BLOCKCHAIN_TOGGLE] Validation failed - no chains selected")
                await query.answer("⚠️ At least one blockchain must be selected", show_alert=True)
                return

            await state.update_data(allowed_chains=allowed_chains)
            logger.debug(f"[BLOCKCHAIN_TOGGLE] State updated, refreshing UI")
            await self.wizard_show_final_settings(query, state)
            logger.debug(f"[BLOCKCHAIN_TOGGLE] Toggle completed successfully")
        except Exception as e:
            logger.error(f"[BLOCKCHAIN_TOGGLE] ERROR: {e}", exc_info=True)
            await query.answer(f"❌ Error toggling blockchain: {str(e)}", show_alert=True)

    async def save_edited_settings(self, query: types.CallbackQuery, state: FSMContext):
        """Save the edited settings for a rule."""
        try:
            data = await state.get_data()
            rule_id = data['rule_id']
            update_data = {
                'time_window_seconds': data['time_window_seconds'],
                'forward_pnl_alerts': data['forward_pnl_alerts']
            }
            await self.rule_model.update(rule_id, update_data)

            # Update allowed_chains separately (JSONB requires special handling)
            if 'allowed_chains' in data:
                await self.rule_model.update_rule_chains(rule_id, data['allowed_chains'])

            await state.clear()
            await self.show_rule_details(query, rule_id)
            await query.answer("✅ Settings updated!")
        except Exception as e:
            logger.error(f"Error saving edited settings: {e}", exc_info=True)
            await query.answer("❌ Error saving settings.", show_alert=True)

    async def wizard_show_summary(self, query: types.CallbackQuery, state: FSMContext):
        """Step 7: Show summary and confirm."""
        logger.debug("[CuratedAlpha] Entering wizard_show_summary")
        try:
            data = await state.get_data()
            logger.debug(f"[CuratedAlpha] State data for summary: {data}")
            
            sources = await self.source_model.get_all_sources()
            selected_sources_data = [s for s in sources if s['id'] in data.get('selected_sources', [])]
            
            selected_source_names = []
            for s in selected_sources_data:
                name = s.get('display_name') or s.get('group_display_name') or s['name'] or s['title'] or f"ID: {s['source_chat_id']}"
                selected_source_names.append(name)

            bot = await self.bot_model.get_by_id(data.get('forwarding_userbot_id'))
            bot_name = bot.get('display_name', bot['id']) if bot else "N/A"

            time_window_seconds = data.get('time_window_seconds', 86400)
            time_display = f"{time_window_seconds // 3600} hours" if time_window_seconds >= 3600 else f"{time_window_seconds // 60} minutes"

            required_mentions = data.get('required_mentions')
            if not required_mentions or required_mentions <= 0:
                mentions_display = f"All ({len(selected_source_names)})"
            else:
                mentions_display = f"{required_mentions} of {len(selected_source_names)}"

            text = (f"<b>✨ Rule Summary (7/7)</b>\n\n" 
                   f"<b>Name:</b> {data.get('name')}\n"
                   f"<b>Required Sources ({mentions_display}):</b>\n - {'\n - '.join(selected_source_names)}\n"
                   f"<b>Forwarding Bot:</b> {bot_name}\n"
                   f"<b>Destination Chat ID:</b> `{data.get('destination_chat_id')}`\n"
                   f"<b>Time Window:</b> {time_display}\n"
                   f"<b>Forward PNL Alerts:</b> {'Yes' if data.get('forward_pnl_alerts') else 'No'}")

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Save Rule", callback_data="curate_alpha:save")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="curate_alpha:summary_back")]
            ])
            await query.message.edit_text(text, reply_markup=keyboard)
            logger.debug("[CuratedAlpha] Successfully displayed summary.")
        except Exception as e:
            logger.error(f"Error in wizard_show_summary: {e}", exc_info=True)
            await query.answer("❌ Failed to generate summary. Check logs.", show_alert=True)

    async def save_rule(self, query: types.CallbackQuery, state: FSMContext):
        try:
            data = await state.get_data()

            if 'name' not in data:
                await query.answer("❌ Session data is missing. Please start over.", show_alert=True)
                await self.show_curate_alpha_menu(query)
                return
            
            sources = await self.source_model.get_all_sources()
            selected_source_chat_ids = [s['source_chat_id'] for s in sources if s['id'] in data.get('selected_sources', [])]

            await self.rule_model.create({
                'name': data['name'],
                'required_source_chat_ids': selected_source_chat_ids,
                'destination_chat_id': data['destination_chat_id'],
                'forwarding_userbot_id': data['forwarding_userbot_id'],
                'time_window_seconds': data.get('time_window_seconds', 86400),
                'forward_pnl_alerts': data.get('forward_pnl_alerts', False),
                'required_mentions': data.get('required_mentions', len(selected_source_chat_ids)),
                'allowed_chains': json.dumps(data.get('allowed_chains', ['SOL'])),
            })
            await state.clear()
            await query.message.edit_text("✅ <b>Curated Alpha Rule Saved!</b>")
            await self.show_curate_alpha_menu(query)
        except Exception as e:
            logger.error(f"Error saving curated alpha rule: {e}", exc_info=True)
            await query.answer("❌ Error saving rule.", show_alert=True)

    # --- EDIT METHODS ---
    async def wizard_start_edit_name(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start the process to edit a rule's name."""
        rule = await self.rule_model.get_by_id(rule_id)
        await state.set_data({'rule_id': rule_id, 'edit_field': 'name'})
        await query.message.edit_text(
            f"Current name is '<b>{rule['name']}</b>'.\n\nEnter the new name:",
            reply_markup=self.keyboards.cancel_button(f"curate_alpha:view:{rule_id}")
        )
        await state.set_state(ManagementStates.curate_alpha_edit_field)

    async def wizard_start_edit_sources(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start the process to edit a rule's sources."""
        rule = await self.rule_model.get_by_id(rule_id)
        all_sources = await self.source_model.get_all_sources()
        
        current_source_pks = [s['id'] for s in all_sources if s['source_chat_id'] in rule['required_source_chat_ids']]

        await state.set_data({
            'rule_id': rule_id, 
            'edit_mode': True,
            'selected_sources': current_source_pks
        })
        await self.wizard_show_source_selection(query, state)

    async def save_edited_sources(self, query: types.CallbackQuery, state: FSMContext):
        """Save the edited sources for a rule."""
        try:
            data = await state.get_data()
            rule_id = data['rule_id']
            
            sources = await self.source_model.get_all_sources()
            selected_source_chat_ids = [s['source_chat_id'] for s in sources if s['id'] in data.get('selected_sources', [])]

            await self.rule_model.update(rule_id, {'required_source_chat_ids': selected_source_chat_ids})
            await state.clear()
            await self.show_rule_details(query, rule_id)
            await query.answer("✅ Sources updated!")
        except Exception as e:
            logger.error(f"Error saving edited sources: {e}", exc_info=True)
            await query.answer("❌ Error saving sources.", show_alert=True)

    async def wizard_start_edit_mentions(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start the process to edit a rule's minimum mentions."""
        rule = await self.rule_model.get_by_id(rule_id)
        if not rule:
            await query.answer("Rule not found.", show_alert=True)
            return

        num_sources = len(rule.get('required_source_chat_ids', []))
        current_mentions = rule.get('required_mentions') or num_sources

        await state.set_data({
            'rule_id': rule_id, 
            'edit_mode': True,
            'selected_sources': [s['id'] for s in await self.source_model.get_all_sources() if s['source_chat_id'] in rule['required_source_chat_ids']]
        })

        await query.message.edit_text(
            f"Current minimum mentions: <b>{current_mentions} of {num_sources}</b>.\n\n" \
            f"Enter the new minimum number of mentions (1 to {num_sources}).",
            reply_markup=self.keyboards.cancel_button(f"curate_alpha:view:{rule_id}")
        )
        await state.set_state(ManagementStates.curate_alpha_set_min_mentions)

    async def wizard_start_edit_bot(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start the process to edit a rule's forwarding bot."""
        await state.set_data({'rule_id': rule_id, 'edit_mode': True})
        await self.wizard_show_bot_selection(query, state)

    async def wizard_start_edit_dest(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start the process to edit a rule's destination."""
        await state.set_data({'rule_id': rule_id, 'edit_mode': True})
        await self.wizard_prompt_for_destination(query, state)

    async def wizard_start_edit_settings(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start the process to edit a rule's settings."""
        await state.set_data({'rule_id': rule_id, 'edit_mode': True})
        await self.wizard_show_final_settings(query, state)

    async def wizard_start_edit_chains(self, query: types.CallbackQuery, state: FSMContext, rule_id: int):
        """Start editing blockchain chains for a rule"""
        rule = await self.rule_model.get_by_id(rule_id)
        await state.set_data({
            'rule_id': rule_id,
            'edit_mode': True,
            'allowed_chains': rule.get('allowed_chains', ['SOL'])
        })
        await self.show_blockchain_selector_edit(query, state)

    async def show_blockchain_selector_edit(self, query: types.CallbackQuery, state: FSMContext):
        """Show blockchain selector for editing existing rule"""
        data = await state.get_data()
        rule_id = data['rule_id']
        allowed_chains_raw = data.get('allowed_chains', ['SOL'])
        if isinstance(allowed_chains_raw, str):
            allowed_chains = json.loads(allowed_chains_raw)
        else:
            allowed_chains = allowed_chains_raw

        text = "<b>⛓️ Edit Blockchains</b>\n\nSelect which blockchains this rule should monitor:"

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"{'✅' if 'SOL' in allowed_chains else '☐'} SOL",
                    callback_data=f"curate_alpha:edit_toggle_chain:SOL:{rule_id}"
                ),
                InlineKeyboardButton(
                    text=f"{'✅' if 'BNB' in allowed_chains else '☐'} BNB",
                    callback_data=f"curate_alpha:edit_toggle_chain:BNB:{rule_id}"
                )
            ],
            [InlineKeyboardButton(text="✅ Save", callback_data=f"curate_alpha:save_chains:{rule_id}")],
            [InlineKeyboardButton(text="🔙 Cancel", callback_data=f"curate_alpha:view:{rule_id}")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def edit_toggle_chain(self, query: types.CallbackQuery, state: FSMContext):
        """Toggle blockchain in edit mode"""
        parts = query.data.split(':')
        blockchain = parts[2]  # SOL or BNB

        data = await state.get_data()
        allowed_chains_raw = data.get('allowed_chains', ['SOL'])
        if isinstance(allowed_chains_raw, str):
            allowed_chains = json.loads(allowed_chains_raw)
        else:
            allowed_chains = allowed_chains_raw

        if blockchain in allowed_chains:
            allowed_chains.remove(blockchain)
        else:
            allowed_chains.append(blockchain)

        if not allowed_chains:
            await query.answer("⚠️ At least one blockchain required", show_alert=True)
            return

        await state.update_data(allowed_chains=allowed_chains)
        await self.show_blockchain_selector_edit(query, state)

    async def save_edited_chains(self, query: types.CallbackQuery, state: FSMContext):
        """Save edited blockchain selection"""
        data = await state.get_data()
        rule_id = data['rule_id']
        allowed_chains = data['allowed_chains']

        await self.rule_model.update_rule_chains(rule_id, allowed_chains)
        await state.clear()
        await query.answer("✅ Blockchains updated!")
        await self.show_rule_details(query, rule_id)

    async def process_field_edit(self, message: types.Message, state: FSMContext):
        """Process a text input for an edit action."""
        try:
            data = await state.get_data()
            rule_id = data['rule_id']
            field = data['edit_field']
            new_value = message.text.strip()

            await self.rule_model.update(rule_id, {field: new_value})
            await message.answer(f"✅ Rule {field} updated successfully!")
            
            await state.clear()
            # This part is tricky, we don't have the query object to redraw the menu
            # Best to just confirm and let the user navigate back
            await message.answer(f"Returning to main menu.", reply_markup=self.keyboards.back_button("curate_alpha:list"))

        except Exception as e:
            logger.error(f"Error processing field edit: {e}", exc_info=True)
            await message.answer("❌ An error occurred while updating.")
        finally:
            await state.clear()