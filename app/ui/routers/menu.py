"""
Main menu routing module.
"""

import logging

from aiogram import Dispatcher, F, types
from aiogram.filters import Command

from .context import ManagementRouterContext

logger = logging.getLogger(__name__)


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register main menu handlers."""

    settings = context.settings
    manager = context.manager
    keyboards = context.keyboards
    db = context.db

    async def cmd_menu(message: types.Message) -> None:
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        status_text = await manager.menu_handler.get_status_text()
        await message.answer(
            "<b>🎛 Management Console</b>\n\n{}".format(status_text),
            reply_markup=keyboards.main_menu(),
        )

    async def show_quotas_menu(query: types.CallbackQuery) -> None:
        try:
            quotas = await db.fetch(
                """
                SELECT
                    g.id,
                    g.title,
                    g.tg_chat_id,
                    g.enabled,
                    q.daily_quota,
                    COALESCE(
                        (
                            SELECT COUNT(*)
                            FROM token_call_history calls
                            WHERE calls.target_group_id = g.id
                              AND DATE(calls.called_at AT TIME ZONE 'UTC') = CURRENT_DATE
                        ),
                        0
                    ) AS sent_today
                FROM groups g
                LEFT JOIN group_quotas q ON q.group_id = g.id
                ORDER BY g.enabled DESC, g.title
                """
            )

            text = "<b>📈 Group Daily Quotas</b>\n\n"
            if not quotas:
                text += "No quotas configured yet."
            else:
                for quota in quotas:
                    title = quota["title"] or f"Chat {quota['tg_chat_id']}"
                    daily_quota = quota["daily_quota"]
                    used = quota["sent_today"]
                    enabled = quota["enabled"]

                    status = "🟢 Active" if enabled else "🔴 Disabled"
                    text += f"{status} <b>{title}</b>\n"
                    if daily_quota:
                        remaining = max(daily_quota - used, 0)
                        text += f"{used}/{daily_quota} sent today ({remaining} remaining)\n\n"
                    else:
                        text += f"{used} sent today (No quota)\n\n"

            await query.message.edit_text(
                text,
                reply_markup=keyboards.back_button("menu:main"),
            )
        except Exception as error:  # pragma: no cover - logging only
            logger.error("Error showing quotas menu: %s", error)
            await query.answer("❌ Error loading quotas", show_alert=True)

    async def handle_main_menu(query: types.CallbackQuery) -> None:
        action = query.data.split(":")[1]

        if action == "main":
            await manager.menu_handler.show_main_menu(query)
        elif action == "status":
            await manager.menu_handler.show_detailed_status(query)
        elif action == "groups":
            await manager.groups_handler.show_groups_menu(query)
        elif action == "schedules":
            await manager.schedules_handler.show_schedules_menu(query)
        elif action == "quotas":
            await show_quotas_menu(query)
        elif action == "userbots":
            await manager.userbots_handler.show_userbots_menu(query)
        elif action == "sources":
            await manager.sources_handler.show_sources_menu(query)
        elif action == "pnl":
            await manager.pnl_handler.show_rules_list(query)
        elif action == "notifications":
            await manager.notifications_handler.show_notifications_menu(query)
        elif action == "auto_click":
            await manager.auto_click_handler.show_auto_click_menu(query)
        elif action == "curate_alpha":
            await manager.curate_alpha_handler.show_curate_alpha_menu(query)
        elif action == "templates":
            await manager.templates_handler.show_templates_root(query)
        elif action == "settings":
            await manager.settings_handler.show_settings_menu(query)
        elif action == "commands":
            await show_commands_help(query)
        elif action == "close":
            await query.message.delete()

        await query.answer()

    async def show_commands_help(query: types.CallbackQuery) -> None:
        """Show all available admin commands"""
        try:
            await query.message.edit_text(
                "📚 <b>Available Admin Commands</b>\n\n"

                "🔍 <b>Token Inspector</b>\n"
                "<code>/i &lt;ca&gt;</code> - Inspect token details\n"
                "Shows 4 pages: Overview, Sources, Targets, Call Activity\n\n"

                "👥 <b>Group Inspector</b>\n"
                "<code>/ic &lt;group_id&gt;</code> - Full group configuration report\n\n"

                "🎯 <b>Trigger Gain Alert</b>\n"
                "<code>/tri &lt;ca&gt; [p] [c]</code> - Force gain alert\n"
                "<code>/tri &lt;group_id&gt; &lt;ca&gt; [p] [c]</code> - To specific group\n"
                "Flags: <code>p</code>=peak MC, <code>c</code>=include chart\n\n"

                "🔄 <b>Restart Monitoring</b>\n"
                "<code>/str &lt;ca&gt; [tier]</code> - Restart stopped token\n"
                "Tiers: tier_a (10s) to tier_f (30min)\n\n"

                "⛔ <b>Stop Monitoring</b>\n"
                "<code>/stop &lt;ca&gt;</code> - Stop tracking token\n\n"

                "🎛 <b>Management</b>\n"
                "<code>/menu</code> or <code>/start</code> - Show main menu\n"
                "<code>/all</code> - Show this command list\n\n"

                "🧹 <b>Danger Zone</b>\n"
                "<code>/clean_ca</code> - Wipe every tracked contract address (confirmation required)\n\n"

                "📖 <b>Examples:</b>\n"
                "• <code>/i HnKk7xPZmL...</code>\n"
                "• <code>/tri HnKk7... p c</code>\n"
                "• <code>/tri -1001234567890 HnKk7... c</code>\n"
                "• <code>/str HnKk7... tier_c</code>\n"
                "• <code>/stop HnKk7...</code>\n\n"

                "💡 <b>Tips:</b>\n"
                "• CA = Contract Address\n"
                "• Use <code>/command</code> without args to see detailed help\n"
                "• All commands support both Solana & BSC tokens",
                reply_markup=keyboards.back_button("menu:main"),
                parse_mode='HTML'
            )
        except Exception as error:  # pragma: no cover - logging only
            logger.error("Error showing commands help: %s", error)
            await query.answer("❌ Error loading commands", show_alert=True)

    dispatcher.message.register(
        cmd_menu,
        Command(commands=["menu", "start"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        handle_main_menu,
        F.data.startswith("menu:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )
