from aiogram import types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
import logging

from app.ui.keyboards import Keyboards
from app.models import ScheduleModel

logger = logging.getLogger(__name__)

class SchedulesHandler:
    """Handler for schedule management"""
    
    def __init__(self, db, keyboards: Keyboards):
        self.db = db
        self.keyboards = keyboards
        self.schedule_model = ScheduleModel(db)
    
    async def show_schedules_menu(self, query: types.CallbackQuery):
        """Show schedules overview"""
        try:
            # Get schedules with group info
            schedules = await self.db.fetch("""
                SELECT s.*, g.title as group_title, g.tg_chat_id
                FROM group_schedules s
                JOIN groups g ON g.id = s.group_id
                ORDER BY g.title, s.start_time
            """)
            
            text = "<b>📅 Schedules Overview</b>\n\n"
            
            if not schedules:
                text += "No schedules configured.\nAdd groups and set their schedules first."
            else:
                current_group = None
                for schedule in schedules:
                    group_name = schedule['group_title'] or f"Chat {schedule['tg_chat_id']}"
                    if current_group != group_name:
                        text += f"\n<b>{group_name}</b>\n"
                        current_group = group_name
                    
                    days = self._format_weekdays(schedule['weekdays'])
                    text += (
                        f"• {schedule['start_time']} - {schedule['end_time']} "
                        f"({days}) Max: {schedule['max_calls_in_window'] or '∞'}\n"
                    )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🔄 Refresh", callback_data="menu:schedules"),
                    InlineKeyboardButton(text="📈 Active Now", callback_data="schedules:active")
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing schedules menu: {e}")
            await query.answer("❌ Error loading schedules")
    
    def _format_weekdays(self, weekdays: List[int]) -> str:
        """Format weekdays list to readable string"""
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        if len(weekdays) == 7:
            return "Daily"
        elif set(weekdays) == {1, 2, 3, 4, 5}:
            return "Weekdays"
        elif set(weekdays) == {6, 7}:
            return "Weekends"
        else:
            return ", ".join([day_names[d-1] for d in sorted(weekdays)])
