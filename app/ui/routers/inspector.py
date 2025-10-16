"""Token inspector command (/i <contract>)."""

from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone
from typing import Iterable, Sequence

from aiogram import Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters.callback_data import CallbackData

from app.models.token import TokenModel

from .context import ManagementRouterContext

logger = logging.getLogger(__name__)


class InspectorPageCallback(CallbackData, prefix="insp"):
    """Callback data for inspector pagination"""
    address: str
    page: int


def register(dispatcher: Dispatcher, context: ManagementRouterContext) -> None:
    """Register the /i inspector command for admins."""

    settings = context.settings
    db = context.db
    token_model = TokenModel(db)
    sol_pattern = re.compile(settings.solana_pattern)
    bnb_pattern = re.compile(settings.bnb_pattern, re.IGNORECASE)

    async def cmd_inspect(message: types.Message) -> None:
        if message.from_user.id not in settings.admin_telegram_ids_list:
            return

        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            await message.answer("Usage: /i <contract address>")
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

    dispatcher.message.register(
        cmd_inspect,
        Command(commands=["i"]),
        F.from_user.id.in_(settings.admin_telegram_ids_list),
    )

    dispatcher.callback_query.register(
        handle_pagination,
        InspectorPageCallback.filter(),
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
