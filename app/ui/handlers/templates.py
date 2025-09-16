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

    async def show_templates_menu(self, query: types.CallbackQuery):
        """Display the main templates management menu."""
        try:
            templates = await self.template_model.get_all_with_assignment_counts()
            text = f"<b>📝 Custom Post Templates ({len(templates)})</b>\n\n"
            text += "Manage templates for call messages."

            keyboard_rows = []
            for t in templates:
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{t['name']} ({t['assignment_count']} assigned)",
                        callback_data=f"templates:view:{t['id']}"
                    )
                ])

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
        action = parts[1]
        item_id = int(parts[2]) if len(parts) > 2 else None

        if action == 'main':
            await self.show_templates_menu(query)
        elif action == 'add':
            await self.wizard_start_add(query, state)
        elif action == 'view':
            await self.show_template_details(query, item_id)
        elif action == 'delete':
            await self.confirm_delete(query, item_id)
        elif action == 'confirm_delete':
            await self.delete_template(query, item_id)
        elif action == 'assign':
            await self.show_assignment_menu(query, item_id, state)
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

            text = f"<b>📝 Template: {template['name']}</b>\n\n"
            text += f"<b>Assignments:</b> {len(assigned_groups)} groups\n\n"
            text += "<b>Preview:</b>\n"
            text += f"<pre>{template['template_text']}</pre>"

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

    async def show_assignment_menu(self, query: types.CallbackQuery, template_id: int, state: FSMContext):
        """Show the menu for assigning a template to groups."""
        try:
            template = await self.template_model.get_by_id(template_id)
            if not template:
                await query.answer("❌ Template not found.")
                return

            all_groups = await self.group_model.get_groups_with_stats()
            assigned_groups_records = await self.assignment_model.get_assigned_groups(template_id)
            assigned_group_ids = {g['id'] for g in assigned_groups_records}

            await state.set_state(ManagementStates.template_assign_select_groups)
            await state.update_data(current_assignments=list(assigned_group_ids))

            text = f"🤝 Assign Template: <b>{template['name']}</b>\n\n"
            text += "Select which target groups should use this template."

            keyboard_rows = []
            for group in all_groups:
                is_assigned = group['id'] in assigned_group_ids
                status_icon = "✅" if is_assigned else "❌"
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {group_name}",
                        callback_data=f"templates:toggle_assign:{template_id}:{group['id']}"
                    )
                ])
            
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
            current_assignments = data.get('current_assignments', [])

            if group_id in current_assignments:
                current_assignments.remove(group_id)
            else:
                current_assignments.append(group_id)
            
            await state.update_data(current_assignments=current_assignments)

            # Redraw the menu
            template = await self.template_model.get_by_id(template_id)
            all_groups = await self.group_model.get_groups_with_stats()

            text = f"🤝 Assign Template: <b>{template['name']}</b>\n\n"
            text += "Select which target groups should use this template."

            keyboard_rows = []
            for group in all_groups:
                is_assigned = group['id'] in current_assignments
                status_icon = "✅" if is_assigned else "❌"
                group_name = group.get('display_name') or group['title'] or f"Chat {group['tg_chat_id']}"
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text=f"{status_icon} {group_name}",
                        callback_data=f"templates:toggle_assign:{template_id}:{group['id']}"
                    )
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="💾 Save Assignments", callback_data=f"templates:save_assign:{template_id}")
            ])
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Cancel", callback_data=f"templates:view:{template_id}")
            ])

            await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows))
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