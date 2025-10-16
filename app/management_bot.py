import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.db import db
from app.ui.keyboards import Keyboards
from app.ui.handlers import (
    MenuHandler, GroupsHandler, UserbotsHandler,
    SchedulesHandler, SourcesHandler, PnlHandler,
    CommandForwardingHandler, NotificationsHandler, AutoClickHandler,
    DynamicReplyHandler, CurateAlphaHandler, TemplatesHandler, SettingsHandler,
    GainAlertsHandler,
)
from app.ui.routers import (
    ManagementRouterContext,
    register_management_routes,
)
from app.services.admin_cleanup import AdminCleanupService
from app.ui.controllers.schedule_mixin import ScheduleMixin

logger = logging.getLogger(__name__)

class ManagementBot(ScheduleMixin):
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
        self.pnl_handler = PnlHandler(db, self.keyboards)
        self.cmd_fwd_handler = CommandForwardingHandler(db, self.keyboards)
        self.notifications_handler = NotificationsHandler(db, self.keyboards)
        self.auto_click_handler = AutoClickHandler(db, self.keyboards)

        # Initialize dynamic reply models and handler
        from app.models.dynamic_reply import DynamicReplyModel
        dynamic_reply_model = DynamicReplyModel(db)
        self.dynamic_reply_handler = DynamicReplyHandler(dynamic_reply_model, self.keyboards)

        self.curate_alpha_handler = CurateAlphaHandler(db, self.keyboards)
        self.templates_handler = TemplatesHandler(db, self.keyboards)
        self.settings_handler = SettingsHandler(db, self.keyboards)
        self.gain_alerts_handler = GainAlertsHandler(db, self.keyboards)
        self.cleanup_service = AdminCleanupService(db, self.keyboards)

        self.setup_handlers()

    def set_system_manager(self, manager):
        """Set the SystemManager instance."""
        self.system_manager = manager
    
    def setup_handlers(self):
        """Register all handlers"""

        router_context = ManagementRouterContext(
            dispatcher=self.dp,
            keyboards=self.keyboards,
            db=db,
            settings=settings,
            manager=self,
            cleanup_service=self.cleanup_service,
            system_manager=self.system_manager,
            settings_handler=self.settings_handler,
        )

        register_management_routes(self.dp, router_context)

        # Error handler  
        self.dp.errors.register(self.handle_errors)
    
    async def handle_errors(self, event, **data):
        """Handle bot errors"""
        exception = data.get('exception')
        if exception:
            logger.error(f"Bot error occurred in event {event}", exc_info=True)
        
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
