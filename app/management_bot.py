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
    AlertsHandler, SchedulesHandler, TargetsHandler, SourcesHandler
)

logger = logging.getLogger(__name__)

class ManagementBot:
    def __init__(self):
        self.bot = Bot(token=settings.mgmt_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
        self.dp = Dispatcher(storage=MemoryStorage())
        self.keyboards = Keyboards()
        
        # Initialize handlers
        self.menu_handler = MenuHandler(db, self.keyboards)
        self.groups_handler = GroupsHandler(db, self.keyboards)
        self.userbots_handler = UserbotsHandler(db, self.keyboards)
        self.alerts_handler = AlertsHandler(db, self.keyboards)
        self.schedules_handler = SchedulesHandler(db, self.keyboards)
        self.targets_handler = TargetsHandler(db, self.keyboards)
        self.sources_handler = SourcesHandler(db, self.keyboards)
        
        self.setup_handlers()
    
    def setup_handlers(self):
        """Register all handlers"""
        
        # Commands
        self.dp.message.register(
            self.cmd_menu,
            Command(commands=['menu', 'start']),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Main menu callbacks
        self.dp.callback_query.register(
            self.handle_main_menu,
            F.data.startswith('menu:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Groups
        self.dp.callback_query.register(
            self.groups_handler.handle_group_action,
            F.data.startswith('group:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Schedules
        self.dp.callback_query.register(
            self.handle_schedules,
            F.data.startswith('sched:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Userbots
        self.dp.callback_query.register(
            self.userbots_handler.handle_userbot_action,
            F.data.startswith('userbot:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Alerts
        self.dp.callback_query.register(
            self.alerts_handler.handle_alerts_action,
            F.data.startswith('alerts:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Targets
        self.dp.callback_query.register(
            self.targets_handler.handle_target_action,
            F.data.startswith('targets:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Sources
        self.dp.callback_query.register(
            self.sources_handler.handle_sources_action,
            F.data.startswith('sources:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.callback_query.register(
            self.handle_source_group_selection,
            F.data.startswith('source_group:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.callback_query.register(
            self.handle_source_edit,
            F.data.startswith('source_edit:'),
            F.from_user.id == settings.admin_telegram_id
        )
        
        # State handlers
        self.dp.message.register(
            self.groups_handler.process_group_input,
            ManagementStates.adding_group,
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.message.register(
            self.process_userbot_phone,
            ManagementStates.userbot_login_phone,
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.message.register(
            self.userbots_handler.process_code_input,
            ManagementStates.userbot_login_code,
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.message.register(
            self.userbots_handler.process_2fa_input,
            ManagementStates.userbot_login_2fa,
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.message.register(
            self.sources_handler.process_source_input,
            ManagementStates.adding_source_chat_id,
            F.from_user.id == settings.admin_telegram_id
        )
        
        self.dp.message.register(
            self.sources_handler.process_user_input,
            ManagementStates.adding_source_user_id,
            F.from_user.id == settings.admin_telegram_id
        )
        
        # Error handler  
        self.dp.errors.register(self.handle_errors)
    
    async def cmd_menu(self, message: types.Message):
        """Handle /menu command"""
        if message.from_user.id != settings.admin_telegram_id:
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
        elif action == 'targets':
            await self.targets_handler.show_targets_menu(query)
        elif action == 'sources':
            await self.sources_handler.show_sources_menu(query)
        elif action == 'alerts':
            await self.alerts_handler.show_alerts_menu(query)
        elif action == 'notifications':
            await self.show_notifications_menu(query)
        elif action == 'tracking':
            await self.menu_handler.show_tracking_menu(query)
        elif action == 'settings':
            await self.menu_handler.show_settings_menu(query)
        elif action == 'close':
            await query.message.delete()
        
        await query.answer()
    
    async def handle_schedules(self, query: types.CallbackQuery):
        """Handle schedule-related callbacks"""
        # Implementation for schedule management
        await query.answer("Schedule management coming soon!")
    
    async def show_quotas_menu(self, query: types.CallbackQuery):
        """Show quotas overview"""
        try:
            groups = await db.fetch("""
                SELECT g.*, 
                       (SELECT COUNT(*) FROM calls WHERE group_id = g.id AND sent_at > CURRENT_DATE) as calls_today
                FROM groups g
                WHERE g.enabled = true
                ORDER BY g.title
            """)
            
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
    
    async def show_notifications_menu(self, query: types.CallbackQuery):
        """Show notifications configuration"""
        try:
            # Get recent events
            recent_events = await db.fetch("""
                SELECT kind, COUNT(*) as count 
                FROM events 
                WHERE created_at > NOW() - INTERVAL '24 hours'
                GROUP BY kind
                ORDER BY count DESC
            """)
            
            text = "<b>📢 Notifications</b>\n\n"
            text += "<b>Event Activity (24h):</b>\n"
            
            if recent_events:
                for event in recent_events:
                    text += f"• {event['kind']}: {event['count']}\n"
            else:
                text += "No recent events\n"
            
            text += "\n<b>Configuration:</b>\n"
            text += "• Forward replies to notification channel ✅\n"
            text += "• Forward mentions to notification channel ✅\n"
            text += "• Forward DMs to notification channel ✅\n"
            
            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("menu:main")
            )
        except Exception as e:
            logger.error(f"Error showing notifications: {e}")
            await query.answer("❌ Error loading notifications")
    
    async def process_userbot_phone(self, message: types.Message, state: FSMContext):
        """Process userbot phone input"""
        await self.userbots_handler.process_phone_input(message, state)
    
    async def handle_source_group_selection(self, query: types.CallbackQuery, state: FSMContext):
        """Handle source group selection for adding source"""
        try:
            group_id = int(query.data.split(':', 1)[1])
            
            # Set group ID in state
            await state.set_data({'group_id': group_id})
            await state.set_state(ManagementStates.adding_source_chat_id)
            
            # Get group info
            group = await db.fetchrow("SELECT * FROM groups WHERE id = $1", group_id)
            group_name = group['title'] or f"Chat {group['tg_chat_id']}"
            
            text = f"<b>➕ Add Source for {group_name}</b>\n\n"
            text += "Please paste the source chat ID (the chat to monitor for token addresses).\n\n"
            text += "Examples:\n"
            text += "• Channel: @channelname or -1001234567890\n"
            text += "• Group: -1001234567890\n"
            text += "• Public chat: @chatname\n\n"
            text += "💡 <i>The bot will auto-detect if it's a channel or group</i>"
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="❌ Cancel", callback_data="menu:sources")]
            ])
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error handling source group selection: {e}")
            await query.answer("❌ Error processing selection")
    
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
                [InlineKeyboardButton(
                    text="🔄 Toggle Enable/Disable",
                    callback_data=f"sources:toggle:{source_id}"
                )]
            ]
            
            if source['source_type'] == 'group':
                keyboard_rows.append([
                    InlineKeyboardButton(
                        text="👥 Manage Users",
                        callback_data=f"sources:users:{source_id}"
                    )
                ])
            
            keyboard_rows.extend([
                [InlineKeyboardButton(
                    text="🗑️ Remove Source",
                    callback_data=f"sources:remove:{source_id}"
                )],
                [InlineKeyboardButton(text="🔙 Back", callback_data="sources:manage")]
            ])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
            
            await query.message.edit_text(text, reply_markup=keyboard)
            
        except Exception as e:
            logger.error(f"Error handling source edit: {e}")
            await query.answer("❌ Error loading source")
    
    async def handle_errors(self, update: types.Update, exception: Exception):
        """Handle bot errors"""
        logger.error(f"Bot error: {exception}")
        
        if update.callback_query:
            try:
                await update.callback_query.answer("❌ An error occurred. Please try again.")
            except:
                pass
        elif update.message:
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