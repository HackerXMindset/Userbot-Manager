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
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="➕ Add Target", callback_data="targets:add"),
                    InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:targets")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing targets menu: {e}")
            await query.answer("❌ Error loading targets")
