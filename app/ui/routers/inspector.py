"""Token inspector command (/i <contract>)."""

from __future__ import annotations

import html
import json
import logging
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from textwrap import shorten
from typing import Iterable, Sequence, Any

from aiogram import Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

from app.models.token import TokenModel

from .context import ManagementRouterContext

logger = logging.getLogger(__name__)

try:
    from asyncpg import exceptions as pg_exceptions  # type: ignore
except ImportError:  # pragma: no cover - fallback when asyncpg unavailable
    class pg_exceptions:  # type: ignore
        UndefinedColumnError = Exception
        UndefinedTableError = Exception


class InspectorPageCallback(CallbackData, prefix="insp"):
    """Callback data for inspector pagination"""
    address: str
    page: int


class GroupInspectorCallback(CallbackData, prefix="ginsp"):
    """Callback data for group inspector pagination"""
    group_id: int
    page: int


async def _fetchrow_safe(db, query: str, *args):
    try:
        return await db.fetchrow(query, *args)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Group inspector fetchrow failed: %s", exc, exc_info=True)
        return None


async def _fetch_safe(db, query: str, *args):
    try:
        return await db.fetch(query, *args)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Group inspector fetch failed: %s", exc, exc_info=True)
        return []


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register the /i inspector command for admins."""

    settings = context.settings
    db = context.db
    token_model = TokenModel(db)
    sol_pattern = re.compile(settings.solana_pattern)
    bnb_pattern = re.compile(settings.bnb_pattern, re.IGNORECASE)

    async def _find_group_record(identifier: int):
        if identifier > 0:
            record = await _fetchrow_safe(db, "SELECT * FROM groups WHERE id = $1", identifier)
            if record:
                return record
            return await _fetchrow_safe(db, "SELECT * FROM groups WHERE tg_chat_id = $1", identifier)
        return await _fetchrow_safe(db, "SELECT * FROM groups WHERE tg_chat_id = $1", identifier)

    async def _gather_group_payload(group_id: int) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        group_row = await _fetchrow_safe(db, "SELECT * FROM groups WHERE id = $1", group_id)
        if not group_row:
            return None, None

        group = dict(group_row)
        tg_chat_id = group.get("tg_chat_id")

        userbot_row = await _fetchrow_safe(
            db,
            """
            SELECT ua.*, b.display_name AS bot_display_name, b.session_name, b.status
            FROM userbot_assignments ua
            LEFT JOIN bots b ON b.id = ua.userbot_id
            WHERE ua.group_id = $1
            """,
            group_id,
        )

        targets_rows = await _fetch_safe(
            db,
            """
            SELECT t.*, g2.display_name AS dest_group_display, g2.title AS dest_group_title
            FROM targets t
            LEFT JOIN groups g2 ON g2.tg_chat_id = t.dest_chat_id
            WHERE t.group_id = $1
            ORDER BY t.dest_chat_id
            """,
            group_id,
        )

        schedules_rows = await _fetch_safe(
            db,
            """
            SELECT *
            FROM group_schedules
            WHERE group_id = $1
            ORDER BY start_time
            """,
            group_id,
        )

        templates_rows = await _fetch_safe(
            db,
            """
            SELECT tta.blockchain, pt.id, pt.name
            FROM target_template_assignments tta
            LEFT JOIN post_templates pt ON pt.id = tta.template_id
            WHERE tta.group_id = $1
            ORDER BY tta.blockchain
            """,
            group_id,
        )

        call_stats_row = await _fetchrow_safe(
            db,
            """
            SELECT COUNT(*) AS total_calls,
                   MAX(called_at) AS last_call_at
            FROM token_call_history
            WHERE target_chat_id = $1
            """,
            tg_chat_id,
        ) if tg_chat_id is not None else None

        recent_calls_rows = await _fetch_safe(
            db,
            """
            SELECT token_address, source_name, called_at, market_cap_at_call
            FROM token_call_history
            WHERE target_chat_id = $1
            ORDER BY called_at DESC
            LIMIT 5
            """,
            tg_chat_id,
        ) if tg_chat_id is not None else []

        queue_stats_rows = await _fetch_safe(
            db,
            """
            SELECT status, COUNT(*) AS total
            FROM call_queue
            WHERE target_group_id = $1
            GROUP BY status
            ORDER BY status
            """,
            group_id,
        )

        pending_jobs_rows = []
        pending_jobs_uses_created = False
        try:
            pending_jobs_rows = await db.fetch(
                """
                SELECT id, token_address, status, priority, scheduled_at, forwarding_userbot_id
                FROM call_queue
                WHERE target_group_id = $1
                ORDER BY scheduled_at ASC NULLS LAST
                LIMIT 5
                """,
                group_id,
            )
        except pg_exceptions.UndefinedColumnError:
            pending_jobs_rows = await db.fetch(
                """
                SELECT id,
                       token_address,
                       status,
                       priority,
                       created_at AS fallback_timestamp,
                       forwarding_userbot_id
                FROM call_queue
                WHERE target_group_id = $1
                ORDER BY created_at ASC NULLS LAST
                LIMIT 5
                """,
                group_id,
            )
            pending_jobs_uses_created = True
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.error("Group inspector pending jobs query failed: %s", exc, exc_info=True)

        gain_summary_row = await _fetchrow_safe(
            db,
            """
            SELECT
                COUNT(*) AS total_tokens,
                COUNT(*) FILTER (WHERE last_alert_at IS NOT NULL) AS tokens_alerted,
                COUNT(*) FILTER (WHERE last_alert_at IS NULL) AS pending_tokens
            FROM token_group_alerts
            WHERE chat_id = $1
            """,
            tg_chat_id,
        ) if tg_chat_id is not None else None

        gain_recent_rows = await _fetch_safe(
            db,
            """
            SELECT tga.*, tt.address
            FROM token_group_alerts tga
            LEFT JOIN tokens_tracked tt ON tt.id = tga.token_id
            WHERE tga.chat_id = $1
            ORDER BY COALESCE(tga.last_alert_at, tga.first_seen_at) DESC
            LIMIT 5
            """,
            tg_chat_id,
        ) if tg_chat_id is not None else []

        monitored_sources_rows = await _fetch_safe(
            db,
            """
            SELECT
                ms.*,
                b.display_name AS assigned_userbot_name,
                b.session_name AS assigned_session_name,
                b.status AS assigned_status,
                ARRAY_REMOVE(ARRAY_AGG(mst.target_chat_id), NULL) AS target_chat_ids
            FROM monitored_sources ms
            LEFT JOIN bots b ON b.id = ms.assigned_userbot_id
            LEFT JOIN monitored_source_targets mst ON mst.source_id = ms.id
            WHERE ms.chat_id = $1
            GROUP BY ms.id, b.display_name, b.session_name, b.status
            ORDER BY ms.created_at ASC
            """,
            tg_chat_id,
        ) if tg_chat_id is not None else []

        targets_ids = [row["id"] for row in targets_rows]
        target_state_stats = {}
        if targets_ids:
            try:
                state_rows = await db.fetch(
                    """
                    SELECT target_id,
                           COUNT(*) AS tracked_tokens,
                           MAX(last_alert_at) AS last_alert_at
                    FROM target_token_alert_state
                    WHERE target_id = ANY($1::bigint[])
                    GROUP BY target_id
                    """,
                    targets_ids,
                )
                target_state_stats = {row["target_id"]: dict(row) for row in state_rows}
            except pg_exceptions.UndefinedTableError:
                target_state_stats = {}
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error("Group inspector target state query failed: %s", exc, exc_info=True)
                target_state_stats = {}

        curated_rules_rows = []
        if tg_chat_id is not None:
            curated_rules_rows = await _fetch_safe(
                db,
                "SELECT id, name FROM curated_alpha_rules WHERE destination_chat_id = $1 ORDER BY created_at DESC",
                tg_chat_id,
            )

        payload = {
            "userbot": dict(userbot_row) if userbot_row else None,
            "templates": [dict(r) for r in templates_rows],
            "targets": [dict(r) for r in targets_rows],
            "target_state_stats": target_state_stats,
            "schedules": [dict(r) for r in schedules_rows],
            "call_stats": dict(call_stats_row) if call_stats_row else None,
            "recent_calls": [dict(r) for r in recent_calls_rows],
            "queue_stats": [dict(r) for r in queue_stats_rows],
            "pending_jobs": [dict(r) for r in pending_jobs_rows],
            "pending_jobs_use_created": pending_jobs_uses_created,
            "gain_summary": dict(gain_summary_row) if gain_summary_row else None,
            "gain_recent": [dict(r) for r in gain_recent_rows],
            "monitored_sources": [dict(r) for r in monitored_sources_rows],
            "curated_alpha_rules": [dict(r) for r in curated_rules_rows],
            "tg_chat_id": tg_chat_id,
        }

        return group, payload

    async def cmd_inspect_group(message: types.Message) -> None:
        """Detailed group inspector command (/ic <group_id>)."""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "👥 <b>Group Inspector</b>\n\n"
                "Inspect every known data point for a configured group.\n\n"
                "📋 <b>Usage:</b>\n"
                "<code>/ic &lt;group_id&gt;</code> — internal group ID (preferred)\n"
                "<code>/ic &lt;chat_id&gt;</code> — Telegram chat ID (e.g. -100...)\n\n"
                "The report includes group settings, routing, activity, and gain-alert configuration.",
                parse_mode="HTML",
            )
            return

        identifier_raw = parts[1].strip().split()[0]
        try:
            identifier_val = int(identifier_raw)
        except ValueError:
            await message.answer("❌ Provide a numeric group ID or Telegram chat ID.", parse_mode="HTML")
            return

        group_row = await _find_group_record(identifier_val)
        if not group_row:
            await message.answer(
                f"❌ Group not found for identifier <code>{html.escape(identifier_raw)}</code>.",
                parse_mode="HTML",
            )
            return

        group, payload = await _gather_group_payload(group_row["id"])
        if not group or payload is None:
            await message.answer("❌ Unable to load group details at this time.", parse_mode="HTML")
            return

        text, keyboard = _render_group_report_page(group, payload, page=1)

        await message.answer(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )

    async def handle_group_pagination(callback: types.CallbackQuery, callback_data: GroupInspectorCallback):
        if callback.from_user.id not in settings.admin_telegram_ids_list:
            await callback.answer("Unauthorized", show_alert=True)
            return

        group_id = callback_data.group_id
        group_row = await _fetchrow_safe(db, "SELECT * FROM groups WHERE id = $1", group_id)
        if not group_row:
            await callback.answer("Group not found", show_alert=True)
            try:
                await callback.message.edit_text("❌ Group no longer exists.")
            except Exception:
                pass
            return

        group, payload = await _gather_group_payload(group_id)
        if not group or payload is None:
            await callback.answer("Failed to load data", show_alert=True)
            return

        text, keyboard = _render_group_report_page(group, payload, page=callback_data.page)

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
        await callback.answer()

    async def handle_group_return(callback: types.CallbackQuery):
        if callback.from_user.id not in settings.admin_telegram_ids_list:
            await callback.answer("Unauthorized", show_alert=True)
            return

        parts = callback.data.split(':')
        if len(parts) < 4:
            await callback.answer("Invalid request", show_alert=True)
            return

        try:
            group_id = int(parts[2])
            page = int(parts[3])
        except ValueError:
            await callback.answer("Invalid request", show_alert=True)
            return

        group, payload = await _gather_group_payload(group_id)
        if not group or payload is None:
            await callback.answer("Failed to load data", show_alert=True)
            return

        text, keyboard = _render_group_report_page(group, payload, page=page)

        await callback.message.edit_text(
            text,
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
        await callback.answer()

    async def cmd_inspect(message: types.Message) -> None:
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "🔍 <b>Token Inspector Command</b>\n\n"
                "Inspect detailed information about a tracked token.\n\n"

                "📋 <b>Usage:</b>\n"
                "<code>/i &lt;contract_address&gt;</code>\n\n"

                "📖 <b>Examples:</b>\n\n"
                "1️⃣ <b>Inspect Solana token:</b>\n"
                "   <code>/i HnKk7xPZmL7KRuUg...</code>\n\n"

                "2️⃣ <b>Inspect BSC token:</b>\n"
                "   <code>/i 0x907D7eE6FB40C...</code>\n\n"

                "📊 <b>Shows:</b>\n"
                "• Page 1: Overview + Tracking (status, MC, tier)\n"
                "• Page 2: Monitored Sources (groups watching)\n"
                "• Page 3: Sources & Targets (where posted)\n"
                "• Page 4: Call Activity (forwarding history)\n\n"

                "💡 <b>Navigation:</b>\n"
                "Use emoji buttons to switch between pages",
                parse_mode='HTML'
            )
            return

        raw_address = parts[1].strip().split()[0]
        chain = _detect_chain(raw_address, sol_pattern, bnb_pattern)
        if chain is None:
            await message.answer("❌ Unrecognised address. Provide a Solana or BNB contract.")
            return

        normalized_address = raw_address.lower() if chain == "BNB" else raw_address

        token_record = await _fetch_token_record(token_model, raw_address, normalized_address)
        token_id = token_record["id"] if token_record else None
        logger.info(f"[INSPECTOR] Inspecting {chain} token {raw_address[:8]}... with token_id={token_id}")

        watchers = await _fetch_watchers(db, token_id)
        call_rows, call_stats = await _fetch_call_history(db, normalized_address)

        text, keyboard = _render_report_page(raw_address, chain, token_record, watchers, call_stats, call_rows, page=1)
        await message.answer(text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)

    async def handle_pagination(callback: types.CallbackQuery, callback_data: InspectorPageCallback):
        """Handle pagination button clicks"""
        if callback.from_user.id not in settings.admin_telegram_ids_list:
            await callback.answer("Unauthorized", show_alert=True)
            return

        raw_address = callback_data.address
        page = callback_data.page
        chain = _detect_chain(raw_address, sol_pattern, bnb_pattern)
        normalized_address = raw_address.lower() if chain == "BNB" else raw_address

        token_record = await _fetch_token_record(token_model, raw_address, normalized_address)
        token_id = token_record["id"] if token_record else None
        watchers = await _fetch_watchers(db, token_id)
        call_rows, call_stats = await _fetch_call_history(db, normalized_address)

        text, keyboard = _render_report_page(raw_address, chain, token_record, watchers, call_stats, call_rows, page=page)

        await callback.message.edit_text(text, parse_mode='HTML', disable_web_page_preview=True, reply_markup=keyboard)
        await callback.answer()

    async def cmd_restart(message: types.Message) -> None:
        """Restart monitoring a stopped token with specified tier"""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        parts = (message.text or "").split()
        if len(parts) < 2:
            await message.answer(
                "🔄 <b>Restart Token Monitoring</b>\n\n"
                "Restart monitoring a stopped token with a specific tier.\n\n"

                "📋 <b>Usage:</b>\n"
                "<code>/str &lt;contract_address&gt; [tier]</code>\n"
                "<code>/restart &lt;contract_address&gt; [tier]</code>\n\n"

                "🎚️ <b>Available Tiers:</b>\n"
                "• <code>tier_a</code> - 10s polling (0-10min old tokens)\n"
                "• <code>tier_b</code> - 30s polling (10-30min old)\n"
                "• <code>tier_c</code> - 3min polling (30min-2hr old)\n"
                "• <code>tier_d</code> - 5min polling (2-6hr old)\n"
                "• <code>tier_e</code> - 10min polling (6-24hr old)\n"
                "• <code>tier_f</code> - 30min polling (1-7 days old)\n\n"

                "📖 <b>Examples:</b>\n\n"
                "1️⃣ <b>Restart with default tier (tier_a):</b>\n"
                "   <code>/str HnKk7xPZmL7...</code>\n\n"

                "2️⃣ <b>Restart with specific tier:</b>\n"
                "   <code>/str HnKk7xPZmL7... tier_c</code>\n\n"

                "💡 <b>Tips:</b>\n"
                "• Default tier is <code>tier_a</code> if not specified\n"
                "• Clears the stop reason\n"
                "• Sets next poll time immediately",
                parse_mode='HTML'
            )
            return

        raw_address = parts[1].strip()
        tier = parts[2].lower() if len(parts) > 2 else "tier_a"

        # Validate tier
        valid_tiers = ['tier_a', 'tier_b', 'tier_c', 'tier_d', 'tier_e', 'tier_f']
        if tier not in valid_tiers:
            await message.answer(
                f"❌ Invalid tier: {html.escape(tier)}\n"
                f"Valid tiers: {', '.join(valid_tiers)}",
                parse_mode='HTML'
            )
            return

        # Validate address
        chain = _detect_chain(raw_address, sol_pattern, bnb_pattern)
        if chain is None:
            await message.answer("❌ Unrecognised address. Provide a Solana or BNB contract.")
            return

        # Find token
        token_record = await token_model.get_by_address(raw_address)
        if not token_record:
            await message.answer(f"❌ Token <code>{html.escape(raw_address)}</code> is not in the database.", parse_mode='HTML')
            return

        token_id = token_record["id"]
        current_status = token_record.get("status")
        ticker = token_record.get("ticker") or raw_address[:8]

        # Calculate next poll time based on tier
        from app.utils.tier_calculator import get_poll_interval_for_tier
        from datetime import datetime, timedelta, timezone

        poll_interval = get_poll_interval_for_tier(tier)
        next_poll = datetime.now(timezone.utc) + timedelta(seconds=poll_interval)

        # Restart the token
        await token_model.set_status(token_id, "active")
        await token_model.set_stop_reason(token_id, None)  # Clear stop reason
        await token_model.update_tier(token_id, tier, next_poll)

        # Format response
        tier_info = {
            'tier_a': "10s polling (0-10min)",
            'tier_b': "30s polling (10-30min)",
            'tier_c': "3min polling (30min-2hr)",
            'tier_d': "5min polling (2-6hr)",
            'tier_e': "10min polling (6-24hr)",
            'tier_f': "30min polling (1-7days)",
        }

        status_emoji = "🔄" if current_status == "stopped" else "✅"
        await message.answer(
            f"{status_emoji} Restarted monitoring token <b>{html.escape(ticker)}</b>\n"
            f"Address: <code>{html.escape(raw_address)}</code>\n"
            f"Status: <b>active</b>\n"
            f"Tier: <b>{tier}</b> ({tier_info.get(tier, 'unknown')})\n"
            f"Next Poll: {next_poll.strftime('%H:%M:%S UTC')}",
            parse_mode='HTML'
        )

    async def cmd_trigger(message: types.Message) -> None:
        """Trigger forced gain alert in all targets where this token was posted"""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        from app.dex import get_dex_service
        from decimal import Decimal

        parts = (message.text or "").split()

        if len(parts) < 2:
            await message.answer(
                "🎯 <b>Trigger Gain Alert Command</b>\n\n"
                "Force-send gain alerts to target groups where a token was posted.\n\n"

                "📋 <b>Usage:</b>\n"
                "<code>/tri &lt;contract_address&gt; [flags]</code>\n"
                "<code>/tri &lt;group_id&gt; &lt;contract_address&gt; [flags]</code>\n\n"

                "🚩 <b>Flags:</b>\n"
                "  <code>p</code> = Use <b>peak MC</b> instead of current MC\n"
                "  <code>c</code> = Include <b>chart</b> in alert\n\n"

                "📖 <b>Examples:</b>\n\n"
                "1️⃣ <b>All targets, current MC, no chart:</b>\n"
                "   <code>/tri HnKk7xPZmL7...</code>\n\n"

                "2️⃣ <b>All targets, current MC, with chart:</b>\n"
                "   <code>/tri HnKk7xPZmL7... c</code>\n\n"

                "3️⃣ <b>All targets, peak MC, no chart:</b>\n"
                "   <code>/tri HnKk7xPZmL7... p</code>\n\n"

                "4️⃣ <b>All targets, peak MC, with chart:</b>\n"
                "   <code>/tri HnKk7xPZmL7... p c</code>\n\n"

                "5️⃣ <b>Specific group, peak MC, with chart:</b>\n"
                "   <code>/tri -1001234567890 HnKk7xPZmL7... p c</code>\n\n"

                "💡 <b>Tips:</b>\n"
                "• Flags can be in any order (<code>c p</code> or <code>p c</code>)\n"
                "• Each group uses its custom template if configured\n"
                "• Replies to the original CA message in each group\n"
                "• Uses assigned userbot or management bot per group settings",
                parse_mode='HTML'
            )
            return

        # Parse arguments: detect if first arg is group_id (numeric) or contract address
        target_group_id = None
        raw_address = None
        include_chart = False
        use_peak_mc = False

        # Check if first argument looks like a group ID (starts with - or is numeric)
        first_arg = parts[1].strip()
        try:
            # Try to parse as integer (group ID)
            potential_group_id = int(first_arg)
            # If successful, this is a group ID
            if len(parts) < 3:
                await message.answer(
                    "❌ Missing contract address after group ID\n"
                    "Usage: /tri <group_id> <contract_address> [p] [c]",
                    parse_mode='HTML'
                )
                return
            target_group_id = potential_group_id
            raw_address = parts[2].strip()
            # Check for flags in remaining args
            flags = [p.lower() for p in parts[3:]]
            include_chart = 'c' in flags
            use_peak_mc = 'p' in flags or 'peak' in flags
        except ValueError:
            # First arg is not numeric, so it's a contract address
            raw_address = first_arg
            # Check for flags in remaining args
            flags = [p.lower() for p in parts[2:]]
            include_chart = 'c' in flags
            use_peak_mc = 'p' in flags or 'peak' in flags

        # Validate address format
        chain = _detect_chain(raw_address, sol_pattern, bnb_pattern)
        if chain is None:
            await message.answer("❌ Unrecognised address. Provide a Solana or BNB contract.")
            return

        try:
            # Find token in database
            token = await token_model.get_by_address(raw_address)

            if not token:
                await message.answer(
                    f"❌ Token not found: <code>{html.escape(raw_address[:8])}...</code>",
                    parse_mode='HTML'
                )
                return

            token_id = token['id']
            ticker = token.get('ticker') or raw_address[:8]
            first_seen_mc = token.get('first_seen_mc') or Decimal(0)

            # Choose MC based on flag
            if use_peak_mc:
                chosen_mc = token.get('peak_mc') or Decimal(0)
                mc_type = "peak"
            else:
                chosen_mc = token.get('last_mc') or Decimal(0)
                mc_type = "current"

            if chosen_mc <= 0 or first_seen_mc <= 0:
                await message.answer(
                    f"❌ Cannot trigger alert for <b>{html.escape(ticker)}</b>\n"
                    f"Missing market cap data ({mc_type} MC or first MC is zero). Token may need to be polled first.",
                    parse_mode='HTML'
                )
                return

            # Get targets where this token was posted with their settings
            if target_group_id:
                # Query specific target group with latest message and userbot settings
                targets = await db.fetch("""
                    SELECT DISTINCT ON (tch.target_chat_id)
                        tch.target_chat_id,
                        tch.forwarded_message_id,
                        ms.assigned_userbot_id,
                        ms.use_management_bot,
                        ms.template_text,
                        tga.original_user_id,
                        tga.first_seen_mc AS group_first_seen_mc
                    FROM token_call_history tch
                    LEFT JOIN token_group_alerts tga
                        ON tga.token_id = $3
                        AND tga.chat_id = tch.target_chat_id
                    LEFT JOIN monitored_sources ms
                        ON ms.chat_id = tch.target_chat_id
                        AND (ms.user_id = tga.original_user_id OR ms.user_id IS NULL)
                    WHERE LOWER(tch.token_address) = LOWER($1)
                    AND tch.target_chat_id = $2
                    ORDER BY tch.target_chat_id, tch.called_at DESC
                """, raw_address, target_group_id, token_id)

                if not targets:
                    await message.answer(
                        f"❌ Token <b>{html.escape(ticker)}</b> was not posted to group <code>{target_group_id}</code>\n"
                        f"Check the group ID and try again.",
                        parse_mode='HTML'
                    )
                    return
            else:
                # Query all targets with latest message and userbot settings
                targets = await db.fetch("""
                    SELECT DISTINCT ON (tch.target_chat_id)
                        tch.target_chat_id,
                        tch.forwarded_message_id,
                        ms.assigned_userbot_id,
                        ms.use_management_bot,
                        ms.template_text,
                        tga.original_user_id,
                        tga.first_seen_mc AS group_first_seen_mc
                    FROM token_call_history tch
                    LEFT JOIN token_group_alerts tga
                        ON tga.token_id = $2
                        AND tga.chat_id = tch.target_chat_id
                    LEFT JOIN monitored_sources ms
                        ON ms.chat_id = tch.target_chat_id
                        AND (ms.user_id = tga.original_user_id OR ms.user_id IS NULL)
                    WHERE LOWER(tch.token_address) = LOWER($1)
                    AND tch.target_chat_id IS NOT NULL
                    ORDER BY tch.target_chat_id, tch.called_at DESC
                """, raw_address, token_id)

                if not targets:
                    await message.answer(
                        f"❌ No targets found for <b>{html.escape(ticker)}</b>\n"
                        f"This token has not been posted to any target channels.",
                        parse_mode='HTML'
                    )
                    return

            logger.info(f"[TRIGGER] Found {len(targets)} target(s) for {raw_address[:8]}...")

            target_count = len(targets)

            # Get DexService for alert dispatching (need it early for formatting)
            dex_service = get_dex_service()

            # Build status message
            mc_display = f"{mc_type.upper()} MC: {dex_service._format_mc_shorthand(chosen_mc)}"

            if target_group_id:
                status_msg = (
                    f"🎯 Triggering forced gain alert for <b>{html.escape(ticker)}</b>\n"
                    f"📍 Target: <code>{target_group_id}</code> (specific)\n"
                    f"💰 {mc_display}\n"
                    f"📊 Chart: {'✅ Enabled' if include_chart else '❌ Disabled'}\n\n"
                    f"Sending alert..."
                )
            else:
                status_msg = (
                    f"🎯 Triggering forced gain alert for <b>{html.escape(ticker)}</b>\n"
                    f"📍 Targets: {target_count} (all)\n"
                    f"💰 {mc_display}\n"
                    f"📊 Chart: {'✅ Enabled' if include_chart else '❌ Disabled'}\n\n"
                    f"Sending alerts..."
                )

            await message.answer(status_msg, parse_mode='HTML')

            # Get global template as fallback
            from app.config import get_gain_alert_template_text
            from app.gain_alert_templates import DEFAULT_GAIN_ALERT_TEMPLATE

            global_template = await get_gain_alert_template_text()

            # Base template values (will be customized per-group for first_market_cap)
            elapsed = dex_service._format_elapsed_time(token.get('first_seen_at'))
            base_template_values = {
                "address": raw_address,
                "token_symbol": ticker,
                "elapsed_time": elapsed,
            }

            # Fetch chart if requested
            chart_bytes = None
            if include_chart and dex_service.chart_fetcher:
                from app.config import get_global_chart_settings
                chart_config = await get_global_chart_settings()
                chart_bot_id = chart_config.get('chart_bot_id')

                if chart_bot_id:
                    try:
                        logger.info(f"[TRIGGER] Fetching chart for {raw_address[:8]}...")
                        chart_bytes = await dex_service.chart_fetcher.fetch_chart_for_token(
                            contract_address=raw_address,
                            chart_bot_id=int(chart_bot_id),
                        )
                        if chart_bytes:
                            logger.info(f"[TRIGGER] Chart fetched ({len(chart_bytes)} bytes)")
                    except Exception as exc:
                        logger.error(f"[TRIGGER] Chart fetch failed: {exc}", exc_info=True)

            # Send alerts to all targets
            success_count = 0
            failed_count = 0

            # Cache for workers
            workers_cache = {}

            for target_row in targets:
                target_chat_id = target_row['target_chat_id']
                reply_to_msg_id = target_row['forwarded_message_id']
                use_management_bot = bool(target_row.get('use_management_bot'))
                assigned_userbot_id = target_row.get('assigned_userbot_id')
                custom_template = target_row.get('template_text')
                group_first_seen_mc = target_row.get('group_first_seen_mc')

                # Use group-specific first_seen_mc if available, otherwise fall back to token's global first_seen_mc
                if group_first_seen_mc and group_first_seen_mc > 0:
                    effective_first_mc = Decimal(str(group_first_seen_mc))
                else:
                    effective_first_mc = first_seen_mc

                # Calculate multiplier using effective first_seen_mc
                multiplier_value = float(chosen_mc / effective_first_mc) if effective_first_mc > 0 else 1.0

                logger.debug(
                    f"[TRIGGER] {target_chat_id}: group_first_mc={group_first_seen_mc}, "
                    f"token_first_mc={first_seen_mc}, effective={effective_first_mc}, "
                    f"chosen_mc={chosen_mc}, multiplier={multiplier_value:.2f}x"
                )

                # Build template values for this group
                group_template_values = dict(base_template_values)
                group_template_values.update({
                    "multiplier": f"{multiplier_value:.1f}x",
                    "first_market_cap": dex_service._format_mc_shorthand(effective_first_mc),
                    "current_market_cap": dex_service._format_mc_shorthand(chosen_mc),
                    "gain_emoji": dex_service._multiplier_to_emoji(multiplier_value),
                })

                # Select template: custom > global > default
                template_to_use = custom_template or global_template or DEFAULT_GAIN_ALERT_TEMPLATE

                # Format alert message for this group
                try:
                    alert_message = template_to_use.format(**group_template_values)
                except KeyError as exc:
                    logger.error(
                        f"[TRIGGER] Template formatting failed for {target_chat_id}: missing key {exc}"
                    )
                    failed_count += 1
                    continue

                logger.info(
                    f"[TRIGGER] Sending to {target_chat_id}, "
                    f"reply_to={reply_to_msg_id}, "
                    f"use_mgmt_bot={use_management_bot}, "
                    f"assigned_userbot={assigned_userbot_id}, "
                    f"custom_template={'Yes' if custom_template else 'No'}"
                )

                try:
                    result = None

                    # Determine which bot to use
                    if use_management_bot:
                        # Use management bot if configured
                        if not dex_service.management_bot:
                            logger.warning(
                                f"[TRIGGER] Management bot not available for {target_chat_id}, falling back to userbot"
                            )
                            use_management_bot = False

                    if use_management_bot:
                        # Send via management bot
                        result = await dex_service._send_via_management_bot(
                            target_chat_id,
                            alert_message,
                            reply_to_msg_id,
                            photo_bytes=chart_bytes,
                        )
                    else:
                        # Send via userbot
                        if not dex_service.userbot_manager:
                            logger.error(f"[TRIGGER] No userbot manager available")
                            failed_count += 1
                            continue

                        worker = None
                        if assigned_userbot_id:
                            worker = dex_service.userbot_manager.get_worker(assigned_userbot_id)
                            if not worker:
                                logger.warning(
                                    f"[TRIGGER] Assigned userbot {assigned_userbot_id} not available, using fallback"
                                )

                        if not worker:
                            # Get any available worker
                            workers = dex_service.userbot_manager.get_all_workers()
                            if not workers:
                                logger.error(f"[TRIGGER] No active workers available")
                                failed_count += 1
                                continue
                            worker = next(iter(workers.values()))

                        worker_id = getattr(worker, 'userbot_id', None)
                        if worker_id is None:
                            logger.error(f"[TRIGGER] Worker missing userbot_id")
                            failed_count += 1
                            continue

                        # Get or create executor for this worker
                        executor = workers_cache.get(worker_id)
                        if executor is None:
                            existing_executor = getattr(worker, 'call_executor', None)
                            if existing_executor:
                                executor = existing_executor
                            else:
                                from app.userbot.call_executor import CallExecutor
                                executor = CallExecutor(worker.userbot_id, worker.session_manager)
                                worker.call_executor = executor
                            workers_cache[worker_id] = executor

                        # Send via userbot
                        result = await executor.send_call_message(
                            target_chat_id=target_chat_id,
                            message=alert_message,
                            token_address=raw_address,
                            reply_to_message_id=reply_to_msg_id,
                            photo_bytes=chart_bytes,
                        )

                    if result and result.get('success'):
                        success_count += 1
                        logger.info(f"[TRIGGER] Successfully sent to {target_chat_id}")
                    else:
                        failed_count += 1
                        error_text = result.get('error') if result else 'No result'
                        logger.error(f"[TRIGGER] Failed to send to {target_chat_id}: {error_text}")

                except Exception as exc:
                    failed_count += 1
                    logger.error(f"[TRIGGER] Error sending to {target_chat_id}: {exc}", exc_info=True)

            # Report results
            if success_count > 0:
                if target_group_id:
                    result_msg = (
                        f"✅ Forced gain alert sent!\n\n"
                        f"<b>{html.escape(ticker)}</b>\n"
                        f"📍 Target: <code>{target_group_id}</code>\n"
                        f"✅ Status: Success\n"
                        f"💰 MC Type: {mc_type.upper()}\n"
                        f"📊 Chart: {'Included' if chart_bytes else 'Not included'}"
                    )
                else:
                    result_msg = (
                        f"✅ Forced gain alert sent!\n\n"
                        f"<b>{html.escape(ticker)}</b>\n"
                        f"✅ Sent: {success_count}/{target_count}\n"
                        f"❌ Failed: {failed_count}/{target_count}\n"
                        f"💰 MC Type: {mc_type.upper()}\n"
                        f"📊 Chart: {'Included' if chart_bytes else 'Not included'}"
                    )
                await message.answer(result_msg, parse_mode='HTML')
            else:
                if target_group_id:
                    await message.answer(
                        f"❌ Failed to send alert\n\n"
                        f"Target <code>{target_group_id}</code> failed. Check logs for details.",
                        parse_mode='HTML'
                    )
                else:
                    await message.answer(
                        f"❌ Failed to send alerts\n\n"
                        f"All {target_count} targets failed. Check logs for details.",
                        parse_mode='HTML'
                    )

        except Exception as e:
            logger.error(f"Error in cmd_trigger: {e}", exc_info=True)
            await message.answer(
                f"❌ Error triggering alert: {html.escape(str(e))}",
                parse_mode='HTML'
            )

    async def cmd_stop(message: types.Message) -> None:
        """Stop monitoring a token by contract address"""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer(
                "⛔ <b>Stop Token Monitoring</b>\n\n"
                "Stop monitoring a token by contract address.\n\n"

                "📋 <b>Usage:</b>\n"
                "<code>/stop &lt;contract_address&gt;</code>\n\n"

                "📖 <b>Examples:</b>\n\n"
                "1️⃣ <b>Stop Solana token:</b>\n"
                "   <code>/stop HnKk7xPZmL7KRuUg...</code>\n\n"

                "2️⃣ <b>Stop BSC token:</b>\n"
                "   <code>/stop 0x907D7eE6FB40C...</code>\n\n"

                "⚙️ <b>What happens:</b>\n"
                "• Sets token status to <code>stopped</code>\n"
                "• Sets stop reason to <code>admin_manual_stop</code>\n"
                "• Removes from polling scheduler\n"
                "• No more gain alerts will be sent\n\n"

                "💡 <b>Tips:</b>\n"
                "• Use <code>/str</code> to restart monitoring\n"
                "• Token data remains in database",
                parse_mode='HTML'
            )
            return

        raw_address = parts[1].strip().split()[0]
        chain = _detect_chain(raw_address, sol_pattern, bnb_pattern)
        if chain is None:
            await message.answer("❌ Unrecognised address. Provide a Solana or BNB contract.")
            return

        # Find token by address
        token_record = await token_model.get_by_address(raw_address)
        if not token_record:
            await message.answer(f"❌ Token <code>{html.escape(raw_address)}</code> is not being tracked.", parse_mode='HTML')
            return

        token_id = token_record["id"]
        current_status = token_record.get("status")

        if current_status == "stopped":
            await message.answer(
                f"⚠️ Token <code>{html.escape(raw_address)}</code> is already stopped.\n"
                f"Stop Reason: {html.escape(token_record.get('stop_reason') or 'Unknown')}",
                parse_mode='HTML'
            )
            return

        # Stop the token
        await token_model.set_status(token_id, "stopped")
        await token_model.set_stop_reason(token_id, "admin_manual_stop")

        ticker = token_record.get("ticker") or raw_address[:8]
        await message.answer(
            f"✅ Stopped monitoring token <b>{html.escape(ticker)}</b>\n"
            f"Address: <code>{html.escape(raw_address)}</code>\n"
            f"Status: <b>stopped</b>\n"
            f"Reason: admin_manual_stop",
            parse_mode='HTML'
        )

    async def cmd_clean_contracts(message: types.Message) -> None:
        """Prompt admin confirmation to wipe all contract addresses."""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        cleanup_service = context.cleanup_service
        if cleanup_service is None:
            await message.answer("❌ Cleanup service unavailable.", parse_mode="HTML")
            return

        await cleanup_service.prompt_wipe_contracts(message)

    dispatcher.message.register(
        cmd_inspect_group,
        Command(commands=["ic"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        cmd_inspect,
        Command(commands=["i"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        cmd_restart,
        Command(commands=["restart", "str"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        cmd_stop,
        Command(commands=["stop"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        cmd_clean_contracts,
        Command(commands=["clean_ca", "wipe_ca"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    async def cmd_all_commands(message: types.Message) -> None:
        """Show all available admin commands"""
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        await message.answer(
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
            parse_mode='HTML'
        )

    dispatcher.message.register(
        cmd_trigger,
        Command(commands=["trigger", "tri"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.message.register(
        cmd_all_commands,
        Command(commands=["all", "commands", "help"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        handle_pagination,
        InspectorPageCallback.filter(),
    )

    dispatcher.callback_query.register(
        handle_group_return,
        F.data.startswith("ginsp:return:"),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        handle_group_pagination,
        GroupInspectorCallback.filter(),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )


def _detect_chain(address: str, sol_pattern: re.Pattern, bnb_pattern: re.Pattern) -> str | None:
    if sol_pattern.fullmatch(address):
        return "SOL"
    if bnb_pattern.fullmatch(address):
        return "BNB"
    return None


async def _fetch_token_record(token_model: TokenModel, raw_address: str, normalized: str):
    try:
        record = await token_model.db.fetchrow(
            "SELECT * FROM tokens_tracked WHERE LOWER(address) = LOWER($1) LIMIT 1",
            raw_address,
        )
        return record
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Inspector token lookup failed for %s: %s", raw_address, exc, exc_info=True)
        return None


async def _fetch_watchers(db, token_id: int | None) -> Sequence[dict[str, object]]:
    if not token_id:
        return []

    try:
        # Debug: Check if token_group_alerts has any entries for this token
        count = await db.fetchval(
            "SELECT COUNT(*) FROM token_group_alerts WHERE token_id = $1",
            token_id
        )
        logger.info(f"[INSPECTOR] token_id={token_id} has {count} entries in token_group_alerts")

        rows = await db.fetch(
            """
            SELECT
                tga.chat_id,
                tga.original_user_id,
                tga.first_seen_mc,
                tga.last_alert_mc,
                tga.created_at,
                tga.original_message_id,
                call_info.target_chat_id AS posted_target,
                call_info.sent_message_id AS posted_message_id,
                call_info.sent_at AS posted_at,
                call_info.source_name AS posted_source,
                ms.display_name,
                ms.chat_type,
                ms.is_enabled,
                ms.sensitivity_pct,
                ms.assigned_userbot_id,
                ms.use_management_bot,
                ms.chart_enabled,
                ms.chart_bot_id,
                ms.chart_mc_threshold,
                ms.template_text,
                ms.chart_min_age_minutes,
                ms.chart_min_liquidity_usd,
                ms.chart_min_volume_usd,
                ms.chart_min_multiplier,
                ms.chart_max_price_change_pct,
                ms.chart_checks_required,
                ms.last_guardrail_result
            FROM token_group_alerts tga
            JOIN tokens_tracked tt ON tt.id = tga.token_id
            LEFT JOIN monitored_sources ms
                ON ms.chat_id = tga.chat_id
               AND (
                    ms.user_id = tga.original_user_id
                    OR ms.user_id IS NULL
                )
            LEFT JOIN LATERAL (
                SELECT
                    ch.target_chat_id,
                    ch.forwarded_message_id AS sent_message_id,
                    ch.called_at AS sent_at,
                    ch.source_name
                FROM token_call_history ch
                WHERE LOWER(ch.token_address) = LOWER(tt.address)
                  AND ch.target_chat_id = tga.chat_id
                ORDER BY ch.called_at DESC
                LIMIT 1
            ) call_info ON TRUE
            WHERE tga.token_id = $1
            ORDER BY tga.chat_id
            """,
            token_id,
        )
        return [dict(row) for row in rows]
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Inspector watcher query failed for token %s: %s", token_id, exc, exc_info=True)
        return []


async def _fetch_call_history(db, address: str):
    try:
        # Debug: Check if token_call_history has any entries for this address
        count = await db.fetchval(
            "SELECT COUNT(*) FROM token_call_history WHERE LOWER(token_address) = LOWER($1)",
            address
        )
        logger.info(f"[INSPECTOR] address={address[:8]}... has {count} entries in token_call_history")

        rows = await db.fetch(
            """
            SELECT
                tch.called_at,
                tch.target_chat_id,
                tch.source_chat_id,
                tch.source_name,
                tch.source_type,
                tch.forwarding_userbot_id,
                tch.routing_rule_id,
                tch.curated_alpha_rule_id,
                tch.market_cap_at_call,
                tch.caller_name,
                tch.caller_user_id,
                tch.call_job_id,
                tch.forwarded_message_id,
                COALESCE(g.display_name, g.title, 'Chat ' || tch.target_chat_id::TEXT) AS target_name
            FROM token_call_history tch
            LEFT JOIN groups g ON g.tg_chat_id = tch.target_chat_id
            WHERE LOWER(tch.token_address) = LOWER($1)
            ORDER BY tch.called_at DESC
            LIMIT 10
            """,
            address,
        )

        stats = await db.fetchrow(
            """
            SELECT
                COUNT(*)                          AS total,
                COUNT(*) FILTER (WHERE called_at > NOW() - INTERVAL '24 hours') AS last_24h,
                COUNT(*) FILTER (WHERE called_at > NOW() - INTERVAL '7 days')  AS last_7d,
                MIN(called_at)                    AS first_call,
                MAX(called_at)                    AS last_call,
                COUNT(*) FILTER (WHERE target_chat_id IS NOT NULL) AS with_targets,
                COUNT(*) FILTER (WHERE forwarding_userbot_id IS NOT NULL) AS with_userbots
            FROM token_call_history
            WHERE LOWER(token_address) = LOWER($1)
            """,
            address,
        )

        return [dict(row) for row in rows], dict(stats or {})
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Inspector call history lookup failed for %s: %s", address, exc, exc_info=True)
        return [], {}


def _render_group_report_page(
    group: dict[str, Any],
    payload: dict[str, Any],
    page: int = 1,
) -> tuple[str, InlineKeyboardMarkup | None]:
    total_pages = 4
    if page < 1 or page > total_pages:
        page = 1

    if page == 1:
        text = _build_group_overview_page(group, payload)
    elif page == 2:
        text = _build_group_routing_page(group, payload)
    elif page == 3:
        text = _build_group_activity_page(group, payload)
    else:
        text = _build_group_gain_page(group, payload)

    keyboard = _build_group_navigation_keyboard(group, payload, page, total_pages)
    return text, keyboard


def _build_group_overview_page(group: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = [
        "<b>👥 Group Overview</b>",
        f"ID: <code>{group['id']}</code>",
        f"Chat ID: <code>{group.get('tg_chat_id') or '—'}</code>",
        f"Title: {html.escape(group.get('title') or '—')}",
        f"Display: {html.escape(group.get('display_name') or '—')}",
        f"Status: {_format_status_with_icon(group.get('enabled'))}",
        f"Daily Cap: {group.get('daily_cap') or '∞'}",
        f"Cooldown: {group.get('cooldown_minutes') or 0} min",
        f"Notif Channel: <code>{group.get('notif_channel_id') or '—'}</code>",
        f"Created: {_format_time(group.get('created_at'))}",
    ]

    lines.append("\n<b>🤖 Userbot</b>")
    userbot = payload.get("userbot")
    if userbot:
        lines.extend(
            [
                f"ID: <code>{userbot.get('userbot_id')}</code>",
                f"Name: {html.escape(userbot.get('bot_display_name') or userbot.get('session_name') or '—')}",
                f"Status: {html.escape(userbot.get('status') or 'unknown')}",
                f"Assigned: {_format_time(userbot.get('created_at'))}",
            ]
        )
    else:
        lines.append("No dedicated userbot assigned.")

    lines.append("\n<b>🧩 Templates</b>")
    templates = payload.get("templates") or []
    if not templates:
        lines.append("No template overrides assigned.")
    else:
        for tpl in templates[:6]:
            name = tpl.get("name") or f"Template #{tpl.get('id')}"
            lines.append(f"{tpl.get('blockchain')} → {html.escape(name)} (#{tpl.get('id')})")
        if len(templates) > 6:
            lines.append(f"... and {len(templates) - 6} more")

    return "\n".join(lines)


def _build_group_routing_page(group: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = ["<b>🎯 Targets</b>"]
    targets = payload.get("targets") or []
    target_stats = payload.get("target_state_stats") or {}
    if not targets:
        lines.append("No forwarding targets configured.")
    else:
        for record in targets[:6]:
            dest_chat_id = record.get("dest_chat_id")
            dest_name = record.get("dest_group_display") or record.get("dest_group_title")
            name_part = f" → {html.escape(dest_name)}" if dest_name else ""
            lines.append(f"<code>{dest_chat_id}</code>{name_part}")
            lines.append(
                f"  Alerts: {_format_yes_no(record.get('alerts_enabled'))} | "
                f"Thresholds: {_format_thresholds(record.get('alerts_thresholds'))}"
            )
            lines.append(
                f"  Modes: {_format_modes(record.get('alerts_modes'))} | "
                f"Sensitivity: {record.get('alerts_sensitivity_percent')}"
            )
            stats = target_stats.get(record.get("id")) or {}
            lines.append(
                f"  Tracked Tokens: {stats.get('tracked_tokens', 0)} | "
                f"Last Alert: {_format_time(stats.get('last_alert_at'))}"
            )
            lines.append(f"  Added: {_format_time(record.get('created_at'))}")
        if len(targets) > 6:
            lines.append(f"... and {len(targets) - 6} more")

    lines.append("\n<b>🗓 Schedules</b>")
    schedules = payload.get("schedules") or []
    if not schedules:
        lines.append("No active schedules.")
    else:
        for sched in schedules[:8]:
            lines.append(
                f"{_format_weekdays_list(sched.get('weekdays'))} "
                f"{sched.get('start_time')}→{sched.get('end_time')} "
                f"(max {sched.get('max_calls_in_window') or '∞'})"
            )
        if len(schedules) > 8:
            lines.append(f"... and {len(schedules) - 8} more")

    return "\n".join(lines)


def _build_group_activity_page(group: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = ["<b>☎️ Call Activity</b>"]
    call_stats = payload.get("call_stats") or {}
    lines.append(f"Total Calls Logged: {call_stats.get('total_calls', 0)}")
    lines.append(f"Last Call: {_format_time(call_stats.get('last_call_at'))}")

    recent_calls = payload.get("recent_calls") or []
    if recent_calls:
        for rec in recent_calls[:6]:
            lines.append(
                f"• {_format_time(rec.get('called_at'))} — {_shorten_address(rec.get('token_address'))} "
                f"(MC {_format_money_from_cents(rec.get('market_cap_at_call'))}) via "
                f"{html.escape(rec.get('source_name') or 'Unknown')}"
            )
        if len(recent_calls) > 6:
            lines.append(f"... and {len(recent_calls) - 6} more")
    else:
        lines.append("No call history yet.")

    lines.append("\n<b>📬 Queue</b>")
    queue_stats = payload.get("queue_stats") or []
    if queue_stats:
        summary = ", ".join(f"{row['status']}: {row['total']}" for row in queue_stats)
        lines.append(summary)
    else:
        lines.append("No queued jobs.")

    pending_jobs = payload.get("pending_jobs") or []
    if pending_jobs:
        lines.append("\n<b>🕒 Pending Jobs</b>")
        use_created = payload.get("pending_jobs_use_created")
        for job in pending_jobs[:5]:
            timestamp = job.get("fallback_timestamp") if use_created else job.get("scheduled_at")
            lines.append(
                f"• #{job['id']} {job['status']} {_shorten_address(job.get('token_address'))} "
                f"(prio {job.get('priority')}, sched {_format_time(timestamp)})"
            )
        if len(pending_jobs) > 5:
            lines.append(f"... and {len(pending_jobs) - 5} more")

    return "\n".join(lines)


def _build_group_gain_page(group: dict[str, Any], payload: dict[str, Any]) -> str:
    lines = ["<b>🚀 Gain Alerts & Monitors</b>"]
    summary = payload.get("gain_summary")
    if summary:
        lines.append(
            f"Tracked Tokens: {summary.get('total_tokens', 0)} "
            f"(alerts sent: {summary.get('tokens_alerted', 0)}, pending: {summary.get('pending_tokens', 0)})"
        )
    else:
        lines.append("No gain-alert state recorded.")

    recent = payload.get("gain_recent") or []
    if recent:
        lines.append("\n<b>Recent Activity</b>")
        for alert in recent[:6]:
            lines.append(
                f"• {_shorten_address(alert.get('address'))} | "
                f"Baseline {_format_money(alert.get('first_seen_mc'))} | "
                f"Last Alert {_format_time(alert.get('last_alert_at'))}"
            )
        if len(recent) > 6:
            lines.append(f"... and {len(recent) - 6} more")

    sources = payload.get("monitored_sources") or []
    lines.append("\n<b>👀 Monitored Sources</b>")
    if not sources:
        lines.append("No monitored-source overrides attach to this chat.")
    else:
        for source in sources[:6]:
            title = f"ID {source['id']} · {source['chat_type']} · User {source.get('user_id') or '—'}"
            branches: list[tuple[str, str | None] | tuple[str, str | None, bool]] = [
                ("Enabled", _format_yes_no(source.get('is_enabled'))),
                ("Sensitivity", source.get('sensitivity_pct')),
                ("Mgmt Bot", _format_yes_no(source.get('use_management_bot'))),
            ]
            assigned_label = source.get("assigned_userbot_name") or source.get("assigned_session_name")
            if assigned_label:
                branches.append(("Userbot", assigned_label))
            if source.get("chart_enabled"):
                branches.append(("Chart", _format_chart(source)))
            targets_list = source.get("target_chat_ids") or []
            if targets_list:
                branches.append(("Extra Targets", ", ".join(str(x) for x in targets_list)))
            template_text = source.get("template_text")
            if template_text:
                snippet = shorten(template_text, width=80, placeholder="…")
                branches.append(("Template", snippet))
            tree = _render_tree(title, branches, title_safe=True)
            if tree:
                lines.append(tree)
        if len(sources) > 6:
            lines.append(f"... and {len(sources) - 6} more")

    return "\n".join(lines)


def _build_group_navigation_keyboard(
    group: dict[str, Any],
    payload: dict[str, Any],
    current_page: int,
    total_pages: int,
) -> InlineKeyboardMarkup:
    group_id = group["id"]
    tg_chat_id = group.get("tg_chat_id")

    page_emojis = {1: "📊", 2: "🎯", 3: "☎️", 4: "🚀"}
    rows: list[list[InlineKeyboardButton]] = [[]]

    if current_page > 1:
        rows[0].append(
            InlineKeyboardButton(
                text="◀️ Prev",
                callback_data=GroupInspectorCallback(group_id=group_id, page=current_page - 1).pack(),
            )
        )

    rows[0].append(
        InlineKeyboardButton(
            text=f"{page_emojis.get(current_page, '📄')} {current_page}/{total_pages}",
            callback_data="noop",
        )
    )

    if current_page < total_pages:
        rows[0].append(
            InlineKeyboardButton(
                text="Next ▶️",
                callback_data=GroupInspectorCallback(group_id=group_id, page=current_page + 1).pack(),
            )
        )

    quick_nav = []
    for page_num in range(1, total_pages + 1):
        emoji = page_emojis.get(page_num, "📄")
        if page_num == current_page:
            quick_nav.append(InlineKeyboardButton(text=f"• {emoji} •", callback_data="noop"))
        else:
            quick_nav.append(
                InlineKeyboardButton(
                    text=emoji,
                    callback_data=GroupInspectorCallback(group_id=group_id, page=page_num).pack(),
                )
            )
    rows.append(quick_nav)

    suffix = f":ginsp-{current_page}"

    primary_actions: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text="⚙️ Group Menu", callback_data=f"group:view:{group_id}{suffix}"),
        InlineKeyboardButton(text="📊 Group Stats", callback_data=f"group:stats:{group_id}"),
    ]

    chat_url = _build_chat_url(tg_chat_id)
    if chat_url:
        primary_actions.append(InlineKeyboardButton(text="🔗 Open Chat", url=chat_url))

    rows.append(primary_actions)

    feature_buttons: list[InlineKeyboardButton] = []
    if payload.get("targets"):
        feature_buttons.append(
            InlineKeyboardButton(text="🎯 Targets", callback_data=f"group:view:{group_id}{suffix}")
        )

    if payload.get("schedules"):
        feature_buttons.append(
            InlineKeyboardButton(text="📅 Schedules", callback_data=f"group:schedules:{group_id}")
        )

    if payload.get("templates"):
        feature_buttons.append(InlineKeyboardButton(text="🧩 Templates", callback_data="menu:templates"))

    if payload.get("monitored_sources"):
        feature_buttons.append(InlineKeyboardButton(text="📡 Sources", callback_data="menu:sources"))
        if tg_chat_id:
            feature_buttons.append(
                InlineKeyboardButton(text="🚀 Gain Alerts", callback_data=f"gain_alerts:view:{tg_chat_id}")
            )

    curated_rules = payload.get("curated_alpha_rules") or []
    if curated_rules:
        rule = curated_rules[0]
        label = rule.get("name") or f"Rule #{rule['id']}"
        label = (label[:14] + "…") if len(label) > 17 else label
        feature_buttons.append(
            InlineKeyboardButton(text=f"✨ {label}", callback_data=f"curate_alpha:view:{rule['id']}")
        )
        feature_buttons.append(InlineKeyboardButton(text="✨ All Rules", callback_data="curate_alpha:list"))

    if feature_buttons:
        rows.append(feature_buttons[:3])
        if len(feature_buttons) > 3:
            rows.append(feature_buttons[3:6])

    sources = payload.get("monitored_sources") or []
    if sources:
        source_buttons: list[InlineKeyboardButton] = []
        for entry in sources[:3]:
            source_id = entry.get("id")
            if not source_id:
                continue
            display = entry.get("display_name") or entry.get("chat_id") or entry.get("chat_type") or "Source"
            display = str(display)
            if len(display) > 14:
                display = display[:13] + "…"
            source_buttons.append(
                InlineKeyboardButton(
                    text=f"📡 {display}",
                    callback_data=f"sources:source_details:{source_id}",
                )
            )
        if len(sources) > 3:
            source_buttons.append(InlineKeyboardButton(text="More Sources", callback_data="menu:sources"))
        if source_buttons:
            rows.append(source_buttons)

    return InlineKeyboardMarkup(inline_keyboard=rows)


def _format_status_with_icon(value: bool | None) -> str:
    return "🟢 Enabled" if value else "⚪️ Disabled"


def _format_yes_no(value: bool | None) -> str:
    return "Yes" if value else "No"


def _format_thresholds(thresholds) -> str:
    thresholds = _parse_json_field(thresholds)
    if isinstance(thresholds, (list, tuple)):
        return ", ".join(f"{item}x" for item in thresholds) if thresholds else "—"
    return str(thresholds) if thresholds is not None else "—"


def _format_modes(modes) -> str:
    modes = _parse_json_field(modes)
    if isinstance(modes, dict):
        if not modes:
            return "{}"
        return ", ".join(f"{key}:{'on' if bool(val) else 'off'}" for key, val in sorted(modes.items()))
    return str(modes) if modes is not None else "—"


def _format_weekdays_list(values) -> str:
    if not values:
        return "—"
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    try:
        return ", ".join(names[int(v) % 7] for v in values)
    except Exception:
        return ", ".join(str(v) for v in values)


def _shorten_address(address: str | None) -> str:
    if not address:
        return "—"
    if len(address) <= 12:
        return address
    return f"{address[:6]}…{address[-4:]}"


def _format_money_from_cents(cents) -> str:
    if cents in (None, "", 0):
        return "N/A"
    try:
        dollars = Decimal(cents) / Decimal(100)
    except (InvalidOperation, ValueError, TypeError):
        return str(cents)
    return _format_money(dollars)


def _parse_json_field(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _render_report_page(
    raw_address: str,
    chain: str,
    token_record,
    watchers: Sequence[dict[str, object]],
    call_stats: dict[str, object],
    call_rows: Sequence[dict[str, object]],
    page: int = 1,
) -> tuple[str, InlineKeyboardMarkup | None]:
    """Render a specific page of the inspector report with navigation"""

    # Page 1: Overview + Tracking
    if page == 1:
        sections = [
            "<b>🔍 Token Overview</b>",
            _build_overview_section(raw_address, chain, token_record),
            "\n<b>📈 Tracking Snapshot</b>",
            _build_tracking_section(token_record),
        ]
        text = "\n".join(filter(None, sections))

    # Page 2: Monitored Sources
    elif page == 2:
        text = "<b>👀 Monitored Sources</b>\n" + _build_watchers_section(watchers)

    # Page 3: Sources & Targets
    elif page == 3:
        text = "<b>📍 Sources & Targets</b>\n" + _build_sources_targets_summary(call_rows)

    # Page 4: Call Activity
    elif page == 4:
        text = "<b>☎️ Call Activity</b>\n" + _build_calls_section(call_stats, call_rows)
    else:
        text = "Invalid page"

    # Build navigation keyboard
    keyboard = _build_navigation_keyboard(raw_address, page, total_pages=4)

    return text, keyboard


def _build_navigation_keyboard(address: str, current_page: int, total_pages: int) -> InlineKeyboardMarkup | None:
    """Build pagination keyboard"""
    if total_pages <= 1:
        return None

    # Page emoji indicators
    page_emojis = {
        1: "📊",  # Overview
        2: "👀",  # Monitored Sources
        3: "📍",  # Sources & Targets
        4: "☎️",  # Call Activity
    }

    buttons = []
    row = []

    # Previous button
    if current_page > 1:
        row.append(InlineKeyboardButton(
            text="◀️ Prev",
            callback_data=InspectorPageCallback(address=address, page=current_page - 1).pack()
        ))

    # Page indicator
    current_emoji = page_emojis.get(current_page, "📄")
    row.append(InlineKeyboardButton(
        text=f"{current_emoji} {current_page}/{total_pages}",
        callback_data="noop"
    ))

    # Next button
    if current_page < total_pages:
        row.append(InlineKeyboardButton(
            text="Next ▶️",
            callback_data=InspectorPageCallback(address=address, page=current_page + 1).pack()
        ))

    buttons.append(row)

    # Quick nav row with emojis
    quick_nav = []
    for p in range(1, total_pages + 1):
        emoji = page_emojis.get(p, "📄")
        if p == current_page:
            quick_nav.append(InlineKeyboardButton(text=f"• {emoji} •", callback_data="noop"))
        else:
            quick_nav.append(InlineKeyboardButton(
                text=emoji,
                callback_data=InspectorPageCallback(address=address, page=p).pack()
            ))
    buttons.append(quick_nav)

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_overview_section(raw_address: str, chain: str, token_record) -> str:
    lines = [
        _fmt_line("Chain", chain),
        _fmt_line("Address", f"<code>{html.escape(raw_address)}</code>", is_raw=True),
    ]

    if token_record:
        lines.append(_fmt_line("Status", token_record.get("status")))
        stop_reason = token_record.get("stop_reason")
        if stop_reason:
            lines.append(_fmt_line("Stop Reason", stop_reason))

        ticker = token_record.get("ticker")
        if ticker:
            lines.append(_fmt_line("Ticker", ticker))

        lines.append(_fmt_line("First Seen", _format_time(token_record.get("first_seen_at"))))
        lines.append(_fmt_line("Last Checked", _format_time(token_record.get("last_checked_at"))))
        lines.append(_fmt_line("Next Poll", _format_time(token_record.get("next_poll_at"))))
        lines.append(_fmt_line("Current Tier", token_record.get("current_tier")))

        # Add last hit multiplier if available
        last_hit = token_record.get("last_hit_multiplier")
        if last_hit and last_hit > 1:
            lines.append(_fmt_line("Last Hit Multiplier", f"{float(last_hit):.0f}x"))

        lines.append(_fmt_line("Dex Refresh", _format_time(token_record.get("dex_screener_refreshed_at"))))
        orig_msg = token_record.get("original_message_id")
        if orig_msg:
            lines.append(_fmt_line("Original Msg", str(orig_msg)))

    return "\n".join(filter(None, lines))


def _build_tracking_section(token_record) -> str:
    if not token_record:
        return "Not tracked yet."

    name = token_record.get("ticker") or token_record.get("address") or "Token"

    first_mc = _format_money(token_record.get("first_seen_mc"))
    last_mc = _format_money(token_record.get("last_mc"))
    last_alert_mc = _format_money(token_record.get("last_alert_mc"))
    peak_mc = _format_money(token_record.get("peak_mc"))
    tier = token_record.get("current_tier") or "Unknown"
    next_poll = _format_time(token_record.get("next_poll_at"), clock_only=True)
    refreshed = _format_time(token_record.get("dex_screener_refreshed_at"), clock_only=True)
    last_alert_at = _format_time(token_record.get("last_alert_at"), clock_only=True)

    multiplier = None
    try:
        first_val = float(token_record.get("first_seen_mc") or 0)
        last_val = float(token_record.get("last_mc") or 0)
        if first_val > 0 and last_val > 0:
            multiplier = last_val / first_val
    except (TypeError, ValueError):
        multiplier = None

    branches: list[tuple[str, str | None]] = [
        ("Tier", tier),
        ("Next Poll", next_poll),
        ("First MC", first_mc),
        ("Last MC", last_mc),
        ("Last Alert", last_alert_mc),
        ("Peak MC", peak_mc),
        ("Last Alert Time", last_alert_at),
        ("Refreshed", refreshed),
    ]

    if multiplier:
        branches.append(("Gain vs First", f"{multiplier:.2f}x"))

    return _render_tree(name, branches)


def _build_watchers_section(watchers: Sequence[dict[str, object]]) -> str:
    if not watchers:
        return "No monitored sources."

    lines = [f"{len(watchers)} linked source(s):"]
    for row in watchers[:12]:
        raw_name = row.get("display_name") or row.get("button_text") or f"Chat {row.get('chat_id')}"
        status = "✅" if row.get("is_enabled", True) else "⛔"
        chat_id = row.get("chat_id")

        title = f"{status} {html.escape(str(raw_name))} (<code>{html.escape(str(chat_id))}</code>)"

        branches: list[tuple[str, str | None]] = [
            ("Tier Gain", _format_gain_pct(row.get("sensitivity_pct"))),
            ("Delivery", _format_delivery(row)),
            ("Chart", _format_chart(row)),
            ("First MC", _format_money(row.get("first_seen_mc"))),
            ("Last Alert", _format_money(row.get("last_alert_mc"))),
            ("Created", _format_time(row.get("created_at"))),
        ]

        if row.get("template_text"):
            branches.append(("Template", "custom"))

        # Add last guardrail result if available
        guardrail_result = row.get("last_guardrail_result")
        if guardrail_result and isinstance(guardrail_result, dict):
            passed = guardrail_result.get("passed", False)
            checks_passed = guardrail_result.get("checks_passed", 0)
            total_checks = guardrail_result.get("total_checks", 0)
            status_emoji = "✅" if passed else "🔴"
            branches.append(("Last Guard", f"{status_emoji} {checks_passed}/{total_checks} passed"))

        origin_meta = []
        if row.get("original_message_id"):
            origin_meta.append(f"msg {row['original_message_id']}")
        if row.get("original_user_id"):
            origin_meta.append(f"user {row['original_user_id']}")

        if origin_meta:
            branches.append(("Origin", "; ".join(origin_meta)))

        # Build Last Post line separately to avoid HTML escaping in _render_tree
        if row.get("posted_message_id"):
            posted_target = row.get('posted_target')
            posted_msg_id = row.get('posted_message_id')
            msg_link = _format_telegram_link(posted_target, posted_msg_id)

            if msg_link:
                posted_desc = f"{posted_target} {msg_link}"
            else:
                posted_desc = f"{posted_target} #{posted_msg_id}"

            if row.get("posted_at"):
                posted_desc += f" ({_format_time(row.get('posted_at'), include_exact=True)})"
            if row.get("posted_source"):
                posted_desc += f" via {row['posted_source']}"
            branches.append(("Last Post", posted_desc, True))  # Mark as HTML-safe

        tree = _render_tree(title, branches, title_safe=True)
        if tree:
            lines.append(tree)

    if len(watchers) > 12:
        lines.append("…and more")

    return "\n".join(lines)


def _build_sources_targets_summary(call_rows: Sequence[dict[str, object]]) -> str:
    """Build a summary of unique sources and targets from call history."""
    if not call_rows:
        return "No call history yet."

    # Aggregate unique sources with counts
    sources = {}  # {chat_id: (name, count, sample_msg_id)}
    for row in call_rows:
        source_id = row.get("source_chat_id")
        source_name = row.get("source_name") or f"Chat {source_id}"
        source_msg = row.get("forwarded_message_id")
        if source_id:
            if source_id not in sources:
                sources[source_id] = [source_name, 0, source_msg]
            sources[source_id][1] += 1

    # Aggregate unique targets with counts
    targets = {}  # {chat_id: (name, count, sample_msg_ids)}
    for row in call_rows:
        target_id = row.get("target_chat_id")
        target_name = row.get("target_name") or f"Chat {target_id}"
        target_msg = row.get("forwarded_message_id")
        if target_id:
            if target_id not in targets:
                targets[target_id] = [target_name, 0, []]
            targets[target_id][1] += 1
            if target_msg and target_msg not in targets[target_id][2] and len(targets[target_id][2]) < 2:
                targets[target_id][2].append(target_msg)

    lines = []

    # Sources section
    if sources:
        lines.append(f"<b>📍 Posted in {len(sources)} source(s):</b>")
        for source_id, (source_name, count, msg_id) in list(sources.items())[:8]:
            msg_link = _format_telegram_link(source_id, msg_id)
            count_str = f" ({count}x)" if count > 1 else ""
            if msg_link:
                lines.append(f"  • {html.escape(source_name)}{count_str} → {msg_link}")
            else:
                lines.append(f"  • {html.escape(source_name)}{count_str}")

        if len(sources) > 8:
            lines.append(f"  <i>... and {len(sources) - 8} more</i>")

    # Targets section
    if targets:
        if lines:
            lines.append("")
        lines.append(f"<b>🎯 Forwarded to {len(targets)} target(s):</b>")
        for target_id, (target_name, count, msg_ids) in list(targets.items())[:8]:
            # Get ALL message IDs for this target, not just first 2
            all_msg_ids = []
            for row in call_rows:
                if row.get("target_chat_id") == target_id:
                    msg = row.get("forwarded_message_id")
                    if msg and msg not in all_msg_ids:
                        all_msg_ids.append(msg)

            msg_links = [_format_telegram_link(target_id, mid) for mid in all_msg_ids]
            msg_links_str = " ".join(filter(None, msg_links))
            count_str = f" ({count}x)" if count > 1 else ""
            lines.append(f"  • {html.escape(target_name)}{count_str} → {msg_links_str}")

        if len(targets) > 8:
            lines.append(f"  <i>... and {len(targets) - 8} more</i>")

    return "\n".join(lines) if lines else "No sources or targets found."


def _build_calls_section(call_stats: dict[str, object], call_rows: Sequence[dict[str, object]]) -> str:
    total = call_stats.get("total") or 0
    lines = [
        _fmt_line("Total Calls", str(total)),
        _fmt_line("Last 24h", str(call_stats.get("last_24h") or 0)),
        _fmt_line("Last 7d", str(call_stats.get("last_7d") or 0)),
        _fmt_line("First Call", _format_time(call_stats.get("first_call"))),
        _fmt_line("Most Recent", _format_time(call_stats.get("last_call"))),
        "",
        "<b>Recent Calls:</b>"
    ]

    logs: list[str] = []
    # Limit to first 10 calls for cleaner display
    for row in list(call_rows)[:10]:
        timestamp = _format_time(row.get("called_at"))
        target_id = row.get("target_chat_id")
        target_name = row.get("target_name") or f"Chat {target_id}"
        source_id = row.get("source_chat_id")
        source_name = row.get("source_name")
        mc = _format_money(row.get("market_cap_at_call"))
        caller = row.get("caller_name") or row.get("caller_user_id")
        forward_msg = row.get("forwarded_message_id")

        # Format source display
        source_display = source_name or f"Chat {source_id}" if source_id else "Unknown"

        # Format target with link
        target_msg_link = _format_telegram_link(target_id, forward_msg)

        # Build cleaner log entry
        # Format: • time | Source → Target | link
        parts = [f"<b>{html.escape(timestamp)}</b>"]
        parts.append(f"{html.escape(source_display)[:30]}")
        parts.append("→")
        parts.append(f"{html.escape(target_name)[:30]}")

        # Add metadata
        meta = []
        if mc and mc != "N/A":
            meta.append(html.escape(mc))
        if caller:
            caller_str = str(caller)[:20]
            meta.append(html.escape(caller_str))

        if meta:
            parts.append(f"({', '.join(meta)})")

        # Add message link
        if target_msg_link:
            parts.append(target_msg_link)

        logs.append("• " + " ".join(parts))

    if not logs:
        logs.append("No calls logged yet.")
    elif len(call_rows) > 10:
        logs.append(f"\n<i>... and {len(call_rows) - 10} more calls</i>")

    return "\n".join(filter(None, lines + logs))


def _format_telegram_link(chat_id: int | None, message_id: int | None) -> str | None:
    """Format a Telegram message link for private/public groups.

    Args:
        chat_id: Telegram chat ID (e.g., -1001234567890)
        message_id: Message ID in that chat

    Returns:
        HTML link like <a href="https://t.me/c/1234567890/123">#123</a>
        or None if inputs are invalid
    """
    if not chat_id or not message_id:
        return None

    try:
        chat_id_int = int(chat_id)
        message_id_int = int(message_id)

        # Convert -1001234567890 to 1234567890
        if chat_id_int < 0:
            # Remove -100 prefix for supergroups
            chat_id_str = str(abs(chat_id_int))
            if chat_id_str.startswith("100"):
                chat_id_str = chat_id_str[3:]
            url = f"https://t.me/c/{chat_id_str}/{message_id_int}"
        else:
            # Public channel or regular chat
            url = f"https://t.me/c/{chat_id_int}/{message_id_int}"

        return f'<a href="{url}">#{message_id_int}</a>'
    except (ValueError, TypeError):
        return None


def _build_chat_url(chat_id: Any) -> str | None:
    try:
        chat_int = int(chat_id)
    except (TypeError, ValueError):
        return None

    if chat_int < 0:
        chat_str = str(abs(chat_int))
        if chat_str.startswith("100"):
            chat_str = chat_str[3:]
        return f"https://t.me/c/{chat_str}"

    return None


def _format_money(value) -> str:
    if value in (None, "N/A"):
        return "N/A"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)

    abs_val = abs(num)
    if abs_val >= 1_000_000_000:
        return f"${num / 1_000_000_000:.2f}B"
    if abs_val >= 1_000_000:
        return f"${num / 1_000_000:.2f}M"
    if abs_val >= 1_000:
        return f"${num / 1_000:.2f}K"
    return f"${num:,.2f}"


def _format_time(value, *, include_exact: bool = False, clock_only: bool = False) -> str:
    if not value:
        return "N/A"

    try:
        dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except Exception:  # pragma: no cover - defensive formatting
        return str(value)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    delta = now - dt

    if clock_only:
        return dt.strftime("%H:%M:%S UTC")

    if delta.total_seconds() < 0:
        rel = "in the future"
    else:
        days = delta.days
        hours = int(delta.seconds / 3600)
        minutes = int((delta.seconds % 3600) / 60)
        if days > 0:
            rel = f"{days}d {hours}h ago"
        elif hours > 0:
            rel = f"{hours}h {minutes}m ago"
        elif minutes > 0:
            rel = f"{minutes}m ago"
        else:
            rel = "just now"

    if include_exact:
        return f"{dt.isoformat()} ({rel})"
    return rel


def _render_tree(title: str, branches: Iterable[tuple[str, str | None] | tuple[str, str | None, bool]], *, title_safe: bool = False) -> str:
    rows = []
    for item in branches:
        # Handle both 2-tuple and 3-tuple formats
        if len(item) == 3:
            label, value, is_html_safe = item
        else:
            label, value = item
            is_html_safe = False

        if value in (None, "", "N/A"):
            continue

        safe_label = html.escape(str(label))
        # Only escape if not marked as HTML-safe
        safe_value = str(value) if is_html_safe else html.escape(str(value))
        rows.append((safe_label, safe_value))

    if not rows:
        return title if title_safe else html.escape(title)

    header = title if title_safe else html.escape(title)
    body_lines = []
    last_index = len(rows) - 1
    for idx, (label, value) in enumerate(rows):
        connector = "└" if idx == last_index else "├"
        body_lines.append(f"  {connector} {label}: {value}")

    return "\n".join([header, *body_lines])


def _format_gain_pct(value) -> str | None:
    if value is None:
        return None
    try:
        pct = float(value) * 100
        return f"{pct:.0f}%"
    except (TypeError, ValueError):
        return None


def _format_delivery(row: dict[str, object]) -> str:
    if row.get("use_management_bot"):
        return "Management bot"
    if row.get("assigned_userbot_id"):
        return f"Userbot {row['assigned_userbot_id']}"
    return "Pooled userbot"


def _format_chart(row: dict[str, object]) -> str | None:
    if not row.get("chart_enabled"):
        return None

    bits = ["Enabled"]
    if row.get("chart_bot_id"):
        bits.append(f"bot {row['chart_bot_id']}")
    if row.get("chart_mc_threshold"):
        bits.append(f"≥ {_format_money(row['chart_mc_threshold'])}")

    # Check if guardrails are overridden
    guardrail_overrides = []
    if row.get("chart_min_age_minutes") is not None:
        guardrail_overrides.append("age")
    if row.get("chart_min_liquidity_usd") is not None:
        guardrail_overrides.append("liq")
    if row.get("chart_min_volume_usd") is not None:
        guardrail_overrides.append("vol")
    if row.get("chart_min_multiplier") is not None:
        guardrail_overrides.append("mult")
    if row.get("chart_max_price_change_pct") is not None:
        guardrail_overrides.append("stab")
    if row.get("chart_checks_required") is not None:
        guardrail_overrides.append("checks")

    if guardrail_overrides:
        bits.append(f"overrides({','.join(guardrail_overrides)})")

    return " ".join(bits)


def _fmt_line(label: str, value: str | None, *, is_raw: bool = False) -> str | None:
    if value in (None, ""):
        return None
    safe = value if is_raw else html.escape(str(value))
    return f"<b>{label}:</b> {safe}"
