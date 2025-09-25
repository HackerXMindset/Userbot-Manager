import logging
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.models.template import TemplateModel, TemplateAssignmentModel
from app.models.group import GroupModel

logger = logging.getLogger(__name__)

class TemplatesHandler:
    """Handler for custom post template management"""

    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.template_model = TemplateModel(db)
        self.assignment_model = TemplateAssignmentModel(db)
        self.group_model = GroupModel(db)

    async def show_templates_menu(self, query: types.CallbackQuery, page: int = 1):
        """Display the main templates management menu with pagination."""
        try:
            templates = await self.template_model.get_all_with_assignment_counts()
            
            page_size = 9
            total_pages = (len(templates) + page_size - 1) // page_size if templates else 1
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_templates = templates[start_index:end_index]

            text = f"<b>📝 Custom Post Templates ({len(templates)})</b> (Page {page}/{total_pages})\n\n"
            text += "Manage templates for call messages."

            keyboard_rows = []
            for t in paginated_templates:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{t['name']} ({t['assignment_count']} assigned)",
                        callback_data=f"templates:view:{t['id']}"
                    )
                ])

            if total_pages > 1:
                pagination_buttons = self.keyboards.pagination(f"templates_page", page, total_pages)
                keyboard_rows.append(pagination_buttons)

            keyboard_rows.append([
                InlineKeyboardButton(text="➕ Create New Template", callback_data="templates:add")
            ])
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")
            ])

            await query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            )
        except Exception as e:
            logger.error(f"Error showing templates menu: {e}")
            await query.answer("❌ Error loading templates.")



    async def handle_templates_action(self, query: types.CallbackQuery, state: FSMContext):
        """Handle callbacks for the templates section."""
        parts = query.data.split(':')

        # Pagination for main templates menu
        if parts[0] == 'templates_page':
            if len(parts) > 2 and parts[1] == 'page' and parts[2].isdigit():
                page = int(parts[2])
                await self.show_templates_menu(query, page=page)
            else:
                await query.answer()
            return

        # Pagination for assignment menu
        if parts[0] == 'templates_assign_page':
            template_id = int(parts[1])
            if len(parts) > 3 and parts[2] == 'page' and parts[3].isdigit():
                page = int(parts[3])
                await self.show_assignment_menu(query, template_id, state, page=page)
            else:
                await query.answer()
            return

        action = parts[1]
        item_id = int(parts[2]) if len(parts) > 2 else None

        if action == 'main':
            await self.show_templates_menu(query, page=1)
        elif action == 'add':
            await self.wizard_start_add(query, state)
        elif action == 'view':
            await self.show_template_details(query, item_id)
        elif action == 'delete':
            await self.confirm_delete(query, item_id)
        elif action == 'confirm_delete':
            await self.delete_template(query, item_id)
        elif action == 'assign':
            await self.show_assignment_menu(query, item_id, state, page=1)
        elif action == 'toggle_assign':
            group_id = int(parts[3])
            await self.toggle_assignment(query, item_id, group_id, state)
        elif action == 'save_assign':
            await self.save_assignments(query, item_id, state)
        elif action == 'edit':
            await self.wizard_start_edit(query, item_id, state)
        elif action == 'edit_name':
            await self.wizard_edit_name(query, item_id, state)
        elif action == 'edit_text':
            await self.wizard_edit_text(query, item_id, state)
        elif action == 'toggle_sender':
            await self.toggle_sender(query, item_id)
        else:
            await query.answer("Action not yet implemented.")

    async def show_template_details(self, query: types.CallbackQuery, template_id: int):
        """Show details for a specific template."""
        try:
            template = await self.template_model.get_by_id(template_id)
            if not template:
                await query.answer("❌ Template not found.")
                return await self.show_templates_menu(query)

            assigned_groups = await self.assignment_model.get_assigned_groups(template_id)

            import html
            text = f"<b>📝 Template: {template['name']}</b>\n\n"
            text += f"<b>Assignments:</b> {len(assigned_groups)} groups\n\n"
            text += "<b>Preview:</b>\n"
            text += f"<pre>{html.escape(template['template_text'])}</pre>"

            sender_text = "Sender: Mgmt Bot" if template.get('use_management_bot') else "Sender: Userbot"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✏️ Edit", callback_data=f"templates:edit:{template_id}"),
                    InlineKeyboardButton(text="🤝 Assign", callback_data=f"templates:assign:{template_id}")
                ],
                [
                    InlineKeyboardButton(text=f"🔄 {sender_text}", callback_data=f"templates:toggle_sender:{template_id}")
                ],
                [
                    InlineKeyboardButton(text="🗑️ Delete", callback_data=f"templates:delete:{template_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back to Templates", callback_data="templates:main")
                ]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Error showing template details: {e}")
            await query.answer("❌ Error loading template details.")

    async def toggle_sender(self, query: types.CallbackQuery, template_id: int):
        """Toggle the use_management_bot flag for a template."""
        try:
            template = await self.template_model.get_by_id(template_id)
            if not template:
                await query.answer("❌ Template not found.")
                return

            new_value = not template.get('use_management_bot', False)
            await self.template_model.update(template_id, {"use_management_bot": new_value})
            
            await query.answer(f"Sender switched to {'Management Bot' if new_value else 'Userbot'}")
            await self.show_template_details(query, template_id)

        except Exception as e:
            logger.error(f"Error toggling sender: {e}")
            await query.answer("❌ Error updating sender.")

    async def show_assignment_menu(self, query: types.CallbackQuery, template_id: int, state: FSMContext, page: int = 1):
        """Show the menu for assigning a template to groups."""
        try:
            template = await self.template_model.get_by_id(template_id)
            if not template:
                await query.answer("❌ Template not found.")
                return

            all_groups = await self.group_model.get_groups_with_stats()
            
            # Initialize state if it's not already set for this wizard
            if await state.get_state() != ManagementStates.template_assign_select_groups:
                assigned_groups_records = await self.assignment_model.get_assigned_groups(template_id)
                assigned_group_ids = {g['id'] for g in assigned_groups_records}
                await state.set_state(ManagementStates.template_assign_select_groups)
                await state.update_data(current_assignments=list(assigned_group_ids))

            data = await state.get_data()
            current_assignments = set(data.get('current_assignments', []))
            await state.update_data(current_page=page) # Store current page

            # Pagination logic
            page_size = 9
            total_pages = (len(all_groups) + page_size - 1) // page_size if all_groups else 1
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_groups = all_groups[start_index:end_index]

            text = f"🤝 Assign Template: <b>{template['name']}</b> (Page {page}/{total_pages})\n\n"
            text += "Select which target groups should use this template."

            keyboard_rows = []
            for group in paginated_groups:
                is_assigned = group['id'] in current_assignments
                status_icon = "✅" if is_assigned else "❌"
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {group_name}",
                        callback_data=f"templates:toggle_assign:{template_id}:{group['id']}"
                    )
                ])
            
            if total_pages > 1:
                pagination_buttons = self.keyboards.pagination(f"templates_assign_page:{template_id}", page, total_pages)
                keyboard_rows.append(pagination_buttons)

            keyboard_rows.append([
                InlineKeyboardButton(text="💾 Save Assignments", callback_data=f"templates:save_assign:{template_id}")
            ])
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Cancel", callback_data=f"templates:view:{template_id}")
            ])

            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))

        except Exception as e:
            logger.error(f"Error showing assignment menu: {e}")
            await query.answer("❌ Error loading assignment menu.")

    async def toggle_assignment(self, query: types.CallbackQuery, template_id: int, group_id: int, state: FSMContext):
        """Toggle a group's assignment for a template in the state."""
        try:
            data = await state.get_data()
            current_assignments = set(data.get('current_assignments', []))
            page = data.get('current_page', 1)

            if group_id in current_assignments:
                current_assignments.remove(group_id)
            else:
                current_assignments.add(group_id)
            
            await state.update_data(current_assignments=list(current_assignments))

            # Redraw the menu on the same page
            await self.show_assignment_menu(query, template_id, state, page=page)
            await query.answer()

        except Exception as e:
            logger.error(f"Error toggling assignment: {e}")
            await query.answer("❌ Error updating selection.")

    async def save_assignments(self, query: types.CallbackQuery, template_id: int, state: FSMContext):
        """Save the template assignments to the database."""
        try:
            data = await state.get_data()
            new_assignments = set(data.get('current_assignments', []))

            # Get all groups to clear old assignments for this template
            all_groups = await self.group_model.get_groups_with_stats()
            for group in all_groups:
                # This is inefficient, a better way would be a single query to unassign all
                # but for now this is fine.
                await self.assignment_model.unassign(group['id'])

            # Add new assignments
            for group_id in new_assignments:
                await self.assignment_model.assign(group_id, template_id)

            await query.answer("✅ Assignments saved!")
            await state.clear()
            await self.show_template_details(query, template_id)

        except Exception as e:
            logger.error(f"Error saving assignments: {e}")
            await query.answer("❌ Error saving assignments.")

    async def confirm_delete(self, query: types.CallbackQuery, template_id: int):
        """Confirm deletion of a template."""
        template = await self.template_model.get_by_id(template_id)
        if not template:
            await query.answer("❌ Template not found.")
            return

        text = f"⚠️ Are you sure you want to delete the template '<b>{template['name']}</b>'?\n\nThis will unassign it from all groups. This action cannot be undone."
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"templates:confirm_delete:{template_id}"),
                InlineKeyboardButton(text="❌ Cancel", callback_data=f"templates:view:{template_id}")
            ]
        ])
        await query.message.edit_text(text, reply_markup=keyboard)

    async def delete_template(self, query: types.CallbackQuery, template_id: int):
        """Delete a template after confirmation."""
        try:
            await self.template_model.delete(template_id)
            await query.answer("✅ Template deleted successfully.")
            await self.show_templates_menu(query)
        except Exception as e:
            logger.error(f"Error deleting template: {e}")
            await query.answer("❌ Error deleting template.")

    async def wizard_start_add(self, query: types.CallbackQuery, state: FSMContext):
        """Start the 'add new template' wizard."""
        await state.clear()
        await query.message.edit_text(
            "<b>➕ Create New Template (1/2)</b>\n\n"
            "Please enter a unique name for this template (e.g., 'Standard Call', 'Pump.fun Special').",
            reply_markup=self.keyboards.cancel_button("templates:main")
        )
        await state.set_state(ManagementStates.template_add_name)

    async def wizard_process_name(self, message: types.Message, state: FSMContext):
        """Process the template name and ask for the template text."""
        template_name = message.text.strip()
        
        # Check if name is unique
        existing = await self.template_model.db.fetchrow(
            "SELECT id FROM post_templates WHERE name = $1", template_name
        )
        if existing:
            await message.reply("A template with this name already exists. Please choose another name.")
            return

        await state.update_data(template_name=template_name)
        
        await message.reply(
            "<b>➕ Create New Template (2/2)</b>\n\n"
            "Great! Now, please send the template text. You can use placeholders like `{address}`, `${token_symbol}`, etc.\n\n"
            "Use standard Telegram markdown for formatting.",
            reply_markup=self.keyboards.cancel_button("templates:main")
        )
        await state.set_state(ManagementStates.template_add_text)

    async def wizard_process_text(self, message: types.Message, state: FSMContext):
        """Process the template text and save the new template."""
        template_text = message.text
        data = await state.get_data()
        template_name = data.get("template_name")

        if not template_name:
            await message.reply("Session expired, please start over.", reply_markup=self.keyboards.back_button("templates:main"))
            await state.clear()
            return

        try:
            new_template = await self.template_model.create({
                "name": template_name,
                "template_text": template_text
            })
            await message.reply(
                f"✅ Template '<b>{template_name}</b>' created successfully!",
                reply_markup=self.keyboards.back_button(f"templates:view:{new_template['id']}")
            )
        except Exception as e:
            logger.error(f"Error creating template: {e}")
            await message.reply(f"❌ An error occurred while saving the template: {e}")
        finally:
            await state.clear()

    async def wizard_start_edit(self, query: types.CallbackQuery, template_id: int, state: FSMContext):
        """Display options for what to edit on a template."""
        template = await self.template_model.get_by_id(template_id)
        if not template:
            await query.answer("❌ Template not found.")
            return

        text = f"✏️ What would you like to edit for '<b>{template['name']}</b>'?"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Name", callback_data=f"templates:edit_name:{template_id}")],
            [InlineKeyboardButton(text="Template Text", callback_data=f"templates:edit_text:{template_id}")],
            [InlineKeyboardButton(text="🔙 Back", callback_data=f"templates:view:{template_id}")]
        ])
        await query.message.edit_text(text, reply_markup=keyboard)

    async def wizard_edit_name(self, query: types.CallbackQuery, template_id: int, state: FSMContext):
        """Start the wizard to edit a template's name."""
        await state.clear()
        await state.update_data(template_id=template_id)
        await query.message.edit_text(
            "✏️ Please enter the new name for this template.",
            reply_markup=self.keyboards.cancel_button(f"templates:view:{template_id}")
        )
        await state.set_state(ManagementStates.template_edit_name)

    async def wizard_edit_text(self, query: types.CallbackQuery, template_id: int, state: FSMContext):
        """Start the wizard to edit a template's text."""
        await state.clear()
        await state.update_data(template_id=template_id)
        await query.message.edit_text(
            "✏️ Please send the new template text.",
            reply_markup=self.keyboards.cancel_button(f"templates:view:{template_id}")
        )
        await state.set_state(ManagementStates.template_edit_text)

    async def wizard_process_edit_name(self, message: types.Message, state: FSMContext):
        """Process and save the new template name."""
        new_name = message.text.strip()
        data = await state.get_data()
        template_id = data.get("template_id")

        if not template_id:
            await message.reply("Session expired, please start over.")
            await state.clear()
            return

        try:
            await self.template_model.update(template_id, {"name": new_name})
            await message.reply(f"✅ Name updated to '<b>{new_name}</b>'!")
        except Exception as e:
            logger.error(f"Error updating template name: {e}")
            await message.reply(f"❌ An error occurred: {e}")
        finally:
            await state.clear()

    async def wizard_process_edit_text(self, message: types.Message, state: FSMContext):
        """Process and save the new template text."""
        new_text = message.text
        data = await state.get_data()
        template_id = data.get("template_id")

        if not template_id:
            await message.reply("Session expired, please start over.")
            await state.clear()
            return

        try:
            await self.template_model.update(template_id, {"template_text": new_text})
            await message.reply("✅ Template text updated successfully!")
        except Exception as e:
            logger.error(f"Error updating template text: {e}")
            await message.reply(f"❌ An error occurred: {e}")
        finally:
            await state.clear()

    # ==================== TEMPLATE HELP SYSTEM ====================

    async def show_help_main(self, query: types.CallbackQuery):
        """Show the main template help menu with categories."""
        try:
            logger.info(f"[HELP_DEBUG] show_help_main() called")

            text = (
                "📖 <b>Template Help Guide</b>\n\n"
                "Templates let you create custom messages using placeholders. "
                "Placeholders are special words that get replaced with real information about tokens!\n\n"
                "<i>Pick a category to learn more:</i>"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔤 Basic Info", callback_data="templates:help:basic")],
                [InlineKeyboardButton(text="💰 Money Stuff", callback_data="templates:help:money")],
                [InlineKeyboardButton(text="📈 Trading Activity", callback_data="templates:help:trading")],
                [InlineKeyboardButton(text="⏰ Time & History", callback_data="templates:help:time")],
                [InlineKeyboardButton(text="🔗 Links & Special", callback_data="templates:help:links")],
                [InlineKeyboardButton(text="📝 Example Templates", callback_data="templates:help:examples")],
                [InlineKeyboardButton(text="❓ How to Use", callback_data="templates:help:howto")],
                [InlineKeyboardButton(text="🔙 Back to Templates", callback_data="templates:main")]
            ])

            logger.info(f"[HELP_DEBUG] show_help_main() sending message edit")
            await query.message.edit_text(text, reply_markup=keyboard)
            logger.info(f"[HELP_DEBUG] show_help_main() completed successfully")

        except Exception as e:
            logger.error(f"[HELP_DEBUG] ❌ ERROR in show_help_main(): {e}")
            logger.error(f"[HELP_DEBUG] show_help_main() traceback:", exc_info=True)
            try:
                await query.answer("❌ Error loading help menu")
            except:
                logger.error(f"[HELP_DEBUG] Could not answer query in show_help_main() error handler")

    async def show_help_basic(self, query: types.CallbackQuery):
        """Show basic info placeholders help."""
        try:
            logger.info(f"[HELP_DEBUG] show_help_basic() called")

            text = (
                "🔤 <b>Basic Info Placeholders</b>\n\n"
                "These show simple information about the token:\n\n"

                "• <code>{address}</code> - The token's address (like its ID number)\n"
                "• <code>{token_symbol}</code> - Short name (like BTC, ETH)\n"
                "• <code>{token_name}</code> - Full name (like Bitcoin, Ethereum)\n"
                "• <code>{chain_id}</code> - Which blockchain (like solana, ethereum)\n"
                "• <code>{dex_id}</code> - Which exchange (like raydium, uniswap)\n\n"

                "<b>Example:</b>\n"
                "<code>🚀 New token found!\n"
                "Name: {token_name} ({token_symbol})\n"
                "Address: {address}</code>\n\n"

                "<b>This becomes:</b>\n"
                "🚀 New token found!\n"
                "Name: Super Coin (SUPER)\n"
                "Address: ABC123DEF456..."
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Help", callback_data="templates:help:main")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            logger.info(f"[HELP_DEBUG] show_help_basic() completed successfully")

        except Exception as e:
            logger.error(f"[HELP_DEBUG] ❌ ERROR in show_help_basic(): {e}")
            logger.error(f"[HELP_DEBUG] show_help_basic() traceback:", exc_info=True)
            try:
                await query.answer("❌ Error loading basic help")
            except:
                logger.error(f"[HELP_DEBUG] Could not answer query in show_help_basic() error handler")

    async def show_help_money(self, query: types.CallbackQuery):
        """Show money-related placeholders help."""
        try:
            logger.info(f"[HELP_DEBUG] show_help_money() called")

            text = (
                "💰 <b>Money Stuff Placeholders</b>\n\n"
                "These show prices and values:\n\n"

                "• <code>{market_cap}</code> - How much the token is worth in total\n"
                "• <code>{price_usd}</code> - Price in US dollars\n"
                "• <code>{ath}</code> - Highest price ever (All Time High)\n"
                "• <code>{multiplier}</code> - How much it went up since first seen\n"
                "• <code>{fdv}</code> - Fully Diluted Value (fancy market cap)\n"
                "• <code>{liquidity_usd}</code> - How easy it is to buy/sell\n\n"

                "<b>Example:</b>\n"
                "<code>💰 Price: ${price_usd}\n"
                "📊 Market Cap: {market_cap}\n"
                "🚀 Multiplier: {multiplier}x</code>\n\n"

                "<b>This becomes:</b>\n"
                "💰 Price: $0.0045\n"
                "📊 Market Cap: $2.5M\n"
                "🚀 Multiplier: 15.6x"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Help", callback_data="templates:help:main")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            logger.info(f"[HELP_DEBUG] show_help_money() completed successfully")

        except Exception as e:
            logger.error(f"[HELP_DEBUG] ❌ ERROR in show_help_money(): {e}")
            logger.error(f"[HELP_DEBUG] show_help_money() traceback:", exc_info=True)
            try:
                await query.answer("❌ Error loading money help")
            except:
                logger.error(f"[HELP_DEBUG] Could not answer query in show_help_money() error handler")

    async def show_help_trading(self, query: types.CallbackQuery):
        """Show trading activity placeholders help."""
        try:
            logger.info(f"[HELP_DEBUG] show_help_trading() called")

            text = (
                "📈 <b>Trading Activity Placeholders</b>\n\n"
                "These show how much buying and selling happened:\n\n"

                "<b>Volume (how much money traded):</b>\n"
                "• <code>{volume_m5}</code> - Last 5 minutes\n"
                "• <code>{volume_h1}</code> - Last 1 hour\n"
                "• <code>{volume_h6}</code> - Last 6 hours\n"
                "• <code>{volume_h24}</code> - Last 24 hours\n\n"

                "<b>Price changes (how much price went up/down):</b>\n"
                "• <code>{price_change_m5}</code> - Last 5 minutes\n"
                "• <code>{price_change_h1}</code> - Last 1 hour\n"
                "• <code>{price_change_h6}</code> - Last 6 hours\n"
                "• <code>{price_change_h24}</code> - Last 24 hours\n\n"

                "<b>Transactions (number of buys/sells):</b>\n"
                "• <code>{txns_h1_buys}</code> / <code>{txns_h1_sells}</code> - Buys and sells in 1 hour"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📊 See Example", callback_data="templates:help:trading_example")],
                [InlineKeyboardButton(text="🔙 Back to Help", callback_data="templates:help:main")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            logger.info(f"[HELP_DEBUG] show_help_trading() completed successfully")

        except Exception as e:
            logger.error(f"[HELP_DEBUG] ❌ ERROR in show_help_trading(): {e}")
            logger.error(f"[HELP_DEBUG] show_help_trading() traceback:", exc_info=True)
            try:
                await query.answer("❌ Error loading trading help")
            except:
                logger.error(f"[HELP_DEBUG] Could not answer query in show_help_trading() error handler")

    async def show_help_trading_example(self, query: types.CallbackQuery):
        """Show trading activity example."""
        try:
            logger.info(f"[HELP_DEBUG] show_help_trading_example() called")

            text = (
                "📈 <b>Trading Activity Example</b>\n\n"

                "<b>Template:</b>\n"
                "<code>📊 24h Stats:\n"
                "Volume: {volume_h24}\n"
                "Price Change: {price_change_h24}%\n"
                "Buys: {txns_h24_buys} | Sells: {txns_h24_sells}</code>\n\n"

                "<b>This becomes:</b>\n"
                "📊 24h Stats:\n"
                "Volume: $1.2M\n"
                "Price Change: +45.6%\n"
                "Buys: 1,234 | Sells: 567"
            )

            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Trading", callback_data="templates:help:trading")]
            ])

            await query.message.edit_text(text, reply_markup=keyboard)
            logger.info(f"[HELP_DEBUG] show_help_trading_example() completed successfully")

        except Exception as e:
            logger.error(f"[HELP_DEBUG] ❌ ERROR in show_help_trading_example(): {e}")
            logger.error(f"[HELP_DEBUG] show_help_trading_example() traceback:", exc_info=True)
            try:
                await query.answer("❌ Error loading trading example")
            except:
                logger.error(f"[HELP_DEBUG] Could not answer query in show_help_trading_example() error handler")

    async def show_help_time(self, query: types.CallbackQuery):
        """Show time and history placeholders help."""
        text = (
            "⏰ <b>Time & History Placeholders</b>\n\n"
            "These show when things happened:\n\n"

            "• <code>{pair_created_at}</code> - When the token was first created\n"
            "• <code>{mention_count}</code> - How many times we've seen this token\n"
            "• <code>{call_history}</code> - List of recent calls for this token\n\n"

            "<b>Example:</b>\n"
            "<code>⏰ Created: {pair_created_at}\n"
            "📞 Times called: {mention_count}\n"
            "📋 Recent history:\n"
            "{call_history}</code>\n\n"

            "<b>This becomes:</b>\n"
            "⏰ Created: 2h 15m ago\n"
            "📞 Times called: 3\n"
            "📋 Recent history:\n"
            "🌕 Recent History\n"
            "• Alpha Chat - 2h ago\n"
            "• Beta Group - 1h ago"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Help", callback_data="templates:help:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_links(self, query: types.CallbackQuery):
        """Show links and special placeholders help."""
        text = (
            "🔗 <b>Links & Special Placeholders</b>\n\n"
            "These show special info and useful links:\n\n"

            "<b>Special Info:</b>\n"
            "• <code>{bonding_status}</code> - 'Bonded' or 'Not Bonded'\n"
            "• <code>{dex_paid}</code> - ✅ if DEX info is paid, ❌ if not\n"
            "• <code>{pair_address}</code> - Trading pair address\n\n"

            "<b>Useful Links:</b>\n"
            "• <code>{dexscreener_link}</code> - Link to DexScreener\n"
            "• <code>{defined_link}</code> - Link to Defined.fi\n\n"

            "<b>Example:</b>\n"
            "<code>🔗 Check it out:\n"
            "DexScreener: {dexscreener_link}\n"
            "Status: {bonding_status}</code>\n\n"

            "<b>This becomes:</b>\n"
            "🔗 Check it out:\n"
            "DexScreener: https://dexscreener.com/solana/ABC123...\n"
            "Status: Bonded"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Help", callback_data="templates:help:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_examples(self, query: types.CallbackQuery):
        """Show ready-to-use template examples."""
        text = (
            "📝 <b>Ready-to-Use Template Examples</b>\n\n"
            "Copy these examples and customize them!\n\n"
            "<i>Pick an example to see:</i>"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Simple Call", callback_data="templates:help:example_simple")],
            [InlineKeyboardButton(text="📊 Detailed Stats", callback_data="templates:help:example_detailed")],
            [InlineKeyboardButton(text="⚡ Quick Alert", callback_data="templates:help:example_quick")],
            [InlineKeyboardButton(text="🎯 Premium Call", callback_data="templates:help:example_premium")],
            [InlineKeyboardButton(text="🔙 Back to Help", callback_data="templates:help:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_example_simple(self, query: types.CallbackQuery):
        """Show simple call template example."""
        text = (
            "🚀 <b>Simple Call Template</b>\n\n"
            "Perfect for basic token calls:\n\n"
            "<code>🚀 NEW TOKEN ALERT!\n\n"
            "💎 {token_name} ({token_symbol})\n"
            "💰 Market Cap: {market_cap}\n"
            "📊 24h Volume: {volume_h24}\n"
            "⏰ Created: {pair_created_at}\n\n"
            "🔗 {dexscreener_link}\n\n"
            "#crypto #{token_symbol}</code>\n\n"

            "<b>✨ This template shows:</b>\n"
            "• Token name and symbol\n"
            "• Basic money info\n"
            "• How old the token is\n"
            "• Link to check it out"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Template", callback_data="templates:help:copy_simple")],
            [InlineKeyboardButton(text="🔙 Back to Examples", callback_data="templates:help:examples")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_example_detailed(self, query: types.CallbackQuery):
        """Show detailed stats template example."""
        text = (
            "📊 <b>Detailed Stats Template</b>\n\n"
            "For serious traders who want all the info:\n\n"
            "<code>📊 DETAILED TOKEN ANALYSIS\n\n"
            "🔸 {token_name} ({token_symbol})\n"
            "💰 Price: ${price_usd}\n"
            "📈 Market Cap: {market_cap}\n"
            "🚀 ATH: {ath}\n"
            "⚡ Multiplier: {multiplier}x\n\n"
            "📊 24H STATS:\n"
            "Volume: {volume_h24}\n"
            "Price Change: {price_change_h24}%\n"
            "Buys: {txns_h24_buys} | Sells: {txns_h24_sells}\n\n"
            "🔗 Analysis: {defined_link}\n"
            "📱 Chart: {dexscreener_link}\n\n"
            "{call_history}</code>\n\n"

            "<b>✨ This template shows:</b>\n"
            "• Complete price info\n"
            "• Trading statistics\n"
            "• Multiple useful links\n"
            "• Call history"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Template", callback_data="templates:help:copy_detailed")],
            [InlineKeyboardButton(text="🔙 Back to Examples", callback_data="templates:help:examples")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_example_quick(self, query: types.CallbackQuery):
        """Show quick alert template example."""
        text = (
            "⚡ <b>Quick Alert Template</b>\n\n"
            "Short and sweet for fast alerts:\n\n"
            "<code>⚡ QUICK ALERT!\n\n"
            "{token_symbol} | {market_cap}\n"
            "📈 {price_change_h24}% (24h)\n"
            "🔗 {dexscreener_link}</code>\n\n"

            "<b>✨ This template is:</b>\n"
            "• Super short and fast\n"
            "• Shows key info only\n"
            "• Perfect for quick notifications\n"
            "• Easy to read on mobile"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Template", callback_data="templates:help:copy_quick")],
            [InlineKeyboardButton(text="🔙 Back to Examples", callback_data="templates:help:examples")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_example_premium(self, query: types.CallbackQuery):
        """Show premium call template example."""
        text = (
            "🎯 <b>Premium Call Template</b>\n\n"
            "Fancy template for VIP groups:\n\n"
            "<code>🎯 PREMIUM TOKEN CALL\n\n"
            "✨ {token_name} ({token_symbol})\n"
            "💎 Current: ${price_usd}\n"
            "🏆 ATH: {ath}\n"
            "🚀 Multiplier: {multiplier}x from launch\n"
            "⏰ Age: {pair_created_at}\n\n"
            "📊 TRADING METRICS:\n"
            "└ Volume (24h): {volume_h24}\n"
            "└ Change (24h): {price_change_h24}%\n"
            "└ Liquidity: {liquidity_usd}\n"
            "└ Status: {bonding_status}\n\n"
            "📞 Called {mention_count} times\n\n"
            "🔗 RESEARCH:\n"
            "└ Chart: {dexscreener_link}\n"
            "└ Data: {defined_link}\n\n"
            "⚠️ DYOR - Not Financial Advice</code>\n\n"

            "<b>✨ This template has:</b>\n"
            "• Professional formatting\n"
            "• Complete information\n"
            "• Clean organization\n"
            "• Disclaimer included"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📋 Copy Template", callback_data="templates:help:copy_premium")],
            [InlineKeyboardButton(text="🔙 Back to Examples", callback_data="templates:help:examples")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def show_help_howto(self, query: types.CallbackQuery):
        """Show how to use templates."""
        text = (
            "❓ <b>How to Use Templates</b>\n\n"

            "<b>Step 1: Create a Template</b>\n"
            "• Go to Templates menu\n"
            "• Click '➕ Create New Template'\n"
            "• Give it a name\n"
            "• Write your message with placeholders\n\n"

            "<b>Step 2: Use Placeholders</b>\n"
            "• Type placeholders like: <code>{token_symbol}</code>\n"
            "• You can also use: <code>${token_symbol}</code>\n"
            "• Both work the same way!\n\n"

            "<b>Step 3: Assign to Groups</b>\n"
            "• Click 'Assign' on your template\n"
            "• Pick which groups should use it\n"
            "• Save your choices\n\n"

            "<b>🎉 That's it!</b>\n"
            "Now when tokens are called in those groups, your custom template will be used instead of the default message!"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📖 View Placeholders", callback_data="templates:help:main")],
            [InlineKeyboardButton(text="🔙 Back to Templates", callback_data="templates:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)

    async def handle_help_copy(self, query: types.CallbackQuery, template_type: str):
        """Handle copying template examples."""
        templates = {
            "simple": (
                "🚀 NEW TOKEN ALERT!\n\n"
                "💎 {token_name} ({token_symbol})\n"
                "💰 Market Cap: {market_cap}\n"
                "📊 24h Volume: {volume_h24}\n"
                "⏰ Created: {pair_created_at}\n\n"
                "🔗 {dexscreener_link}\n\n"
                "#crypto #{token_symbol}"
            ),
            "detailed": (
                "📊 DETAILED TOKEN ANALYSIS\n\n"
                "🔸 {token_name} ({token_symbol})\n"
                "💰 Price: ${price_usd}\n"
                "📈 Market Cap: {market_cap}\n"
                "🚀 ATH: {ath}\n"
                "⚡ Multiplier: {multiplier}x\n\n"
                "📊 24H STATS:\n"
                "Volume: {volume_h24}\n"
                "Price Change: {price_change_h24}%\n"
                "Buys: {txns_h24_buys} | Sells: {txns_h24_sells}\n\n"
                "🔗 Analysis: {defined_link}\n"
                "📱 Chart: {dexscreener_link}\n\n"
                "{call_history}"
            ),
            "quick": (
                "⚡ QUICK ALERT!\n\n"
                "{token_symbol} | {market_cap}\n"
                "📈 {price_change_h24}% (24h)\n"
                "🔗 {dexscreener_link}"
            ),
            "premium": (
                "🎯 PREMIUM TOKEN CALL\n\n"
                "✨ {token_name} ({token_symbol})\n"
                "💎 Current: ${price_usd}\n"
                "🏆 ATH: {ath}\n"
                "🚀 Multiplier: {multiplier}x from launch\n"
                "⏰ Age: {pair_created_at}\n\n"
                "📊 TRADING METRICS:\n"
                "└ Volume (24h): {volume_h24}\n"
                "└ Change (24h): {price_change_h24}%\n"
                "└ Liquidity: {liquidity_usd}\n"
                "└ Status: {bonding_status}\n\n"
                "📞 Called {mention_count} times\n\n"
                "🔗 RESEARCH:\n"
                "└ Chart: {dexscreener_link}\n"
                "└ Data: {defined_link}\n\n"
                "⚠️ DYOR - Not Financial Advice"
            )
        }

        template_text = templates.get(template_type, "Template not found")

        text = (
            f"📋 <b>Template Copied!</b>\n\n"
            f"Here's your template text. Copy and paste it when creating a new template:\n\n"
            f"<code>{template_text}</code>\n\n"
            f"💡 <b>Tip:</b> You can modify this template to fit your style!"
        )

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Examples", callback_data="templates:help:examples")],
            [InlineKeyboardButton(text="🏠 Main Help", callback_data="templates:help:main")]
        ])

        await query.message.edit_text(text, reply_markup=keyboard)