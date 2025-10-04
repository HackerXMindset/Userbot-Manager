"""
Handler for Dynamic Reply management UI.
"""
import logging
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from app.ui.states import ManagementStates

logger = logging.getLogger(__name__)


class DynamicReplyHandler:
    """Handles Dynamic Reply UI interactions."""

    def __init__(self, reply_model, keyboards):
        self.reply_model = reply_model
        self.keyboards = keyboards

    async def show_menu(self, query: types.CallbackQuery):
        """Show Dynamic Reply main menu."""
        logger.debug("[DYNAMIC_REPLY_UI] Showing main menu")

        text = "<b>💬 Dynamic Reply Management</b>\n\n"
        text += "Manage preset replies for auto-reply when bots DM after button clicks.\n\n"
        text += "Use <code>{ticker}</code> placeholder in your messages - it will be replaced with the rule's ticker value."

        await query.message.edit_text(
            text,
            reply_markup=self.keyboards.dynamic_reply_menu(),
            parse_mode="HTML"
        )
        await query.answer()

    async def start_add_reply(self, query: types.CallbackQuery, state: FSMContext):
        """Start wizard to add new reply."""
        logger.debug("[DYNAMIC_REPLY_UI] Starting add reply wizard")

        text = "<b>➕ Add New Reply</b>\n\n"
        text += "Send your reply message. You can use <code>{ticker}</code> as a placeholder.\n\n"
        text += "<i>Example: 'Buying {ticker} to the moon! 🚀'</i>"

        await query.message.edit_text(
            text,
            reply_markup=self.keyboards.cancel_button("dynamic_reply:menu"),
            parse_mode="HTML"
        )
        await state.set_state(ManagementStates.adding_dynamic_reply_message)
        await query.answer()

    async def process_add_reply(self, message: types.Message, state: FSMContext):
        """Save new reply message."""
        reply_text = message.text.strip()

        logger.info(f"[DYNAMIC_REPLY_UI] Adding new reply: {reply_text[:50]}...")

        # Add to database
        reply_id = await self.reply_model.add_reply(reply_text)

        await message.reply(f"✅ Reply added successfully! (ID: {reply_id})")
        await state.clear()

    async def show_reply_list(self, query: types.CallbackQuery, page: int = 1):
        """Show all replies with usage stats and pagination."""
        logger.debug("[DYNAMIC_REPLY_UI] Showing reply list")

        replies = await self.reply_model.get_all_replies()

        if not replies:
            text = "<b>📋 Reply List</b>\n\nNo replies configured yet."
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.dynamic_reply_menu(),
                parse_mode="HTML"
            )
            await query.answer()
            return

        text = "<b>📋 All Dynamic Replies</b>\n\n"
        text += f"Total: {len(replies)} replies\n\n"
        text += "<i>Click a reply to delete it.</i>"

        # For list view, we show 0 uses since we don't have a specific rule context
        usage_stats = {reply['id']: 0 for reply in replies}

        await query.message.edit_text(
            text,
            reply_markup=self.keyboards.dynamic_reply_list(replies, usage_stats, page),
            parse_mode="HTML"
        )
        await query.answer()

    async def delete_reply(self, query: types.CallbackQuery, reply_id: int):
        """Delete a reply message."""
        logger.info(f"[DYNAMIC_REPLY_UI] Deleting reply {reply_id}")

        success = await self.reply_model.delete_reply(reply_id)

        if success:
            await query.answer("✅ Reply deleted", show_alert=False)
        else:
            await query.answer("❌ Failed to delete reply", show_alert=True)

        # Refresh list
        await self.show_reply_list(query)
