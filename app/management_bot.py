import asyncio
import logging
from typing import Dict, Any, Optional, List
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from app.config import settings
from app.db import db
from app.ui.keyboards import Keyboards
from app.ui.states import ManagementStates
from app.ui.handlers import (
    MenuHandler, GroupsHandler, UserbotsHandler, 
    SchedulesHandler, SourcesHandler, AlertsHandler, PnlHandler,
    NotificationsHandler, AutoClickHandler, CurateAlphaHandler
)

logger = logging.getLogger(__name__)

class ManagementBot:
    def __init__(self):
        self.bot = Bot(token=settings.mgmt_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher(storage=MemoryStorage())
        self.keyboards = Keyboards()
        self.system_manager = None
        
        # Initialize handlers
        self.menu_handler = MenuHandler(db, self.keyboards)
        self.groups_handler = GroupsHandler(db, self.keyboards)
        self.userbots_handler = UserbotsHandler(db, self.keyboards, self)
        self.schedules_handler = SchedulesHandler(db, self.keyboards)
        self.sources_handler = SourcesHandler(db, self.keyboards)
        self.alerts_handler = AlertsHandler(db, self.keyboards)
        self.pnl_handler = PnlHandler(db, self.keyboards)
        self.notifications_handler = NotificationsHandler(db, self.keyboards)
        self.auto_click_handler = AutoClickHandler(db, self.keyboards)
        self.curate_alpha_handler = CurateAlphaHandler(db, self.keyboards)
        
        self.setup_handlers()

    def set_system_manager(self, manager):
        """Set the SystemManager instance."""
        self.system_manager = manager
    
    def setup_handlers(self):
        """Register all handlers"""
        
        # Commands
        self.dp.message.register(
            self.cmd_menu,
            Command(commands=['menu', 'start']),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Main menu callbacks
        self.dp.callback_query.register(
            self.handle_main_menu,
            F.data.startswith('menu:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Groups
        self.dp.callback_query.register(
            self.groups_handler.handle_group_action,
            F.data.startswith(('group:', 'groups_page:')),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Userbot assignments
        self.dp.callback_query.register(
            self.handle_userbot_assignment,
            F.data.startswith('assign:userbot:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Schedules
        self.dp.callback_query.register(
            self.handle_schedules,
            F.data.startswith('sched:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Userbots
        self.dp.callback_query.register(
            self.userbots_handler.handle_userbot_action,
            F.data.startswith('userbot:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        
        
        # Tracking actions
        self.dp.callback_query.register(
            self.handle_tracking_action,
            F.data.startswith('tracking:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Cleanup confirmation
        self.dp.callback_query.register(
            self.confirm_cleanup,
            F.data == 'confirm_cleanup',
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Tracking time period selection
        self.dp.callback_query.register(
            self.handle_tracking_time,
            F.data.startswith('tracking_time:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        
        
        
        # Sources
        self.dp.callback_query.register(
            self.sources_handler.handle_sources_action,
            F.data.startswith(('sources:', 'add_route_page:', 'sources_manage_page:')),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # Alerts
        self.dp.callback_query.register(
            self.alerts_handler.handle_alerts_action,
            F.data.startswith('alerts:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.alerts_handler.handle_gains_preset,
            F.data.startswith('gains:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.alerts_handler.handle_drop_setting,
            F.data.startswith('drop:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        # PNL
        self.dp.callback_query.register(
            self.pnl_handler.handle_pnl_action,
            F.data.startswith('pnl:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        # Notifications
        self.dp.callback_query.register(
            self.notifications_handler.handle_notifications_action,
            F.data.startswith('notifications:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        # Auto Click
        self.dp.callback_query.register(
            self.auto_click_handler.handle_auto_click_action,
            F.data.startswith('auto_click:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.auto_click_handler.wizard_process_target_group,
            F.data.startswith('auto_click_wizard:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        # Curate Alpha
        self.dp.callback_query.register(
            self.curate_alpha_handler.handle_curate_alpha_action,
            F.data.startswith('curate_alpha:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        
        
        # Schedule management (schedule:add, schedule:delete)
        self.dp.callback_query.register(
            self.handle_schedule_action,
            F.data.startswith('schedule:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        
        # Group deletion confirmation
        self.dp.callback_query.register(
            self.groups_handler.delete_group,
            F.data.startswith('confirm_delete_group:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.handle_source_group_selection,
            F.data.startswith('source_group:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.handle_source_type_selection,
            F.data.startswith('source_type:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.handle_global_source_type_selection,
            F.data.startswith('source_global_type:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.callback_query.register(
            self.handle_source_edit,
            F.data.startswith('source_edit:'),
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        # State handlers
        self.dp.message.register(
            self.groups_handler.process_group_input,
            ManagementStates.adding_group,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.process_userbot_phone,
            ManagementStates.userbot_login_phone,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.userbots_handler.process_code_input,
            ManagementStates.userbot_login_code,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.userbots_handler.process_2fa_input,
            ManagementStates.userbot_login_2fa,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.userbots_handler.process_userbot_name_input,
            ManagementStates.userbot_set_name,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.groups_handler.process_group_name_input,
            ManagementStates.group_set_name,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.sources_handler.process_source_input,
            ManagementStates.adding_source_chat_id,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.sources_handler.process_user_input,
            ManagementStates.adding_source_user_id,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.sources_handler.process_source_name_input,
            ManagementStates.source_set_name,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.pnl_handler.wizard_process_user_id_input,
            ManagementStates.pnl_add_monitored_user_id,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.pnl_handler.wizard_process_destination_input,
            ManagementStates.pnl_add_rule_destination,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.pnl_handler.wizard_process_user_id_input,
            ManagementStates.pnl_add_replying_user_id,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.notifications_handler.process_notification_channel_input,
            ManagementStates.setting_notification_channel,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.notifications_handler.process_blacklist_input,
            ManagementStates.adding_blacklist_user,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.auto_click_handler.wizard_process_bot_id,
            ManagementStates.adding_auto_click_rule_bot_id,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.auto_click_handler.wizard_process_button_text,
            ManagementStates.adding_auto_click_rule_button_text,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.curate_alpha_handler.wizard_process_name,
            ManagementStates.curate_alpha_add_rule_name,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.curate_alpha_handler.wizard_process_destination,
            ManagementStates.curate_alpha_set_destination,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.curate_alpha_handler.process_field_edit,
            ManagementStates.curate_alpha_edit_field,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        self.dp.message.register(
            self.curate_alpha_handler.process_field_edit,
            ManagementStates.curate_alpha_edit_field,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )

        
        
        
        # Custom schedule input handlers
        self.dp.message.register(
            self.process_start_time_input,
            ManagementStates.custom_schedule_start_time,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.process_end_time_input,
            ManagementStates.custom_schedule_end_time,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        self.dp.message.register(
            self.process_max_calls_input,
            ManagementStates.custom_schedule_max_calls,
            F.from_user.id.in_(settings.admin_telegram_ids_list)
        )
        
        
        
        # Error handler  
        self.dp.errors.register(self.handle_errors)
    
    async def cmd_menu(self, message: types.Message):
        """Handle /menu command"""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return
        
        status_text = await self.menu_handler.get_status_text()
        
        await message.answer(
            f"<b>🎛 Management Console</b>\n\n{status_text}",
            reply_markup=self.keyboards.main_menu()
        )
    
    async def handle_main_menu(self, query: types.CallbackQuery):
        """Handle main menu navigation"""
        action = query.data.split(':')[1]
        
        if action == 'main':
            await self.menu_handler.show_main_menu(query)
        elif action == 'status':
            await self.menu_handler.show_detailed_status(query)
        elif action == 'groups':
            await self.groups_handler.show_groups_menu(query)
        elif action == 'schedules':
            await self.schedules_handler.show_schedules_menu(query)
        elif action == 'quotas':
            await self.show_quotas_menu(query)
        elif action == 'userbots':
            await self.userbots_handler.show_userbots_menu(query)
        elif action == 'sources':
            await self.sources_handler.show_sources_menu(query)
        elif action == 'alerts':
            await self.alerts_handler.show_alerts_menu(query)
        elif action == 'tracking':
            await self.menu_handler.show_tracking_menu(query)
        elif action == 'pnl':
            await self.pnl_handler.show_rules_list(query)
        elif action == 'notifications':
            await self.notifications_handler.show_notifications_menu(query)
        elif action == 'auto_click':
            await self.auto_click_handler.show_auto_click_menu(query)
        elif action == 'curate_alpha':
            await self.curate_alpha_handler.show_curate_alpha_menu(query)
        elif action == 'close':
            await query.message.delete()
        
        await query.answer()
    
    async def handle_tracking_action(self, query: types.CallbackQuery):
        """Handle tracking-related actions"""
        try:
            # Parse callback: tracking:action
            action = query.data.split(':', 1)[1]
            
            if action == 'cleanup':
                await self.menu_handler.confirm_cleanup(query)
            elif action == 'cleanup:confirm':
                await self.menu_handler.execute_cleanup(query)
            else:
                await query.answer("❌ Unknown tracking action")
                
        except Exception as e:
            logger.error(f"Error handling tracking action: {e}")
            await query.answer("❌ Error processing tracking action")
    
    async def cleanup_tracking_data(self, query: types.CallbackQuery):
        """Clean up old tracking data"""
        try:
            # Show confirmation dialog
            text = (
                f"<b>🧹 Cleanup Tracking Data</b>\n\n"
                f"This will remove:\n"
                f"• Stopped tokens (older than 24h)\n"
                f"• Failed call records (older than 7 days)\n"
                f"<b>⚠️ This action cannot be undone!</b>\n"
                f"Are you sure you want to proceed?"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes, Cleanup", callback_data="confirm_cleanup"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data="menu:tracking")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing cleanup confirmation: {e}")
            await query.answer("❌ Error loading cleanup dialog")
    
    async def confirm_cleanup(self, query: types.CallbackQuery):
        """Actually perform the cleanup"""
        try:
            # Count items to be cleaned
            stopped_tokens = await db.fetchval(
                """
                SELECT COUNT(*) FROM tokens_tracked 
                WHERE status = 'stopped' AND first_seen_at < NOW() - INTERVAL '1 day'
                """
            )
            
            old_calls = await db.fetchval(
                """
                SELECT COUNT(*) FROM calls 
                WHERE status != 'sent' AND created_at < NOW() - INTERVAL '7 days'
                """
            )
            
            
            # Perform cleanup
            await db.execute(
                """
                DELETE FROM tokens_tracked 
                WHERE status = 'stopped' AND first_seen_at < NOW() - INTERVAL '1 day'
                """
            )
            
            await db.execute(
                """
                DELETE FROM calls 
                WHERE status != 'sent' AND created_at < NOW() - INTERVAL '7 days'
                """
            )
            
            
            total_cleaned = stopped_tokens + old_calls
            
            text = (
                f"✅ <b>Cleanup Completed</b>\n\n"
                f"<b>Items Removed:</b>\n"
                f"├ Stopped Tokens: {stopped_tokens}\n"
                f"├ Failed Calls: {old_calls}\n"
                f"└ Total: {total_cleaned} records\n\n"
                f"Database cleanup successful!"
            )
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 Back to Tracking", callback_data="menu:tracking")],
                [InlineKeyboardButton(text="🏠 Main Menu", callback_data="menu:main")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Cleanup completed successfully!")
            
        except Exception as e:
            logger.error(f"Error performing cleanup: {e}")
            await query.answer("❌ Error performing cleanup")
    
    async def handle_tracking_time(self, query: types.CallbackQuery):
        """Handle tracking time period selection"""
        try:
            # Parse callback: tracking_time:1d
            timeframe = query.data.split(':', 1)[1]
            
            # Show tracking menu with selected timeframe
            await self.menu_handler.show_tracking_menu(query, timeframe)
            
        except Exception as e:
            logger.error(f"Error handling tracking time selection: {e}")
            await query.answer("❌ Error loading tracking data")
    
    
    async def handle_schedules(self, query: types.CallbackQuery):
        """Handle schedule-related callbacks"""
        # Implementation for schedule management
        await query.answer("Schedule management coming soon!")
    
    async def handle_schedule_action(self, query: types.CallbackQuery):
        """Handle schedule management actions (add/delete)"""
        from aiogram.fsm.context import FSMContext
        from aiogram.fsm.storage.base import StorageKey
        
        # Get state manually for callback handlers
        storage_key = StorageKey(bot_id=query.bot.id, chat_id=query.from_user.id, user_id=query.from_user.id)
        state = FSMContext(storage=self.dp.storage, key=storage_key)
        try:
            parts = query.data.split(':')
            logger.debug(f"Schedule action callback - parts: {parts}")
            action = parts[1]
            
            if action == 'add':
                group_id = int(parts[2])
                await self.show_add_schedule_wizard(query, group_id)
            elif action == 'template':
                template = parts[2]
                group_id = int(parts[3])
                await self.create_schedule_from_template(query, group_id, template)
            elif action == 'custom':
                group_id = int(parts[2])
                await self.start_custom_schedule(query, group_id, state)
            elif action == 'delete':
                schedule_id = int(parts[2])
                await self.confirm_delete_schedule(query, schedule_id)
            elif action == 'confirm_delete':
                schedule_id = int(parts[2])
                await self.delete_schedule(query, schedule_id)
            elif action == 'day':
                day = int(parts[2])
                group_id = int(parts[3])
                await self.toggle_schedule_day(query, group_id, day, state)
            elif action == 'preset':
                preset = parts[2]
                group_id = int(parts[3])
                await self.set_schedule_preset_days(query, group_id, preset, state)
            elif action == 'set_times':
                group_id = int(parts[2])
                await self.show_custom_schedule_times(query, group_id, state)
            elif action == 'finish_custom':
                group_id = int(parts[2])
                max_calls_setting = parts[3]
                await self.finish_custom_schedule(query, group_id, max_calls_setting, state)
            elif action == 'time':
                logger.debug(f"Time action callback data: {query.data}")
                time_type = parts[2]  # start/end
                time_value = parts[3]  # e.g., "09:00" or "custom"
                if time_value == 'custom':
                    time_for = parts[4]  # start/end
                    group_id = int(parts[5])
                    logger.debug(f"Custom time - group_id: {group_id}")
                    await self.show_custom_time_input(query, group_id, time_for, state)
                else:
                    # Get group_id from state data instead of callback to avoid parsing errors
                    data = await state.get_data()
                    group_id = data.get('group_id', int(parts[4])) if data else int(parts[4])
                    logger.debug(f"Time selection - group_id from state: {group_id} (callback had: {parts[4]})")
                    await self.handle_time_selection(query, group_id, time_type, time_value, state)
            elif action == 'maxcalls':
                max_calls = parts[2]
                group_id = int(parts[3])
                await self.handle_max_calls_selection(query, group_id, max_calls, state)
            else:
                await query.answer("❌ Unknown schedule action")
                
        except Exception as e:
            logger.error(f"Error handling schedule action: {e}")
            await query.answer("❌ Error processing schedule action")
    
    async def show_add_schedule_wizard(self, query: types.CallbackQuery, group_id: int):
        """Show the schedule creation wizard"""
        try:
            # Get group info
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                await query.answer("❌ Group not found")
                return
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = f"<b>➕ Add Schedule for {group_name}</b>\n\n"
            text += "Create a time window when this group can send calls.\n\n"
            text += "<b>Schedule Templates:</b>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🌅 Morning (9-12)", callback_data=f"schedule:template:morning:{group_id}"),
                    InlineKeyboardButton(text="🌞 Afternoon (12-17)", callback_data=f"schedule:template:afternoon:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="🌆 Evening (17-22)", callback_data=f"schedule:template:evening:{group_id}"),
                    InlineKeyboardButton(text="🌙 Night (22-6)", callback_data=f"schedule:template:night:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="☀️ Business Hours (9-17)", callback_data=f"schedule:template:business:{group_id}"),
                    InlineKeyboardButton(text="🕐 24/7", callback_data=f"schedule:template:24h:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="⚙️ Custom", callback_data=f"schedule:custom:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back", callback_data=f"group:schedules:{group_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing add schedule wizard: {e}")
            await query.answer("❌ Error loading schedule wizard")
    
    async def start_custom_schedule(self, query: types.CallbackQuery, group_id: int, state: FSMContext):
        """Start custom schedule creation wizard"""
        try:
            # Get group info
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            if not group:
                await query.answer("❌ Group not found")
                return
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += "First, select the days when this schedule should be active:\n\n"
            text += "<b>Select Days:</b>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📅 Monday", callback_data=f"schedule:day:1:{group_id}"),
                    InlineKeyboardButton(text="📅 Tuesday", callback_data=f"schedule:day:2:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="📅 Wednesday", callback_data=f"schedule:day:3:{group_id}"),
                    InlineKeyboardButton(text="📅 Thursday", callback_data=f"schedule:day:4:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="📅 Friday", callback_data=f"schedule:day:5:{group_id}"),
                    InlineKeyboardButton(text="📅 Saturday", callback_data=f"schedule:day:6:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="📅 Sunday", callback_data=f"schedule:day:7:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="☑️ Weekdays (M-F)", callback_data=f"schedule:preset:weekdays:{group_id}"),
                    InlineKeyboardButton(text="☑️ Weekends (S-S)", callback_data=f"schedule:preset:weekends:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="☑️ All Days", callback_data=f"schedule:preset:daily:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back", callback_data=f"schedule:add:{group_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
            # Set state for day selection
            await state.set_data({'group_id': group_id, 'selected_days': []})
            
        except Exception as e:
            logger.error(f"Error starting custom schedule: {e}")
            await query.answer("❌ Error starting custom schedule creation")
    
    async def toggle_schedule_day(self, query: types.CallbackQuery, group_id: int, day: int, state: FSMContext):
        """Toggle a day selection for custom schedule"""
        try:
            data = await state.get_data()
            
            selected_days = data.get('selected_days', [])
            
            if day in selected_days:
                selected_days.remove(day)
            else:
                selected_days.append(day)
            
            await state.set_data({'group_id': group_id, 'selected_days': selected_days})
            
            # Update the display
            await self.show_custom_schedule_day_selection(query, group_id, selected_days)
            
        except Exception as e:
            logger.error(f"Error toggling schedule day: {e}")
            await query.answer("❌ Error updating day selection")
    
    async def set_schedule_preset_days(self, query: types.CallbackQuery, group_id: int, preset: str, state: FSMContext):
        """Set preset days for custom schedule"""
        try:
            preset_days = {
                'weekdays': [1, 2, 3, 4, 5],
                'weekends': [6, 7], 
                'daily': [1, 2, 3, 4, 5, 6, 7]
            }
            
            if preset not in preset_days:
                await query.answer("❌ Invalid preset")
                return
                
            selected_days = preset_days[preset]
            await state.set_data({'group_id': group_id, 'selected_days': selected_days})
            
            # Update display
            await self.show_custom_schedule_day_selection(query, group_id, selected_days)
            
        except Exception as e:
            logger.error(f"Error setting preset days: {e}")
            await query.answer("❌ Error setting preset days")
    
    async def show_custom_schedule_day_selection(self, query: types.CallbackQuery, group_id: int, selected_days: list):
        """Show the day selection interface with current selections"""
        try:
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(selected_days)]
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Selected Days:</b> {', '.join(selected_names) if selected_days else 'None'}\n\n"
            text += "Select or deselect days:"
            
            keyboard_rows = []
            
            # Individual day buttons
            for i, day_name in enumerate(['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'], 1):
                icon = "✅" if i in selected_days else "📅"
                keyboard_rows.append([
                    InlineKeyboardButton(text=f"{icon} {day_name}", callback_data=f"schedule:day:{i}:{group_id}")
                ])
            
            # Preset buttons
            keyboard_rows.append([
                InlineKeyboardButton(text="☑️ Weekdays (M-F)", callback_data=f"schedule:preset:weekdays:{group_id}"),
                InlineKeyboardButton(text="☑️ Weekends (S-S)", callback_data=f"schedule:preset:weekends:{group_id}")
            ])
            keyboard_rows.append([
                InlineKeyboardButton(text="☑️ All Days", callback_data=f"schedule:preset:daily:{group_id}")
            ])
            
            # Continue or back buttons
            if selected_days:
                keyboard_rows.append([
                    InlineKeyboardButton(text="➡️ Next: Set Times", callback_data=f"schedule:set_times:{group_id}")
                ])
            
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data=f"schedule:add:{group_id}")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing day selection: {e}")
            await query.answer("❌ Error updating display")
    
    async def show_custom_schedule_times(self, query: types.CallbackQuery, group_id: int, state: FSMContext):
        """Show the time input interface for custom schedule"""
        try:
            data = await state.get_data()
            
            selected_days = data.get('selected_days', [])
            if not selected_days:
                await query.answer("❌ No days selected")
                return
            
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(selected_days)]
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Days:</b> {', '.join(selected_names)}\n\n"
            text += "<b>Select start time (24-hour format):</b>"
            
            # Create comprehensive 24-hour time picker
            keyboard_rows = []
            
            # All 24 hours in rows of 4
            for hour_start in range(0, 24, 4):
                row = []
                for hour in range(hour_start, min(hour_start + 4, 24)):
                    time_str = f"{hour:02d}:00"
                    # Add appropriate emoji based on time of day
                    if 0 <= hour < 6:
                        emoji = "🌃"  # Night
                    elif 6 <= hour < 12:
                        emoji = "🌅"  # Morning
                    elif 12 <= hour < 18:
                        emoji = "☀️"  # Day
                    else:
                        emoji = "🌆"  # Evening
                    
                    row.append(InlineKeyboardButton(
                        text=f"{emoji} {time_str}",
                        callback_data=f"schedule:time:start:{time_str}:{group_id}"
                    ))
                keyboard_rows.append(row)
            
            # Add custom time and back buttons
            keyboard_rows.append([
                InlineKeyboardButton(text="⚙️ Custom Time", callback_data=f"schedule:time:custom:start:{group_id}"),
                InlineKeyboardButton(text="🔙 Back", callback_data=f"schedule:set_times:{group_id}")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            # Preserve existing state data and add new data
            current_data = await state.get_data() or {}
            current_data.update({
                'group_id': group_id, 
                'selected_days': selected_days,
                'message_id': query.message.message_id
            })
            await state.set_data(current_data)
            
        except Exception as e:
            logger.error(f"Error showing time input: {e}")
            await query.answer("❌ Error showing time input")
    
    async def finish_custom_schedule(self, query: types.CallbackQuery, group_id: int, max_calls_setting: str, state: FSMContext):
        """Finish custom schedule creation with unlimited calls"""
        try:
            data = await state.get_data()
            
            if not data.get('selected_days') or not data.get('start_time') or not data.get('end_time'):
                await query.answer("❌ Missing schedule data")
                return
            
            max_calls = None if max_calls_setting == 'unlimited' else None
            
            # Create the schedule
            await self._create_custom_schedule(
                group_id, 
                data['selected_days'], 
                data['start_time'], 
                data['end_time'], 
                max_calls
            )
            
            group_name = await self._get_group_name(group_id)
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"✅ <b>Custom Schedule Created!</b>\n\n"
            text += f"Group: {group_name}\n"
            text += f"Days: {', '.join(selected_names)}\n"
            text += f"Time: {data['start_time'].strftime('%H:%M')} - {data['end_time'].strftime('%H:%M')}\n"
            text += f"Max calls: Unlimited\n\n"
            text += "The schedule is now active!"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📅 View Schedules", callback_data=f"group:schedules:{group_id}"),
                    InlineKeyboardButton(text="➕ Add Another", callback_data=f"schedule:add:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{group_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Custom schedule created!")
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error finishing custom schedule: {e}")
            await query.answer("❌ Error creating schedule")
    
    async def handle_time_selection(self, query: types.CallbackQuery, group_id: int, time_type: str, time_value: str, state: FSMContext):
        """Handle time selection from button picker"""
        try:
            logger.debug(f"handle_time_selection called with group_id: {group_id}, time_type: {time_type}, time_value: {time_value}")
            from datetime import time
            selected_time = time.fromisoformat(time_value)
            
            data = await state.get_data()
            logger.debug(f"Time selection - State data: {data}")
            
            # Check if we have the required state data
            if not data or not data.get('selected_days'):
                logger.error(f"Missing state data in time selection: {data}")
                await query.answer("❌ Session expired. Please start over.")
                # Reinitialize the custom schedule flow
                await self.start_custom_schedule(query, group_id, state)
                return
            
            if time_type == 'start':
                data['start_time'] = selected_time
                logger.debug(f"Setting start time: {selected_time}, full data: {data}")
                await state.set_data(data)
                
                # Verify the data was saved
                verification_data = await state.get_data()
                logger.debug(f"Verification after saving start time: {verification_data}")
                
                await self.show_end_time_picker(query, group_id, state)
            elif time_type == 'end':
                data['end_time'] = selected_time
                await state.set_data(data)
                await self.show_max_calls_picker(query, group_id, state)
            
        except Exception as e:
            logger.error(f"Error handling time selection: {e}")
            await query.answer("❌ Error processing time selection")
    
    async def show_end_time_picker(self, query: types.CallbackQuery, group_id: int, state: FSMContext):
        """Show end time picker buttons"""
        try:
            data = await state.get_data()
            logger.debug(f"End time picker - State data: {data}")
            
            # Validate required state data
            if not data or not data.get('selected_days') or not data.get('start_time'):
                logger.error(f"Missing required state data for end time picker: {data}")
                await query.answer("❌ Session expired. Please start over.")
                await self.start_custom_schedule(query, group_id, state)
                return
            
            try:
                group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
                if not group:
                    logger.error(f"Group {group_id} not found")
                    await query.answer("❌ Group not found")
                    return
                group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            except Exception as e:
                logger.error(f"Error fetching group: {e}")
                await query.answer("❌ Error loading group")
                return
            
            try:
                day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
                selected_days_list = data['selected_days']
                if not selected_days_list:
                    logger.error("Selected days list is empty")
                    selected_names = []
                else:
                    selected_names = [day_names[d-1] for d in sorted(selected_days_list)]
            except Exception as e:
                logger.error(f"Error processing selected days: {e}")
                selected_names = []
            
            try:
                start_time = data['start_time']
                if not start_time:
                    logger.error("Start time is None")
                    await query.answer("❌ Start time not set")
                    return
                start_hour = start_time.hour
            except Exception as e:
                logger.error(f"Error accessing start time: {e}")
                await query.answer("❌ Error with start time")
                return
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Days:</b> {', '.join(selected_names)}\n"
            text += f"<b>Start:</b> {start_time.strftime('%H:%M')}\n\n"
            text += "<b>Select end time (24-hour format):</b>\n"
            text += f"<i>Choose any time after {start_time.strftime('%H:%M')} or next day</i>"
            
            # Create comprehensive 24-hour time picker for end time
            try:
                keyboard_rows = []
                
                # All 24 hours in rows of 4
                for hour_start in range(0, 24, 4):
                    row = []
                    for hour in range(hour_start, min(hour_start + 4, 24)):
                        time_str = f"{hour:02d}:00"
                        
                        # Add appropriate emoji and indicator
                        if 0 <= hour < 6:
                            emoji = "🌃"  # Night
                        elif 6 <= hour < 12:
                            emoji = "🌅"  # Morning
                        elif 12 <= hour < 18:
                            emoji = "☀️"  # Day
                        else:
                            emoji = "🌆"  # Evening
                        
                        # Add visual indicator for recommended times
                        if hour > start_hour:
                            # Same day, after start time
                            button_text = f"{emoji} {time_str}"
                        elif hour <= start_hour:
                            # Next day option
                            button_text = f"{emoji} {time_str}+1"
                        else:
                            button_text = f"{emoji} {time_str}"
                        
                        row.append(InlineKeyboardButton(
                            text=button_text,
                            callback_data=f"schedule:time:end:{time_str}:{group_id}"
                        ))
                    keyboard_rows.append(row)
                
                # Add special end times
                keyboard_rows.append([
                    InlineKeyboardButton(text="🌃 23:59 (End of Day)", callback_data=f"schedule:time:end:23:59:{group_id}"),
                    InlineKeyboardButton(text="⚙️ Custom Time", callback_data=f"schedule:time:custom:end:{group_id}")
                ])
                keyboard_rows.append([
                    InlineKeyboardButton(text="🔙 Back", callback_data=f"schedule:set_times:{group_id}")
                ])
                
                keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
                await query.message.edit_text(text, reply_markup=keyboard)
                
            except Exception as e:
                logger.error(f"Error creating end time picker keyboard: {e}")
                await query.answer("❌ Error creating time picker")
                return
            
        except Exception as e:
            logger.error(f"Error showing end time picker: {e}")
            await query.answer("❌ Error showing end time picker")
    
    async def show_max_calls_picker(self, query: types.CallbackQuery, group_id: int, state: FSMContext):
        """Show max calls picker buttons"""
        try:
            data = await state.get_data()
            
            # Validate required state data
            if not data or not data.get('selected_days') or not data.get('start_time') or not data.get('end_time'):
                logger.error(f"Missing required state data for max calls picker: {data}")
                await query.answer("❌ Session expired. Please start over.")
                await self.start_custom_schedule(query, group_id, state)
                return
            
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Days:</b> {', '.join(selected_names)}\n"
            text += f"<b>Time:</b> {data['start_time'].strftime('%H:%M')} - {data['end_time'].strftime('%H:%M')}\n\n"
            text += "<b>Select max calls per time window:</b>\n"
            text += "<i>This limits how many calls can be sent during the schedule window</i>"
            
            keyboard_rows = []
            
            # Low volume options
            keyboard_rows.append([
                InlineKeyboardButton(text="1 Call", callback_data=f"schedule:maxcalls:1:{group_id}"),
                InlineKeyboardButton(text="2 Calls", callback_data=f"schedule:maxcalls:2:{group_id}"),
                InlineKeyboardButton(text="3 Calls", callback_data=f"schedule:maxcalls:3:{group_id}"),
                InlineKeyboardButton(text="5 Calls", callback_data=f"schedule:maxcalls:5:{group_id}")
            ])
            
            # Medium volume options  
            keyboard_rows.append([
                InlineKeyboardButton(text="10 Calls", callback_data=f"schedule:maxcalls:10:{group_id}"),
                InlineKeyboardButton(text="15 Calls", callback_data=f"schedule:maxcalls:15:{group_id}"),
                InlineKeyboardButton(text="20 Calls", callback_data=f"schedule:maxcalls:20:{group_id}"),
                InlineKeyboardButton(text="25 Calls", callback_data=f"schedule:maxcalls:25:{group_id}")
            ])
            
            # High volume options
            keyboard_rows.append([
                InlineKeyboardButton(text="30 Calls", callback_data=f"schedule:maxcalls:30:{group_id}"),
                InlineKeyboardButton(text="50 Calls", callback_data=f"schedule:maxcalls:50:{group_id}"),
                InlineKeyboardButton(text="75 Calls", callback_data=f"schedule:maxcalls:75:{group_id}"),
                InlineKeyboardButton(text="100 Calls", callback_data=f"schedule:maxcalls:100:{group_id}")
            ])
            
            # Unlimited and custom
            keyboard_rows.append([
                InlineKeyboardButton(text="♾️ Unlimited", callback_data=f"schedule:maxcalls:unlimited:{group_id}"),
                InlineKeyboardButton(text="⚙️ Custom Number", callback_data=f"schedule:maxcalls:custom:{group_id}")
            ])
            
            # Back button
            keyboard_rows.append([
                InlineKeyboardButton(text="🔙 Back", callback_data=f"schedule:set_times:{group_id}")
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing max calls picker: {e}")
            await query.answer("❌ Error showing max calls picker")
    
    async def show_custom_time_input(self, query: types.CallbackQuery, group_id: int, time_for: str, state: FSMContext):
        """Show custom time input (fallback to text input)"""
        try:
            data = await state.get_data()
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Custom {time_for.title()} Time Entry</b>\n\n"
            text += "Please enter the time in HH:MM format (24-hour):\n"
            text += "Examples: 09:30, 14:15, 22:45\n\n"
            text += "Type /cancel to abort."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"schedule:set_times:{group_id}")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
            if time_for == 'start':
                await state.set_state(ManagementStates.custom_schedule_start_time)
            else:
                await state.set_state(ManagementStates.custom_schedule_end_time)
            
        except Exception as e:
            logger.error(f"Error showing custom time input: {e}")
            await query.answer("❌ Error showing time input")
    
    async def handle_max_calls_selection(self, query: types.CallbackQuery, group_id: int, max_calls: str, state: FSMContext):
        """Handle max calls selection from button picker"""
        try:
            data = await state.get_data()
            
            # Validate required state data
            if not data or not data.get('selected_days') or not data.get('start_time') or not data.get('end_time'):
                logger.error(f"Missing required state data for max calls selection: {data}")
                await query.answer("❌ Session expired. Please start over.")
                await self.start_custom_schedule(query, group_id, state)
                return
            
            if max_calls == 'unlimited':
                max_calls_value = None
            elif max_calls == 'custom':
                # Show custom number input
                await self.show_custom_max_calls_input(query, group_id, state)
                return
            else:
                max_calls_value = int(max_calls)
            
            # Create the schedule
            await self._create_custom_schedule(
                group_id, 
                data['selected_days'], 
                data['start_time'], 
                data['end_time'], 
                max_calls_value
            )
            
            # Show success message
            group_name = await self._get_group_name(group_id)
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"✅ <b>Custom Schedule Created!</b>\n\n"
            text += f"Group: {group_name}\n"
            text += f"Days: {', '.join(selected_names)}\n"
            text += f"Time: {data['start_time'].strftime('%H:%M')} - {data['end_time'].strftime('%H:%M')}\n"
            text += f"Max calls: {'Unlimited' if max_calls_value is None else max_calls_value}\n\n"
            text += "The schedule is now active!"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📅 View Schedules", callback_data=f"group:schedules:{group_id}"),
                    InlineKeyboardButton(text="➕ Add Another", callback_data=f"schedule:add:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{group_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Custom schedule created!")
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error handling max calls selection: {e}")
            await query.answer("❌ Error creating schedule")
    
    async def show_custom_max_calls_input(self, query: types.CallbackQuery, group_id: int, state: FSMContext):
        """Show custom max calls number input"""
        try:
            data = await state.get_data()
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Days:</b> {', '.join(selected_names)}\n"
            text += f"<b>Time:</b> {data['start_time'].strftime('%H:%M')} - {data['end_time'].strftime('%H:%M')}\n\n"
            text += "<b>Custom Max Calls Entry</b>\n\n"
            text += "Enter the maximum number of calls per time window:\n"
            text += "Examples: 1, 5, 10, 25, 100\n\n"
            text += "Type /cancel to abort."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"schedule:set_times:{group_id}")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.custom_schedule_max_calls)
            
        except Exception as e:
            logger.error(f"Error showing custom max calls input: {e}")
            await query.answer("❌ Error showing input")
    
    async def process_start_time_input(self, message: types.Message, state: FSMContext):
        """Process start time input for custom schedule"""
        try:
            if message.text == '/cancel':
                await message.reply("❌ Custom schedule creation cancelled.")
                await state.clear()
                return
            
            # Validate time format
            try:
                from datetime import time
                start_time = time.fromisoformat(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid time format. Please use HH:MM format (e.g., 09:00, 14:30)")
                return
            
            # Update state with start time
            data = await state.get_data()
            data['start_time'] = start_time
            await state.set_data(data)
            
            # Ask for end time
            group_name = await self._get_group_name(data['group_id'])
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Days:</b> {', '.join(selected_names)}\n"
            text += f"<b>Start:</b> {start_time.strftime('%H:%M')}\n\n"
            text += "<b>Now enter the end time:</b>\n"
            text += "Format: HH:MM (24-hour format)\n"
            text += "Examples: 12:00, 17:30, 23:59\n\n"
            text += "Type /cancel to abort."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"schedule:add:{data['group_id']}")]
            ])
            
            await message.reply(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.custom_schedule_end_time)
            
        except Exception as e:
            logger.error(f"Error processing start time input: {e}")
            await message.reply("❌ Error processing start time")
            await state.clear()
    
    async def process_end_time_input(self, message: types.Message, state: FSMContext):
        """Process end time input for custom schedule"""
        try:
            if message.text == '/cancel':
                await message.reply("❌ Custom schedule creation cancelled.")
                await state.clear()
                return
            
            # Validate time format
            try:
                from datetime import time
                end_time = time.fromisoformat(message.text.strip())
            except ValueError:
                await message.reply("❌ Invalid time format. Please use HH:MM format (e.g., 12:00, 17:30)")
                return
            
            # Update state with end time
            data = await state.get_data()
            data['end_time'] = end_time
            await state.set_data(data)
            
            # Ask for max calls (optional)
            group_name = await self._get_group_name(data['group_id'])
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"<b>⚙️ Custom Schedule for {group_name}</b>\n\n"
            text += f"<b>Days:</b> {', '.join(selected_names)}\n"
            text += f"<b>Time:</b> {data['start_time'].strftime('%H:%M')} - {end_time.strftime('%H:%M')}\n\n"
            text += "<b>Max calls per window (optional):</b>\n"
            text += "Enter a number to limit calls during this time window.\n"
            text += "Or type 'unlimited' for no limit.\n\n"
            text += "Examples: 5, 10, unlimited\n"
            text += "Type /cancel to abort."
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="♾️ Unlimited", callback_data=f"schedule:finish_custom:{data['group_id']}:unlimited"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"schedule:add:{data['group_id']}")
                ]
            ])
            
            await message.reply(text, reply_markup=keyboard)
            await state.set_state(ManagementStates.custom_schedule_max_calls)
            
        except Exception as e:
            logger.error(f"Error processing end time input: {e}")
            await message.reply("❌ Error processing end time")
            await state.clear()
    
    async def process_max_calls_input(self, message: types.Message, state: FSMContext):
        """Process max calls input for custom schedule"""
        try:
            if message.text == '/cancel':
                await message.reply("❌ Custom schedule creation cancelled.")
                await state.clear()
                return
            
            max_calls = None
            text_input = message.text.strip().lower()
            
            if text_input in ['unlimited', 'none', '0']:
                max_calls = None
            else:
                try:
                    max_calls = int(text_input)
                    if max_calls < 1:
                        await message.reply("❌ Max calls must be a positive number or 'unlimited'")
                        return
                except ValueError:
                    await message.reply("❌ Please enter a number or 'unlimited'")
                    return
            
            # Create the schedule
            data = await state.get_data()
            await self._create_custom_schedule(
                data['group_id'], 
                data['selected_days'], 
                data['start_time'], 
                data['end_time'], 
                max_calls
            )
            
            group_name = await self._get_group_name(data['group_id'])
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            selected_names = [day_names[d-1] for d in sorted(data['selected_days'])]
            
            text = f"✅ <b>Custom Schedule Created!</b>\n\n"
            text += f"Group: {group_name}\n"
            text += f"Days: {', '.join(selected_names)}\n"
            text += f"Time: {data['start_time'].strftime('%H:%M')} - {data['end_time'].strftime('%H:%M')}\n"
            text += f"Max calls: {'Unlimited' if max_calls is None else max_calls}\n\n"
            text += "The schedule is now active!"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📅 View Schedules", callback_data=f"group:schedules:{data['group_id']}"),
                    InlineKeyboardButton(text="➕ Add Another", callback_data=f"schedule:add:{data['group_id']}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{data['group_id']}")
                ]
            ])
            
            await message.reply(text, reply_markup=keyboard)
            await state.clear()
            
        except Exception as e:
            logger.error(f"Error processing max calls input: {e}")
            await message.reply("❌ Error creating schedule")
            await state.clear()
    
    async def _get_group_name(self, group_id: int) -> str:
        """Helper to get group name"""
        group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
        return group['title'] or f"Chat {group['tg_chat_id']}" if group else "Unknown"
    
    async def _create_custom_schedule(self, group_id: int, days: list, start_time, end_time, max_calls):
        """Helper to create custom schedule in database"""
        await db.execute (
            """INSERT INTO group_schedules (group_id, start_time, end_time, weekdays, max_calls_in_window)
            VALUES ($1, $2, $3, $4, $5)
            """,
            group_id, start_time, end_time, days, max_calls
        )
    
    async def create_schedule_from_template(self, query: types.CallbackQuery, group_id: int, template: str):
        """Create a schedule from a predefined template"""
        try:
            # Define schedule templates
            templates = {
                'morning': {'start': '09:00', 'end': '12:00', 'weekdays': [1,2,3,4,5]},
                'afternoon': {'start': '12:00', 'end': '17:00', 'weekdays': [1,2,3,4,5]},
                'evening': {'start': '17:00', 'end': '22:00', 'weekdays': [1,2,3,4,5,6,7]},
                'night': {'start': '22:00', 'end': '06:00', 'weekdays': [1,2,3,4,5,6,7]},
                'business': {'start': '09:00', 'end': '17:00', 'weekdays': [1,2,3,4,5]},
                '24h': {'start': '00:00', 'end': '23:59', 'weekdays': [1,2,3,4,5,6,7]}
            }
            
            if template not in templates:
                await query.answer("❌ Invalid template")
                return
            
            template_data = templates[template]
            
            # Convert string times to time objects
            from datetime import time
            start_time = time.fromisoformat(template_data['start'])
            end_time = time.fromisoformat(template_data['end'])
            
            # Create the schedule in database
            await db.execute (
                """INSERT INTO group_schedules (group_id, start_time, end_time, weekdays, max_calls_in_window)
                VALUES ($1, $2, $3, $4, $5)
                """,
                group_id, start_time, end_time, 
                template_data['weekdays'], None
            )
            
            # Get group info for confirmation
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            # Format weekdays for display
            days = self._format_template_weekdays(template_data['weekdays'])
            
            text = f"✅ <b>Schedule Created</b>\n\n"
            text += f"Group: {group_name}\n"
            text += f"Time: {template_data['start']} - {template_data['end']}\n"
            text += f"Days: {days}\n"
            text += f"Max calls: Unlimited\n\n"
            text += "The schedule is now active!"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📅 View Schedules", callback_data=f"group:schedules:{group_id}"),
                    InlineKeyboardButton(text="➕ Add Another", callback_data=f"schedule:add:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="🔙 Back to Group", callback_data=f"group:view:{group_id}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            await query.answer("✅ Schedule created successfully!")
            
        except Exception as e:
            logger.error(f"Error creating schedule from template: {e}")
            await query.answer("❌ Error creating schedule")
    
    async def confirm_delete_schedule(self, query: types.CallbackQuery, schedule_id: int):
        """Confirm schedule deletion"""
        try:
            # Get schedule info
            schedule = await db.fetchrow (
                """SELECT s.*, g.title as group_title, g.tg_chat_id, g.id as group_id
                FROM group_schedules s
                JOIN groups g ON g.id = s.group_id
                WHERE s.id = $1
                """,
                schedule_id
            )
            
            if not schedule:
                await query.answer("❌ Schedule not found")
                return
            
            group_name = schedule['group_title'] or f"Chat {schedule['tg_chat_id']}"
            days = self._format_template_weekdays(schedule['weekdays'])
            
            text = f"<b>🗑️ Delete Schedule</b>\n\n"
            text += f"Group: {group_name}\n"
            text += f"Time: {schedule['start_time']} - {schedule['end_time']}\n"
            text += f"Days: {days}\n\n"
            text += "⚠️ Are you sure you want to delete this schedule?"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Yes, Delete", callback_data=f"schedule:confirm_delete:{schedule_id}"),
                    InlineKeyboardButton(text="❌ Cancel", callback_data=f"group:schedules:{schedule['group_id']}")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error showing delete confirmation: {e}")
            await query.answer("❌ Error loading schedule")
    
    async def delete_schedule(self, query: types.CallbackQuery, schedule_id: int):
        """Actually delete the schedule"""
        try:
            # Get schedule and group info before deletion
            schedule = await db.fetchrow (
                """SELECT s.*, g.id as group_id 
                FROM group_schedules s
                JOIN groups g ON g.id = s.group_id
                WHERE s.id = $1
                """,
                schedule_id
            )
            
            if not schedule:
                await query.answer("❌ Schedule not found")
                return
            
            group_id = schedule['group_id']
            
            # Delete the schedule
            await db.execute("DELETE FROM group_schedules WHERE id = $1", schedule_id)
            
            await query.answer("✅ Schedule deleted successfully!")
            
            # Go back to group schedules view
            from app.ui.handlers.groups import GroupsHandler
            groups_handler = GroupsHandler(db, self.keyboards)
            await groups_handler.show_group_schedules(query, group_id)
            
        except Exception as e:
            logger.error(f"Error deleting schedule: {e}")
            await query.answer("❌ Error deleting schedule")
    
    def _format_template_weekdays(self, weekdays):
        """Format weekdays list to readable string"""
        if not weekdays:
            return "No days"
        
        day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        
        if len(weekdays) == 7:
            return "Daily"
        elif set(weekdays) == {1, 2, 3, 4, 5}:
            return "Weekdays" 
        elif set(weekdays) == {6, 7}:
            return "Weekends"
        else:
            return ", ".join([day_names[d-1] for d in sorted(weekdays)])
    
    async def show_quotas_menu(self, query: types.CallbackQuery):
        """Show quotas overview"""
        try:
            groups = await db.fetch (
                """SELECT g.*, 
                       (SELECT COUNT(*) FROM calls WHERE group_id = g.id AND sent_at > CURRENT_DATE) as calls_today
                FROM groups g
                WHERE g.enabled = true
                ORDER BY g.title
                """
            )
            
            text = "<b>📦 Daily Quotas</b>\n\n"
            
            if not groups:
                text += "No active groups with quotas."
            else:
                for group in groups:
                    title = group['title'] or f"Chat {group['tg_chat_id']}"
                    quota = group['daily_cap'] or "∞"
                    used = group['calls_today']
                    
                    if group['daily_cap'] and group['daily_cap'] > 0:
                        percentage = (used / group['daily_cap']) * 100
                        bar = "█" * int(percentage / 10) + "░" * (10 - int(percentage / 10))
                        text += f"<b>{title}</b>\n{bar} {used}/{quota} ({percentage:.0f}%)\n\n"
                    else:
                        text += f"<b>{title}</b>\nUnlimited - {used} sent today\n\n"
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:main")
            )
        except Exception as e:
            logger.error(f"Error showing quotas: {e}")
            await query.answer("❌ Error loading quotas")
    
    
    async def process_userbot_phone(self, message: types.Message, state: FSMContext):
        """Process userbot phone input"""
        await self.userbots_handler.process_phone_input(message, state)
    
    async def handle_userbot_assignment(self, query: types.CallbackQuery):
        """Handle userbot assignment to group"""
        try:
            # Parse callback data: assign:userbot:group_id:userbot_id
            parts = query.data.split(':')
            group_id = int(parts[2])
            userbot_id = int(parts[3])
            
            # Get bot model
            from app.models import BotModel
            bot_model = BotModel(db)
            
            # Assign userbot to group
            await bot_model.assign_to_group(userbot_id, group_id)
            
            # Enable the group when userbot is assigned
            await db.execute("UPDATE groups SET enabled = true WHERE id = $1", group_id)
            
            # Get group and userbot info for confirmation
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            userbot = await db.fetchrow("SELECT * FROM bots WHERE id = $1", userbot_id)
            
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            bot_name = userbot['session_name'] or f"Bot {userbot_id}"
            
            await query.answer(f"✅ {bot_name} assigned to {group_name}")
            
            # Go back to group details
            await self.groups_handler.show_group_details(query, group_id)
            
        except Exception as e:
            logger.error(f"Error handling userbot assignment: {e}")
            await query.answer("❌ Error assigning userbot")
    
    
    
    async def handle_source_group_selection(self, query: types.CallbackQuery, state: FSMContext):
        """Handle source group selection - show source type selection"""
        try:
            group_id = int(query.data.split(':', 1)[1])
            
            # Set group ID in state
            await state.set_data({'group_id': group_id})
            
            # Get group info
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = f"<b>➕ Add Source for {group_name}</b>\n\n"
            text += "What type of source are you adding?\n\n"
            text += "📢 <b>Channel</b> - Monitors all posts from a channel\n"
            text += "👥 <b>Group</b> - Monitors group with user filtering\n" 
            text += "💬 <b>DM</b> - Monitors direct messages from a user"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="📢 Channel", callback_data=f"source_type:channel:{group_id}"),
                    InlineKeyboardButton(text="👥 Group", callback_data=f"source_type:group:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="💬 DM", callback_data=f"source_type:dm:{group_id}")
                ],
                [
                    InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")
                ]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error handling source group selection: {e}")
            await query.answer("❌ Error processing selection")
    
    async def handle_source_type_selection(self, query: types.CallbackQuery, state: FSMContext):
        """Handle source type selection for adding source"""
        try:
            parts = query.data.split(':')
            source_type = parts[1]
            group_id = int(parts[2])
            
            # Get existing state data and add source type
            data = await state.get_data()
            data['source_type'] = source_type
            await state.set_data(data)
            await state.set_state(ManagementStates.adding_source_chat_id)
            
            # Get group info
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            # Source type specific instructions
            type_instructions = {
                'channel': {
                    'emoji': '📢',
                    'name': 'Channel',
                    'id_format': 'Channel ID (negative): -1001234567890',
                    'example': '-1001234567890',
                    'validation': 'Must be negative and typically start with -100'
                },
                'group': {
                    'emoji': '👥', 
                    'name': 'Group',
                    'id_format': 'Group ID (negative): -1001234567890 or -123456789',
                    'example': '-1001234567890',
                    'validation': 'Must be negative'
                },
                'dm': {
                    'emoji': '💬',
                    'name': 'DM',
                    'id_format': 'User ID (positive): 123456789',
                    'example': '123456789',
                    'validation': 'Must be positive'
                }
            }
            
            info = type_instructions[source_type]
            
            text = f"<b>➕ Add {info['emoji']} {info['name']} Source</b>\n\n"
            text += f"Target Group: <b>{group_name}</b>\n"
            text += f"Source Type: {info['emoji']} {info['name']}\n\n"
            text += f"Please enter the {info['id_format']}\n\n"
            text += f"<b>Example:</b> <code>{info['example']}</code>\n\n"
            text += f"💡 <i>{info['validation']}</i>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error handling source type selection: {e}")
            await query.answer("❌ Error selecting source type")
    
    async def handle_global_source_type_selection(self, query: types.CallbackQuery, state: FSMContext):
        """Handle global source type selection"""
        try:
            source_type = query.data.split(':', 1)[1]
            
            # Set source type in state
            await state.set_data({'source_type': source_type})
            await state.set_state(ManagementStates.adding_source_chat_id)
            
            # Source type specific instructions
            type_instructions = {
                'channel': {
                    'emoji': '📢',
                    'name': 'Channel',
                    'id_format': 'Channel ID (negative): -1001234567890',
                    'example': '-1001234567890',
                    'validation': 'Must be negative and typically start with -100'
                },
                'group': {
                    'emoji': '👥', 
                    'name': 'Group',
                    'id_format': 'Group ID (negative): -1001234567890 or -123456789',
                    'example': '-1001234567890',
                    'validation': 'Must be negative'
                },
                'dm': {
                    'emoji': '💬',
                    'name': 'DM',
                    'id_format': 'User ID (positive): 123456789',
                    'example': '123456789',
                    'validation': 'Must be positive'
                }
            }
            
            info = type_instructions[source_type]
            
            text = f"<b>➕ Add {info['emoji']} {info['name']} Source</b>\n\n"
            text += f"Please enter the {info['id_format']}\n\n"
            text += f"<b>Example:</b> <code>{info['example']}</code>\n\n"
            text += f"💡 <i>{info['validation']}</i>\n\n"
            text += "<i>After adding, you can configure routing to target groups.</i>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error handling global source type selection: {e}")
            await query.answer("❌ Error selecting source type")
    
    async def handle_source_edit(self, query: types.CallbackQuery):
        """Handle source edit menu"""
        try:
            source_id = int(query.data.split(':', 1)[1])
            
            # Get source info
            source = await db.fetchrow("SELECT * FROM source_chats WHERE id = $1", source_id)
            if not source:
                await query.answer("❌ Source not found")
                return
            
            title = source['title'] or f"ID: {source['source_chat_id']}"
            status = "✅ Enabled" if source['enabled'] else "❌ Disabled"
            type_name = "📢 Channel" if source['source_type'] == 'channel' else "👥 Group"
            
            text = f"<b>⚙️ Edit Source</b>\n\n"
            text += f"{type_name} {title}\n"
            text += f"Status: {status}\n"
            text += f"Chat ID: <code>{source['source_chat_id']}</code>\n"
            
            keyboard_rows = [
                [
                    InlineKeyboardButton(
                        text="🔄 Toggle Enable/Disable",
                        callback_data=f"sources:toggle:{source_id}"
                    )
                ]
            ]
            
            if source['source_type'] == 'group':
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text="👥 Manage Users",
                        callback_data=f"sources:users:{source_id}"
                    )
                ])
            
            keyboard_rows.extend([
                [
                    InlineKeyboardButton(
                        text="🗑️ Remove Source",
                        callback_data=f"sources:remove:{source_id}"
                    )
                ],
                [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error handling source edit: {e}")
            await query.answer("❌ Error loading source")
    
    async def handle_errors(self, event, **data):
        """Handle bot errors"""
        exception = data.get('exception')
        if exception:
            logger.error(f"Bot error: {exception}")
        
        # Get update from event
        update = event.update if hasattr(event, 'update') else event
        
        if hasattr(update, 'callback_query') and update.callback_query:
            try:
                await update.callback_query.answer("❌ An error occurred. Please try again.")
            except:
                pass
        elif hasattr(update, 'message') and update.message:
            try:
                await update.message.reply("❌ An error occurred. Please try again.")
            except:
                pass
    
    async def run(self, shutdown_event: asyncio.Event = None):
        """Start the management bot"""
        logger.info("Starting management bot...")
        
        # Initialize database
        await db.connect()
        
        # Start polling
        try:
            if shutdown_event:
                polling_task = asyncio.create_task(self.dp.start_polling(self.bot))
                shutdown_task = asyncio.create_task(shutdown_event.wait())
                
                # Wait for either polling to finish or shutdown signal
                done, pending = await asyncio.wait(
                    [polling_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel remaining tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            else:
                await self.dp.start_polling(self.bot)
        finally:
            await db.disconnect()
            await self.bot.session.close()

if __name__ == "__main__":
    bot = ManagementBot()
    asyncio.run(bot.run())
