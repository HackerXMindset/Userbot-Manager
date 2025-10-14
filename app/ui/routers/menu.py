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
        elif action == "close":
            await query.message.delete()

        await query.answer()

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
