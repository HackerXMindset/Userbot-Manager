"""
Settings Handler - Manages gain alert threshold configuration
"""

import logging
import html

from aiogram import types
from aiogram.fsm.context import FSMContext

from app.ui.keyboards import Keyboards
from app.config import (
    get_gain_alert_settings,
    get_gain_alert_template_text,
    set_gain_alert_template_text,
)
from app.gain_alert_templates import (
    DEFAULT_GAIN_ALERT_TEMPLATE,
    missing_required_placeholders,
    normalise_template,
    REQUIRED_GAIN_TEMPLATE_PLACEHOLDERS,
)
from app.db import db

logger = logging.getLogger(__name__)


class SettingsHandler:
    """Handler for system settings"""

    def __init__(self, db_pool, keyboards: Keyboards):
        self.db = db_pool
        self.keyboards = keyboards

    def _compose_gain_alert_settings_text(
        self,
        gain_threshold: float,
        drop_threshold: float,
        drop_floor: float,
        template_text: str,
    ) -> str:
        """Render the gain alert settings summary block."""
        template_preview = html.escape(template_text)
        return (
            "<b>🌙 Gain Alert Settings</b>\n\n"
            "Configure market cap monitoring thresholds:\n\n"
            f"<b>📈 Gain Threshold:</b> {gain_threshold*100:.0f}%\n"
            f"  └ Alert when MC rises {gain_threshold*100:.0f}% above last alert\n\n"
            f"<b>📉 Drop Threshold:</b> {drop_threshold*100:.0f}%\n"
            f"  └ Stop monitoring when MC drops to {drop_threshold*100:.0f}% of first seen\n\n"
            f"<b>💰 Minimum Market Cap:</b> ${drop_floor:,.0f}\n"
            f"  └ Stop monitoring when MC falls below this absolute floor\n\n"
            "<i>Tap a setting to edit it.</i>\n\n"
            "<b>Current Alert Template</b>\n"
            f"<code>{template_preview}</code>"
        )

    async def show_settings_menu(self, query: types.CallbackQuery):
        """Show main settings menu"""
        try:
            await query.message.edit_text(
                "<b>⚙️ System Settings</b>\n\n"
                "Manage gain alert sources, global thresholds, and scheduler diagnostics.",
                reply_markup=self.keyboards.settings_menu()
            )
            await query.answer()
        except Exception as e:
            logger.error(f"Error showing settings menu: {e}")
            await query.answer("❌ Error loading settings", show_alert=True)

    async def show_gain_alert_settings(self, query: types.CallbackQuery):
        """Show gain alert threshold settings"""
        try:
            # Load current settings
            settings_dict = await get_gain_alert_settings()
            gain_threshold = settings_dict['gain_threshold_pct']
            drop_threshold = settings_dict['drop_threshold_pct']
            drop_floor = settings_dict['drop_floor_mc']

            global_template = await get_gain_alert_template_text()
            text = self._compose_gain_alert_settings_text(
                gain_threshold,
                drop_threshold,
                drop_floor,
                global_template,
            )

            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.gain_alert_settings_menu(
                    gain_threshold, drop_threshold, drop_floor
                )
            )
            await query.answer()
        except Exception as e:
            logger.error(f"Error showing gain alert settings: {e}")
            await query.answer("❌ Error loading gain alert settings", show_alert=True)

    async def prompt_edit_gain_threshold(self, query: types.CallbackQuery, state: FSMContext):
        """Prompt user to enter new gain threshold percentage"""
        try:
            settings_dict = await get_gain_alert_settings()
            current = settings_dict['gain_threshold_pct'] * 100

            await query.message.edit_text(
                f"<b>📈 Edit Gain Threshold</b>\n\n"
                f"Current: {current:.0f}%\n\n"
                f"Enter new gain threshold percentage (e.g., 30 for 30%):\n\n"
                f"<i>This determines when alerts fire. A 30% threshold means an alert "
                f"will be sent when the market cap rises 30% above the last alert level.</i>",
                reply_markup=self.keyboards.cancel_button("settings:gain_alerts")
            )
            await state.set_state("awaiting_gain_threshold")
            await query.answer()
        except Exception as e:
            logger.error(f"Error prompting gain threshold edit: {e}")
            await query.answer("❌ Error", show_alert=True)

    async def prompt_edit_drop_threshold(self, query: types.CallbackQuery, state: FSMContext):
        """Prompt user to enter new drop threshold percentage"""
        try:
            settings_dict = await get_gain_alert_settings()
            current = settings_dict['drop_threshold_pct'] * 100

            await query.message.edit_text(
                f"<b>📉 Edit Drop Threshold</b>\n\n"
                f"Current: {current:.0f}%\n\n"
                f"Enter new drop threshold percentage (e.g., 70 for 70%):\n\n"
                f"<i>Monitoring stops when MC drops to this percentage of the initial market cap. "
                f"A 70% threshold means monitoring stops when MC falls to 70% of the first seen value.</i>",
                reply_markup=self.keyboards.cancel_button("settings:gain_alerts")
            )
            await state.set_state("awaiting_drop_threshold")
            await query.answer()
        except Exception as e:
            logger.error(f"Error prompting drop threshold edit: {e}")
            await query.answer("❌ Error", show_alert=True)

    async def prompt_edit_drop_floor(self, query: types.CallbackQuery, state: FSMContext):
        """Prompt user to enter new minimum market cap floor"""
        try:
            settings_dict = await get_gain_alert_settings()
            current = settings_dict['drop_floor_mc']

            await query.message.edit_text(
                f"<b>💰 Edit Minimum Market Cap</b>\n\n"
                f"Current: ${current:,.0f}\n\n"
                f"Enter new minimum market cap (e.g., 8000 for $8,000):\n\n"
                f"<i>Monitoring stops when MC falls below this absolute value, "
                f"regardless of percentage thresholds.</i>",
                reply_markup=self.keyboards.cancel_button("settings:gain_alerts")
            )
            await state.set_state("awaiting_drop_floor")
            await query.answer()
        except Exception as e:
            logger.error(f"Error prompting drop floor edit: {e}")
            await query.answer("❌ Error", show_alert=True)

    async def prompt_edit_gain_template(self, query: types.CallbackQuery, state: FSMContext):
        """Prompt user to update the global gain alert template."""
        try:
            template = await get_gain_alert_template_text()
            placeholder_list = ", ".join([
                "{gain_emoji}",
                "{token_symbol}",
                "{multiplier}",
                "{first_market_cap}",
                "{current_market_cap}",
                "{elapsed_time}",
                "{address}",
            ])
            preview = html.escape(template)

            await query.message.edit_text(
                "<b>📝 Edit Global Gain Alert Template</b>\n\n"
                "Available placeholders:\n"
                f"<code>{placeholder_list}</code>\n\n"
                "<i>Placeholders are optional—use any combination or none at all.</i>\n\n"
                "Send the new template text exactly as it should appear.\n"
                "Type <code>reset</code> to restore the default template.\n\n"
                "<b>Current template:</b>\n"
                f"<code>{preview}</code>",
                reply_markup=self.keyboards.cancel_button("settings:gain_alerts"),
                parse_mode="HTML",
            )
            await state.set_state("awaiting_gain_template")
            await query.answer()
        except Exception as exc:
            logger.error(f"Error prompting global template edit: {exc}")
            await query.answer("❌ Error", show_alert=True)

    async def save_gain_threshold(self, message: types.Message, state: FSMContext):
        """Save new gain threshold value"""
        try:
            value = float(message.text.strip())

            if value <= 0 or value > 1000:
                await message.answer("❌ Invalid value. Please enter a percentage between 1 and 1000.")
                return

            # Convert percentage to decimal
            decimal_value = value / 100.0

            # Update settings table
            await self.db.execute(
                "UPDATE settings SET value = $1 WHERE key = 'gain_threshold_pct'",
                str(decimal_value)
            )

            await message.answer(
                f"✅ Gain threshold updated to {value:.0f}%\n\n"
                f"Alerts will now fire when tokens gain {value:.0f}% from their last alert level."
            )

            await state.clear()

            # Show updated settings menu
            settings_dict = await get_gain_alert_settings()
            gain_threshold = settings_dict['gain_threshold_pct']
            drop_threshold = settings_dict['drop_threshold_pct']
            drop_floor = settings_dict['drop_floor_mc']

            global_template = await get_gain_alert_template_text()
            text = self._compose_gain_alert_settings_text(
                gain_threshold,
                drop_threshold,
                drop_floor,
                global_template,
            )

            await message.answer(
                text,
                reply_markup=self.keyboards.gain_alert_settings_menu(
                    gain_threshold, drop_threshold, drop_floor
                )
            )

        except ValueError:
            await message.answer("❌ Invalid input. Please enter a valid number.")
        except Exception as e:
            logger.error(f"Error saving gain threshold: {e}")
            await message.answer("❌ Error saving setting")

    async def save_drop_threshold(self, message: types.Message, state: FSMContext):
        """Save new drop threshold value"""
        try:
            value = float(message.text.strip())

            if value <= 0 or value > 100:
                await message.answer("❌ Invalid value. Please enter a percentage between 1 and 100.")
                return

            # Convert percentage to decimal
            decimal_value = value / 100.0

            # Update settings table
            await self.db.execute(
                "UPDATE settings SET value = $1 WHERE key = 'drop_threshold_pct'",
                str(decimal_value)
            )

            await message.answer(
                f"✅ Drop threshold updated to {value:.0f}%\n\n"
                f"Monitoring will stop when tokens drop to {value:.0f}% of their initial market cap."
            )

            await state.clear()

            # Show updated settings menu
            settings_dict = await get_gain_alert_settings()
            gain_threshold = settings_dict['gain_threshold_pct']
            drop_threshold = settings_dict['drop_threshold_pct']
            drop_floor = settings_dict['drop_floor_mc']

            global_template = await get_gain_alert_template_text()
            text = self._compose_gain_alert_settings_text(
                gain_threshold,
                drop_threshold,
                drop_floor,
                global_template,
            )

            await message.answer(
                text,
                reply_markup=self.keyboards.gain_alert_settings_menu(
                    gain_threshold, drop_threshold, drop_floor
                )
            )

        except ValueError:
            await message.answer("❌ Invalid input. Please enter a valid number.")
        except Exception as e:
            logger.error(f"Error saving drop threshold: {e}")
            await message.answer("❌ Error saving setting")

    async def save_drop_floor(self, message: types.Message, state: FSMContext):
        """Save new minimum market cap floor"""
        try:
            value = float(message.text.strip().replace(',', '').replace('$', ''))

            if value < 0 or value > 1_000_000_000:
                await message.answer("❌ Invalid value. Please enter a market cap between 0 and 1,000,000,000.")
                return

            # Update settings table
            await self.db.execute(
                "UPDATE settings SET value = $1 WHERE key = 'drop_floor_mc'",
                str(value)
            )

            await message.answer(
                f"✅ Minimum market cap updated to ${value:,.0f}\n\n"
                f"Monitoring will stop when tokens fall below ${value:,.0f}."
            )

            await state.clear()

            # Show updated settings menu
            settings_dict = await get_gain_alert_settings()
            gain_threshold = settings_dict['gain_threshold_pct']
            drop_threshold = settings_dict['drop_threshold_pct']
            drop_floor = settings_dict['drop_floor_mc']

            global_template = await get_gain_alert_template_text()
            text = self._compose_gain_alert_settings_text(
                gain_threshold,
                drop_threshold,
                drop_floor,
                global_template,
            )

            await message.answer(
                text,
                reply_markup=self.keyboards.gain_alert_settings_menu(
                    gain_threshold, drop_threshold, drop_floor
                )
            )

        except ValueError:
            await message.answer("❌ Invalid input. Please enter a valid number.")
        except Exception as e:
            logger.error(f"Error saving drop floor: {e}")
            await message.answer("❌ Error saving setting")

    async def save_gain_template(self, message: types.Message, state: FSMContext) -> None:
        """Persist the updated global gain alert template."""
        raw_input = message.text or ""
        stripped = raw_input.strip()

        if not stripped:
            await message.answer(
                "❌ Template cannot be empty. Include the required placeholders or type 'reset'."
            )
            return

        if stripped.lower() == "reset":
            template_to_store = DEFAULT_GAIN_ALERT_TEMPLATE
        else:
            template_to_store = normalise_template(raw_input)

        try:
            await set_gain_alert_template_text(template_to_store)
        except Exception as exc:
            logger.error(f"Error saving gain alert template: {exc}", exc_info=True)
            await message.answer("❌ Failed to save template. Please try again.")
            return

        await state.clear()
        preview = html.escape(template_to_store)
        await message.answer(
            "✅ Global gain alert template updated.\n\n"
            "Current template:\n"
            f"<code>{preview}</code>",
            parse_mode="HTML",
        )

    async def show_token_status_menu(self, query: types.CallbackQuery):
        """Show token status menu"""
        try:
            await query.message.edit_text(
                "<b>📊 Token Status & Monitoring</b>\n\n"
                "View scheduler health and token details.",
                reply_markup=self.keyboards.token_status_menu()
            )
            await query.answer()
        except Exception as e:
            logger.error(f"Error showing token status menu: {e}")
            await query.answer("❌ Error", show_alert=True)

    async def show_scheduler_overview(self, query: types.CallbackQuery):
        """Show scheduler overview with tier breakdown"""
        try:
            from app.dex import get_dex_service

            dex_service = get_dex_service()
            stats = await dex_service.get_service_stats()

            # Get tier breakdown
            tier_counts = await self.db.fetch("""
                SELECT current_tier, COUNT(*) as count
                FROM tokens_tracked
                WHERE status = 'active' AND current_tier IS NOT NULL
                GROUP BY current_tier
                ORDER BY current_tier
            """)

            stopped_count = await self.db.fetchval(
                "SELECT COUNT(*) FROM tokens_tracked WHERE status = 'stopped'"
            )

            tier_map = {
                'tier_a': ('Tier A (10s)', 0),
                'tier_b': ('Tier B (30s)', 0),
                'tier_c': ('Tier C (3m)', 0),
                'tier_d': ('Tier D (5m)', 0),
                'tier_e': ('Tier E (10m)', 0),
                'tier_f': ('Tier F (30m)', 0),
            }

            for row in tier_counts:
                tier = row['current_tier']
                if tier in tier_map:
                    tier_map[tier] = (tier_map[tier][0], row['count'])

            text = (
                "<b>📊 DexScreener Scheduler Status</b>\n\n"
                f"🔄 <b>Scheduler Active:</b> {'✅ Yes' if stats['scheduler_active'] else '❌ No'}\n"
                f"📦 <b>Tokens in Queue:</b> {stats['tokens_in_queue']}\n"
                f"⚙️ <b>Service Running:</b> {'✅ Yes' if stats['running'] else '❌ No'}\n\n"
                "<b>📈 By Tier:</b>\n"
            )

            for tier_name, count in tier_map.values():
                text += f"  ├ {tier_name}: {count} tokens\n"

            text += f"\n⛔ <b>Stopped:</b> {stopped_count or 0} tokens"

            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.back_button("settings:token_status")
            )
            await query.answer()

        except Exception as e:
            logger.error(f"Error showing scheduler overview: {e}")
            await query.answer("❌ Error loading scheduler stats", show_alert=True)

    async def show_tokens_list(self, query: types.CallbackQuery, status: str, page: int = 1):
        """Show paginated list of tokens with details"""
        try:
            items_per_page = 5
            offset = (page - 1) * items_per_page

            # Get tokens with pagination
            tokens = await self.db.fetch(f"""
                SELECT
                    address, ticker, current_tier, next_poll_at,
                    first_seen_mc, last_mc, last_alert_mc,
                    dex_screener_refreshed_at, stop_reason,
                    first_seen_at
                FROM tokens_tracked
                WHERE status = $1
                ORDER BY
                    CASE WHEN status = 'active' THEN next_poll_at ELSE first_seen_at END DESC
                LIMIT $2 OFFSET $3
            """, status, items_per_page, offset)

            total_count = await self.db.fetchval(
                "SELECT COUNT(*) FROM tokens_tracked WHERE status = $1", status
            )

            total_pages = max(1, (total_count + items_per_page - 1) // items_per_page)

            if status == 'active':
                title = f"🪙 Active Tokens (Page {page}/{total_pages})"
            else:
                title = f"⛔ Stopped Tokens (Page {page}/{total_pages})"

            text = f"<b>{title}</b>\n\n"

            if not tokens:
                text += "<i>No tokens found.</i>"
            else:
                for token in tokens:
                    ticker = token['ticker'] or token['address'][:8]
                    text += f"<b>{ticker}</b>\n"

                    if status == 'active':
                        tier = token['current_tier'] or 'N/A'
                        next_poll = token['next_poll_at']

                        # Format tier display
                        tier_display = tier.replace('tier_', 'Tier ').upper() if tier != 'N/A' else 'N/A'

                        text += f"  ├ <b>Tier:</b> {tier_display}\n"

                        if next_poll:
                            text += f"  ├ <b>Next Poll:</b> {next_poll.strftime('%H:%M:%S UTC')}\n"

                        if token['first_seen_mc']:
                            text += f"  ├ <b>First MC:</b> {self._format_mc_short(token['first_seen_mc'])}\n"

                        if token['last_mc']:
                            text += f"  ├ <b>Last MC:</b> {self._format_mc_short(token['last_mc'])}\n"

                        if token['last_alert_mc'] and token['last_alert_mc'] > 0:
                            text += f"  ├ <b>Last Alert:</b> {self._format_mc_short(token['last_alert_mc'])}\n"

                        if token['dex_screener_refreshed_at']:
                            text += f"  └ <b>Refreshed:</b> {token['dex_screener_refreshed_at'].strftime('%H:%M:%S UTC')}\n"
                    else:
                        # Stopped token
                        stop_reason = token['stop_reason'] or 'Unknown'
                        reason_display = {
                            'mc_drop_70': '📉 Dropped below 70%',
                            'mc_below_floor': '💰 Below minimum MC',
                        }.get(stop_reason, stop_reason)

                        text += f"  ├ <b>Reason:</b> {reason_display}\n"

                        if token['first_seen_mc']:
                            text += f"  ├ <b>First MC:</b> {self._format_mc_short(token['first_seen_mc'])}\n"

                        if token['last_mc']:
                            text += f"  └ <b>Last MC:</b> {self._format_mc_short(token['last_mc'])}\n"

                    text += "\n"

            await query.message.edit_text(
                text,
                reply_markup=self.keyboards.token_list_navigation(status, page, total_pages)
            )
            await query.answer()

        except Exception as e:
            logger.error(f"Error showing tokens list: {e}")
            await query.answer("❌ Error loading tokens", show_alert=True)

    def _format_mc_short(self, mc):
        """Format market cap in shorthand (copied from dex.py logic)"""
        if mc is None:
            return "N/A"

        value = float(mc)

        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        elif value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"${value / 1_000:.1f}K"
        else:
            return f"${value:.0f}"
