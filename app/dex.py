"""
DexScreener Token Service with Tier-Based Scheduler

Monitors token market caps using DexScreener API with intelligent tier-based
polling intervals. Handles gain alert triggers and stop-loss conditions.
"""

import asyncio
import heapq
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from aiogram.types import BufferedInputFile

from app.config import (
    settings,
    get_gain_alert_settings,
    get_gain_alert_template_text,
    get_global_chart_settings,
)
from app.db import db
from app.models import TokenModel
from app.models.monitored_source import MonitoredSourceModel
from app.services.dexscreener_api import get_dexscreener_client
from app.services.okx_market_api import get_okx_market_client
from app.utils.tier_calculator import calculate_next_poll_time, get_poll_interval_for_tier
from app.gain_alert_templates import (
    DEFAULT_GAIN_ALERT_TEMPLATE,
    missing_required_placeholders,
)
from app.chart_fetcher import ChartFetcher

logger = logging.getLogger(__name__)

# Singleton instance for global access
_dex_service_instance: Optional["DexScreenerService"] = None

DEFAULT_CHART_THRESHOLD = Decimal("100000")


def get_dex_service() -> "DexScreenerService":
    """Return the singleton Dex service instance."""
    global _dex_service_instance
    if _dex_service_instance is None:
        _dex_service_instance = DexScreenerService()
    return _dex_service_instance


class DexScreenerService:
    """
    DexScreener integration with tier-based market cap monitoring.

    Implements a min-heap scheduler that polls tokens at different intervals
    based on their age, evaluates gain/drop conditions, and manages tier transitions.
    """

    def __init__(self) -> None:
        self.token_model = TokenModel(db)
        self.source_model = MonitoredSourceModel(db)
        self.dex_client = get_dexscreener_client()
        self.okx_client = get_okx_market_client()
        self.userbot_manager = None
        self.chart_fetcher: Optional[ChartFetcher] = None
        self.management_bot = None
        self.running = False
        self._scheduler_task: Optional[asyncio.Task] = None
        self._poll_heap: List[Tuple[datetime, int, str]] = []  # (next_poll_at, token_id, address)
        self._tokens_in_heap: set[int] = set()  # Track tokens to prevent duplicates
        self._semaphore = asyncio.Semaphore(5)  # Limit concurrent DexScreener requests

    # ==================== LIFECYCLE ====================

    def set_userbot_manager(self, manager) -> None:
        """Record the UserbotManager reference for alert dispatching."""
        self.userbot_manager = manager
        if manager:
            logger.info("UserbotManager set on Dex service")
            self.chart_fetcher = ChartFetcher(db, manager)
        else:
            logger.info("UserbotManager cleared on Dex service")
            self.chart_fetcher = None

    def set_management_bot(self, management_bot) -> None:
        """Record the management bot wrapper for alert dispatching."""
        self.management_bot = management_bot
        if management_bot:
            logger.info("Management bot set on Dex service")
        else:
            logger.info("Management bot cleared on Dex service")

    async def start(self) -> None:
        """Start the service and scheduler background task."""
        if self.running:
            return

        self.running = True

        # Start DexScreener API client
        await self.dex_client.start()
        await self.okx_client.start()

        # Load all active tokens into scheduler
        await self._load_tokens_into_scheduler()

        # Start background scheduler task
        self._scheduler_task = asyncio.create_task(self._run_scheduler())

        logger.info("Dex service started with tier-based scheduler")

    async def stop(self) -> None:
        """Stop the service and scheduler."""
        if not self.running:
            return

        self.running = False

        # Cancel scheduler task
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass

        # Stop DexScreener client
        await self.dex_client.stop()
        await self.okx_client.stop()

        logger.info("Dex service stopped")

    # ==================== SCHEDULER ====================

    async def _load_tokens_into_scheduler(self) -> None:
        """Load all active scheduled tokens from DB into heap on startup."""
        try:
            tokens = await self.token_model.get_all_active_scheduled_tokens()

            for token in tokens:
                next_poll = token.get('next_poll_at')
                token_id = token['id']
                if next_poll:
                    heapq.heappush(
                        self._poll_heap,
                        (next_poll, token_id, token['address'])
                    )
                    self._tokens_in_heap.add(token_id)

            logger.info(f"Loaded {len(tokens)} tokens into scheduler")

        except Exception as e:
            logger.error(f"Error loading tokens into scheduler: {e}", exc_info=True)

    async def _run_scheduler(self) -> None:
        """Main scheduler run loop - polls tokens based on heap."""
        logger.info("[SCHEDULER] Starting scheduler loop")

        while self.running:
            try:
                # Check if any tokens are due for polling
                now = datetime.now(timezone.utc)
                tokens_to_poll = []

                # Pop all tokens whose next_poll_at <= now
                while self._poll_heap and self._poll_heap[0][0] <= now:
                    next_poll, token_id, address = heapq.heappop(self._poll_heap)
                    self._tokens_in_heap.discard(token_id)  # Remove from tracking set
                    tokens_to_poll.append((token_id, address))

                if tokens_to_poll:
                    logger.debug(f"[SCHEDULER] Polling {len(tokens_to_poll)} token(s)")

                    # Poll tokens (with semaphore to limit concurrency)
                    tasks = [
                        self._poll_token(token_id, address)
                        for token_id, address in tokens_to_poll
                    ]
                    await asyncio.gather(*tasks, return_exceptions=True)

                # Sleep briefly before next check
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[SCHEDULER] Error in scheduler loop: {e}", exc_info=True)
                await asyncio.sleep(10)

        logger.info("[SCHEDULER] Scheduler loop stopped")

    async def _poll_token(self, token_id: int, address: str) -> None:
        """Poll a single token and update its data."""
        async with self._semaphore:
            try:
                # Fetch token from DB
                token = await db.fetchrow("SELECT * FROM tokens_tracked WHERE id = $1", token_id)

                if not token or token.get('status') != 'active':
                    logger.debug(f"[POLL] Token {address[:8]}... is no longer active, skipping")
                    return

                # Determine chain ID (Solana vs BSC) for API call
                raw_chain_id = self._determine_chain_id(token, address)
                chain_id = self._normalise_chain_id(raw_chain_id, address)

                market_cap: Optional[Decimal] = None
                ticker: Optional[str] = None

                okx_data = await self.okx_client.fetch_token_info(address, chain_id)
                if okx_data:
                    market_cap = self.okx_client.get_market_cap(okx_data)
                    ticker = self.okx_client.get_ticker(okx_data)
                    if market_cap:
                        logger.debug(
                            f"[POLL] {address[:8]}... ({chain_id}) MC from OKX: ${float(market_cap):,.2f}"
                        )

                if market_cap is None:
                    pairs = await self.dex_client.fetch_token_pairs(
                        address,
                        chain_id=chain_id,
                        use_cache=False,
                    )

                    if pairs is None:
                        pair_data = None
                    elif not pairs:
                        logger.info(
                            f"[POLL] {address[:8]}... ({chain_id}) has no DexScreener pools; stopping token."
                        )
                        await self._stop_token(token_id, address, "dex_no_pools")
                        return
                    else:
                        pair_data = self.dex_client._select_preferred_pair(pairs)

                    if pair_data:
                        market_cap = self.dex_client.get_market_cap(pair_data)
                        ticker = self.dex_client.get_ticker(pair_data)

                        if market_cap:
                            logger.debug(
                                f"[POLL] {address[:8]}... ({chain_id}) MC from DexScreener: ${float(market_cap):,.2f}"
                            )

                if market_cap and market_cap > 0:
                    # Update market cap in DB
                    await self.token_model.update_market_cap(token_id, market_cap, ticker)
                    await self.token_model.update_dex_refresh_time(token_id)

                    # Update peak MC if needed
                    peak_mc = token.get('peak_mc') or Decimal(0)
                    if market_cap > peak_mc:
                        await self.token_model.update_peak_mc(token_id, market_cap)

                    # Evaluate gain alert conditions
                    await self._evaluate_gain_alert(token, market_cap, address, ticker)

                    # Evaluate stop-loss conditions
                    should_stop, stop_reason = await self._evaluate_stop_loss(token, market_cap)
                    if should_stop:
                        await self._stop_token(token_id, address, stop_reason)
                        return  # Don't reschedule
                else:
                    logger.debug(f"[POLL] {address[:8]}... ({chain_id}) missing market cap from OKX/Dex")

                # Re-evaluate tier based on age and reschedule
                first_seen_at = token.get('first_seen_at')
                if first_seen_at:
                    tier_name, next_poll = calculate_next_poll_time(first_seen_at)

                    # Update tier in DB
                    await self.token_model.update_tier(token_id, tier_name, next_poll)

                    # Re-add to heap (only if not already scheduled)
                    if token_id not in self._tokens_in_heap:
                        heapq.heappush(self._poll_heap, (next_poll, token_id, address))
                        self._tokens_in_heap.add(token_id)

                        logger.debug(
                            f"[POLL] {address[:8]}... ({chain_id}) rescheduled to {tier_name} at {next_poll}"
                        )
                    else:
                        logger.debug(
                            f"[POLL] {address[:8]}... ({chain_id}) already in heap, skipping reschedule"
                        )

            except Exception as e:
                logger.error(f"[POLL] Error polling token {address[:8]}...: {e}", exc_info=True)

                # Reschedule with backoff on error (only if not already scheduled)
                try:
                    if token_id not in self._tokens_in_heap:
                        next_poll = datetime.now(timezone.utc) + timedelta(seconds=30)
                        heapq.heappush(self._poll_heap, (next_poll, token_id, address))
                        self._tokens_in_heap.add(token_id)
                except Exception:
                    pass

    async def _evaluate_gain_alert(self, token: Dict, current_mc: Decimal, address: str, ticker: Optional[str]) -> None:
        """
        Evaluate if token should trigger a gain alert.
        Per gain.md Phase 4: Fire alert when current_mc >= last_alert_mc * (1 + gain_threshold_pct)
        """
        try:
            token_id = token['id']
            last_alert_mc = token.get('last_alert_mc') or Decimal(0)
            first_seen_mc = token.get('first_seen_mc') or Decimal(0)
            first_seen_at = token.get('first_seen_at')

            # Get threshold from settings
            settings_dict = await get_gain_alert_settings()
            gain_threshold_pct = Decimal(str(settings_dict['gain_threshold_pct']))

            # Use first_seen_mc as baseline if no previous alert (last_alert_mc is NULL or 0)
            baseline_mc = last_alert_mc if last_alert_mc and last_alert_mc > 0 else first_seen_mc

            # Check if baseline is valid
            if not baseline_mc or baseline_mc <= 0:
                logger.debug(f"[GAIN_ALERT] Token {address[:8]}... has no valid baseline (first_seen_mc={first_seen_mc}, last_alert_mc={last_alert_mc})")
                return

            # Check if first_seen_mc is valid for multiplier calculation
            if first_seen_mc <= 0:
                logger.debug(f"[GAIN_ALERT] Token {address[:8]}... has invalid first_seen_mc={first_seen_mc}")
                return

            # Fire alert when: current_mc >= baseline_mc * (1 + gain_threshold_pct)
            threshold_mc = baseline_mc * (Decimal(1) + gain_threshold_pct)

            if current_mc >= threshold_mc:
                # Calculate multiplier = current_mc / first_seen_mc
                multiplier_value = float(current_mc / first_seen_mc)

                # Calculate elapsed time
                elapsed = self._format_elapsed_time(first_seen_at)

                ticker_display = ticker or address[:8]
                template_context = {
                    "address": address,
                    "token_symbol": ticker_display,
                    "multiplier": f"{multiplier_value:.1f}x",
                    "first_market_cap": self._format_mc_shorthand(first_seen_mc),
                    "current_market_cap": self._format_mc_shorthand(current_mc),
                    "elapsed_time": elapsed,
                    "gain_emoji": self._multiplier_to_emoji(multiplier_value),
                }

                default_preview = DEFAULT_GAIN_ALERT_TEMPLATE.format(**template_context)
                logger.info(f"[GAIN_ALERT] Token {address[:8]}... triggered: {default_preview}")

                # Dispatch alert to target groups (returns True if any deliveries succeeded)
                dispatched = await self._dispatch_gain_alert(token, template_context, address, current_mc)

                if dispatched:
                    # Post-alert bookkeeping only when at least one destination handled the alert
                    await self.token_model.update_last_alert_mc(token_id, current_mc)
                    await self.promote_to_tier_b(token_id)
                    logger.info(
                        f"[GAIN_ALERT] Token {address[:8]}... bookkeeping complete: last_alert_mc updated, promoted to Tier B"
                    )
                else:
                    logger.debug(
                        f"[GAIN_ALERT] Token {address[:8]}... had no eligible destinations; skipping bookkeeping"
                    )

        except Exception as e:
            logger.error(f"Error evaluating gain alert for {address[:8]}...: {e}", exc_info=True)

    def _format_elapsed_time(self, first_seen_at: Optional[datetime]) -> str:
        """Format elapsed time since first seen in compact units (14m, 3h, 2d)"""
        if not first_seen_at:
            return "N/A"

        from app.utils.tier_calculator import format_duration

        now = datetime.now(timezone.utc)
        if first_seen_at.tzinfo is None:
            first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)

        elapsed_seconds = int((now - first_seen_at).total_seconds())
        return format_duration(elapsed_seconds)

    def _format_mc_shorthand(self, mc: Decimal) -> str:
        """Format market cap in shorthand notation (8.5K, 1.2M, 52.7M, 1.5B)"""
        value = float(mc)

        if value >= 1_000_000_000:
            return f"${value / 1_000_000_000:.1f}B"
        elif value >= 1_000_000:
            return f"${value / 1_000_000:.1f}M"
        elif value >= 1_000:
            return f"${value / 1_000:.1f}K"
        else:
            return f"${value:.0f}"

    async def _send_via_management_bot(
        self,
        chat_id: int,
        message: str,
        reply_to_message_id: Optional[int],
        photo_bytes: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        """Send alert message using the management bot instance."""
        if not self.management_bot:
            return {"success": False, "error": "management_bot_unavailable"}

        try:
            if photo_bytes:
                input_file = BufferedInputFile(photo_bytes, filename="chart.jpg")
                sent_message = await self.management_bot.bot.send_photo(
                    chat_id=chat_id,
                    photo=input_file,
                    caption=message,
                    reply_to_message_id=reply_to_message_id,
                )
            else:
                sent_message = await self.management_bot.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_to_message_id=reply_to_message_id,
                    disable_web_page_preview=True,
                )
            return {"success": True, "message_id": getattr(sent_message, "message_id", None)}
        except Exception as exc:
            logger.error(
                f"[GAIN_ALERT] Management bot failed to send to chat {chat_id}: {exc}",
                exc_info=True,
            )
            return {"success": False, "error": str(exc)}

    def _multiplier_to_emoji(self, multiplier_value: float) -> str:
        """Return a dynamic emoji based on the gain multiplier."""
        if multiplier_value >= 100:
            return "⭐"
        if multiplier_value >= 50:
            return "💫"
        if multiplier_value >= 20:
            return "🌙"
        if multiplier_value >= 10:
            return "🚀"
        if multiplier_value >= 5:
            return "🔥"
        if multiplier_value >= 3:
            return "🌕"
        if multiplier_value >= 1.5:
            return "🎉"
        return "📈"

    async def _dispatch_gain_alert(self, token: Dict, template_values: Dict[str, str], address: str, current_mc: Decimal) -> bool:
        """
        Dispatch gain alert to target groups using configured templates.
        Sends as reply to original message if available, otherwise standalone.
        """
        try:
            token_id = token['id']

            if not self.userbot_manager:
                logger.warning(f"[GAIN_ALERT] No userbot manager set, cannot dispatch alert for {address[:8]}...")
                return False

            tracking_groups = await db.fetch(
                """
                SELECT
                    tga.chat_id,
                    tga.original_message_id,
                    tga.first_seen_mc,
                    tga.last_alert_mc,
                    tga.original_user_id,
                    ms.id AS source_id,
                    ms.is_enabled,
                    ms.sensitivity_pct,
                    ms.assigned_userbot_id,
                    ms.template_text,
                    ms.use_management_bot,
                    ms.chart_enabled,
                    ms.chart_bot_id,
                    ms.chart_mc_threshold,
                    ARRAY_REMOVE(ARRAY_AGG(mst.target_chat_id), NULL) AS extra_targets
                FROM token_group_alerts tga
                LEFT JOIN monitored_sources ms
                    ON ms.chat_id = tga.chat_id
                   AND (
                        ms.user_id = tga.original_user_id
                        OR ms.user_id IS NULL
                   )
                LEFT JOIN monitored_source_targets mst ON mst.source_id = ms.id
                WHERE tga.token_id = $1
                GROUP BY
                    tga.chat_id,
                    tga.original_message_id,
                    tga.first_seen_mc,
                    tga.last_alert_mc,
                    tga.original_user_id,
                    ms.id,
                    ms.is_enabled,
                    ms.sensitivity_pct,
                    ms.assigned_userbot_id,
                    ms.template_text,
                    ms.use_management_bot,
                    ms.chart_enabled,
                    ms.chart_bot_id,
                    ms.chart_mc_threshold
                """,
                token_id,
            )

            if not tracking_groups:
                logger.debug(f"[GROUP_ALERT_FIRE] No monitored groups for token {address[:8]}..., skipping")
                return False

            settings_dict = await get_gain_alert_settings()
            default_gain_threshold_pct = Decimal(str(settings_dict['gain_threshold_pct']))
            global_template = await get_gain_alert_template_text()
            chart_config = await get_global_chart_settings()
            chart_threshold_override = chart_config.get('chart_threshold_override')
            chart_threshold_default = chart_config['chart_threshold_default']
            global_chart_threshold: Decimal

            candidate_threshold = chart_threshold_override or chart_threshold_default
            if not isinstance(candidate_threshold, Decimal):
                try:
                    candidate_threshold = Decimal(str(candidate_threshold))
                except (InvalidOperation, TypeError, ValueError):
                    logger.warning(
                        "[CHART_ALERT] Invalid global chart threshold %s; falling back to %s",
                        candidate_threshold,
                        self.DEFAULT_CHART_THRESHOLD,
                    )
                    candidate_threshold = self.DEFAULT_CHART_THRESHOLD

            if candidate_threshold <= 0:
                logger.warning(
                    "[CHART_ALERT] Non-positive global chart threshold %s detected; falling back to %s",
                    candidate_threshold,
                    self.DEFAULT_CHART_THRESHOLD,
                )
                global_chart_threshold = self.DEFAULT_CHART_THRESHOLD
            else:
                global_chart_threshold = candidate_threshold

            global_chart_bot_id = chart_config.get('chart_bot_id')

            workers_cache: Dict[int, Any] = {}
            template_cache: Dict[int, Optional[str]] = {}
            any_success = False

            for group in tracking_groups:
                chat_id = group['chat_id']
                reply_to_msg_id = group['original_message_id']
                first_seen_raw = group['first_seen_mc']
                last_alert_mc = group['last_alert_mc']

                if not first_seen_raw:
                    logger.debug(f"[GROUP_ALERT_FIRE] Chat {chat_id} missing first_seen market cap, skipping")
                    continue

                try:
                    first_seen_mc = Decimal(str(first_seen_raw))
                except (ValueError, TypeError):
                    logger.debug(f"[GROUP_ALERT_FIRE] Chat {chat_id} has invalid first_seen_mc={first_seen_raw}, skipping")
                    continue
                is_enabled = group['is_enabled'] if group['is_enabled'] is not None else True

                if not is_enabled:
                    logger.debug(f"[GROUP_ALERT_FIRE] Chat {chat_id} disabled for gain alerts, skipping")
                    continue

                baseline_mc = Decimal(str(last_alert_mc)) if last_alert_mc else first_seen_mc

                if baseline_mc <= 0:
                    logger.debug(
                        f"[GROUP_ALERT_FIRE] Chat {chat_id} baseline invalid "
                        f"(first_seen={first_seen_mc}, last_alert={last_alert_mc}), skipping"
                    )
                    continue

                custom_gain_pct = group['sensitivity_pct']
                if custom_gain_pct is not None:
                    gain_threshold_pct = Decimal(str(custom_gain_pct))
                else:
                    gain_threshold_pct = default_gain_threshold_pct

                threshold_mc = baseline_mc * (Decimal(1) + gain_threshold_pct)

                if current_mc < threshold_mc:
                    continue

                use_management_bot = bool(group.get('use_management_bot')) if group.get('use_management_bot') is not None else False

                assigned_userbot_id = group['assigned_userbot_id']
                worker = None
                executor = None

                if use_management_bot:
                    if not self.management_bot:
                        logger.warning(
                            f"[GAIN_ALERT] Management bot not available for chat {chat_id}; falling back to userbot."
                        )
                        use_management_bot = False
                    else:
                        # Ensure we clear any cached worker usage
                        assigned_userbot_id = None

                if not use_management_bot:
                    if assigned_userbot_id:
                        worker = self.userbot_manager.get_worker(assigned_userbot_id)
                        if not worker:
                            logger.warning(
                                f"[GAIN_ALERT] Assigned userbot {assigned_userbot_id} unavailable for chat {chat_id}; falling back"
                            )
                    if not worker:
                        workers = self.userbot_manager.get_all_workers()
                        if not workers:
                            logger.error(f"[GAIN_ALERT] No active workers available to send alert")
                            continue
                        worker = next(iter(workers.values()))

                    worker_id = getattr(worker, 'userbot_id', None)
                    if worker_id is None:
                        logger.error("[GAIN_ALERT] Worker missing userbot_id, skipping send")
                        continue

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

                chart_enabled_flag = bool(group.get('chart_enabled')) if group.get('chart_enabled') is not None else False
                chart_bot_id_value = group.get('chart_bot_id')
                if chart_bot_id_value is None:
                    chart_bot_id_value = global_chart_bot_id

                chart_threshold_raw = group.get('chart_mc_threshold')
                chart_threshold = global_chart_threshold
                if chart_threshold_raw is not None:
                    try:
                        chart_threshold = Decimal(str(chart_threshold_raw))
                    except (InvalidOperation, ValueError, TypeError):
                        logger.warning(
                            "[CHART_ALERT] Invalid chart threshold %s for chat %s; using global %s",
                            chart_threshold_raw,
                            chat_id,
                            global_chart_threshold,
                        )
                        chart_threshold = global_chart_threshold
                elif chart_threshold is None:
                    chart_threshold = self.DEFAULT_CHART_THRESHOLD

                chart_bytes: Optional[bytes] = None
                if chart_enabled_flag and chart_bot_id_value:
                    if current_mc >= chart_threshold:
                        if self.chart_fetcher:
                            try:
                                logger.info(
                                    "[CHART_ALERT] Fetching chart for %s (chat %s, threshold=%s, current_mc=%s)",
                                    address[:8],
                                    chat_id,
                                    chart_threshold,
                                    current_mc,
                                )
                                chart_bytes = await self.chart_fetcher.fetch_chart_for_token(
                                    contract_address=address,
                                    chart_bot_id=int(chart_bot_id_value),
                                )
                                if chart_bytes:
                                    logger.info(
                                        "[CHART_ALERT] Chart fetched for %s (chat %s, bytes=%d)",
                                        address[:8],
                                        chat_id,
                                        len(chart_bytes),
                                    )
                                else:
                                    logger.warning(
                                        "[CHART_ALERT] Chart fetch returned no image for %s (chat %s)",
                                        address[:8],
                                        chat_id,
                                    )
                            except Exception as exc:
                                logger.error(
                                    "[CHART_ALERT] Error fetching chart for %s (chat %s): %s",
                                    address[:8],
                                    chat_id,
                                    exc,
                                    exc_info=True,
                                )
                                chart_bytes = None
                        else:
                            logger.warning(
                                "[CHART_ALERT] ChartFetcher unavailable; cannot fetch chart for chat %s",
                                chat_id,
                            )
                    else:
                        logger.debug(
                            "[CHART_ALERT] Current MC %s below chart threshold %s for chat %s; skipping chart fetch",
                            current_mc,
                            chart_threshold,
                            chat_id,
                        )
                elif chart_enabled_flag:
                    logger.warning(
                        "[CHART_ALERT] Chart bot not configured for chat %s and no global default; skipping chart fetch",
                        chat_id,
                    )

                extra_targets = group.get('extra_targets') or []
                unique_targets = {chat_id}
                unique_targets.update(extra_targets)

                sent_success = False

                template_override = group.get('template_text')
                if (template_override is None or template_override == "") and chat_id not in template_cache:
                    try:
                        chat_records = await self.source_model.get_by_chat(chat_id)
                        template_cache[chat_id] = next(
                            (record.get('template_text') for record in chat_records if record.get('template_text')),
                            None,
                        )
                    except Exception as exc:
                        logger.debug(
                            "[GAIN_ALERT] Failed to lookup template for chat %s: %s",
                            chat_id,
                            exc,
                        )
                        template_cache[chat_id] = None
                if template_override in (None, ""):
                    template_override = template_cache.get(chat_id)
                template_candidate = template_override or global_template or DEFAULT_GAIN_ALERT_TEMPLATE

                missing = missing_required_placeholders(template_candidate)
                if missing:
                    logger.warning(
                        "[GAIN_ALERT] Template for chat %s missing placeholders %s. Falling back to global template.",
                        chat_id,
                        ", ".join(sorted(missing)),
                    )
                    template_candidate = global_template or DEFAULT_GAIN_ALERT_TEMPLATE

                group_template_values = dict(template_values)
                group_template_values["first_market_cap"] = self._format_mc_shorthand(first_seen_mc)
                try:
                    multiplier_value = float(current_mc / first_seen_mc) if first_seen_mc > 0 else None
                except (ValueError, ZeroDivisionError):
                    multiplier_value = None
                if multiplier_value is not None:
                    group_template_values["multiplier"] = f"{multiplier_value:.1f}x"

                try:
                    alert_message = template_candidate.format(**group_template_values)
                except KeyError as exc:
                    logger.error(
                        "[GAIN_ALERT] Template formatting failed for chat %s (missing key: %s). Skipping.",
                        chat_id,
                        exc,
                        exc_info=True,
                    )
                    continue

                for target_chat in unique_targets:
                    try:
                        target_chat_int = int(target_chat)
                    except (TypeError, ValueError):
                        logger.debug(f"[GROUP_ALERT_FIRE] Invalid target chat id {target_chat}, skipping")
                        continue

                    reply_id = reply_to_msg_id if target_chat_int == chat_id else None

                    alert_id = await db.fetchval(
                        """
                            INSERT INTO alert_queue
                            (token_id, token_address, alert_message, target_chat_id, reply_to_message_id, status)
                            VALUES ($1, $2, $3, $4, $5, 'pending')
                            RETURNING id
                        """,
                        token_id,
                        address,
                        alert_message,
                        target_chat_int,
                        reply_id,
                    )

                    if use_management_bot:
                        result = await self._send_via_management_bot(
                            target_chat_int,
                            alert_message,
                            reply_id,
                            photo_bytes=chart_bytes,
                        )
                    else:
                        result = await executor.send_call_message(
                            target_chat_id=target_chat_int,
                            message=alert_message,
                            token_address=address,
                            reply_to_message_id=reply_id,
                            photo_bytes=chart_bytes,
                        )

                    if result.get('success'):
                        sent_success = True
                        any_success = True
                        logger.info(
                            f"[GROUP_ALERT_FIRE] Sent to chat {target_chat_int}, msg_id={result.get('message_id')}"
                        )
                        await db.execute(
                            """
                                UPDATE alert_queue
                                SET status='sent', attempt_count=1, last_attempt_at=NOW()
                                WHERE id=$1
                            """,
                            alert_id,
                        )
                    else:
                        error_text = result.get('error') or 'Unknown error'
                        logger.error(
                            f"[GROUP_ALERT_FIRE] Failed to send to chat {target_chat_int}: {error_text}"
                        )
                        await db.execute(
                            """
                                UPDATE alert_queue
                                SET status='failed', error=$2, attempt_count=1, last_attempt_at=NOW()
                                WHERE id=$1
                            """,
                            alert_id,
                            error_text,
                        )

                if sent_success:
                    await db.execute(
                        """
                            UPDATE token_group_alerts
                            SET last_alert_mc = $1
                            WHERE token_id = $2 AND chat_id = $3
                        """,
                        current_mc,
                        token_id,
                        chat_id,
                    )

            return any_success

        except Exception as e:
            logger.error(f"Error dispatching gain alert for {address[:8]}...: {e}", exc_info=True)
            return False

    async def _evaluate_stop_loss(self, token: Dict, current_mc: Decimal) -> Tuple[bool, Optional[str]]:
        """
        Evaluate if token should stop monitoring based on drop conditions.

        Returns:
            Tuple of (should_stop, stop_reason)
        """
        try:
            # Get thresholds from settings
            settings_dict = await get_gain_alert_settings()
            drop_threshold_pct = settings_dict['drop_threshold_pct']
            drop_floor_mc = Decimal(str(settings_dict['drop_floor_mc']))

            first_seen_mc = token.get('first_seen_mc')

            if not first_seen_mc or first_seen_mc <= 0:
                return (False, None)

            # Calculate drop threshold (70% of first_seen_mc)
            drop_threshold = first_seen_mc * Decimal(str(drop_threshold_pct))

            # Check if below percentage threshold
            if current_mc <= drop_threshold:
                return (True, 'mc_drop_70')

            # Check if below absolute floor
            if current_mc <= drop_floor_mc:
                return (True, 'mc_below_floor')

            return (False, None)

        except Exception as e:
            logger.error(f"Error evaluating stop-loss: {e}", exc_info=True)
            return (False, None)

    async def _stop_token(self, token_id: int, address: str, reason: str) -> None:
        """Stop monitoring a token and remove from scheduler."""
        try:
            await self.token_model.set_status(token_id, 'stopped')
            await self.token_model.set_stop_reason(token_id, reason)

            logger.info(f"[STOP] Token {address[:8]}... stopped monitoring: {reason}")

        except Exception as e:
            logger.error(f"Error stopping token {address[:8]}...: {e}", exc_info=True)

    # ==================== TOKEN MANAGEMENT ====================

    async def add_token(self, token_address: str) -> Dict[str, Any]:
        """
        Register a new token (creates initial DB record).
        Note: Jupiter snapshot and tier initialization happen in TokenMonitor.
        """
        try:
            existing = await self.token_model.get_by_address(token_address)
            if existing:
                return {
                    "success": False,
                    "error": "Token already being tracked",
                    "token": dict(existing),
                }

            initial_mc = Decimal("0")
            token = await self.token_model.create_or_update(
                token_address, initial_mc, ticker=None
            )

            logger.info(f"[INIT] Registered {token_address[:8]}... for tracking")

            return {
                "success": True,
                "token": dict(token),
                "initial_mc": float(initial_mc),
            }

        except Exception as exc:
            logger.error(f"Error adding token {token_address[:8]}...: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

    async def remove_token(self, token_address: str) -> Dict[str, Any]:
        """Mark a token as stopped and remove from scheduler."""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    "success": False,
                    "error": "Token not found",
                }

            await self.token_model.set_status(token["id"], "stopped")
            logger.info(f"Stopped tracking {token_address[:8]}...")

            return {
                "success": True,
                "token": dict(token),
            }

        except Exception as exc:
            logger.error(f"Error stopping tracking for {token_address[:8]}...: {exc}", exc_info=True)
            return {
                "success": False,
                "error": str(exc),
            }

    async def promote_to_tier_b(self, token_id: int) -> None:
        """
        Promote token to Tier B (used after gain alert fires).
        Immediately resets tier and reschedules for 30s polling.
        """
        try:
            # Set tier to tier_b with 30s poll interval
            next_poll = datetime.now(timezone.utc) + timedelta(seconds=30)
            await self.token_model.update_tier(token_id, 'tier_b', next_poll)

            # Fetch token info for heap
            token = await db.fetchrow("SELECT * FROM tokens_tracked WHERE id = $1", token_id)
            if token:
                # Add to heap only if not already scheduled
                if token_id not in self._tokens_in_heap:
                    heapq.heappush(self._poll_heap, (next_poll, token_id, token['address']))
                    self._tokens_in_heap.add(token_id)
                    logger.info(f"[TIER_B] Token ID {token_id} promoted to Tier B")
                else:
                    logger.debug(f"[TIER_B] Token ID {token_id} already in heap, skipping")

        except Exception as e:
            logger.error(f"Error promoting token {token_id} to Tier B: {e}", exc_info=True)

    async def add_token_to_scheduler(self, token_id: int) -> None:
        """
        Add a newly detected token to the scheduler heap.
        Should be called after token initialization with next_poll_at set.
        """
        try:
            # Fetch token info from DB
            token = await db.fetchrow("SELECT * FROM tokens_tracked WHERE id = $1", token_id)

            if not token:
                logger.warning(f"[SCHEDULER] Cannot add token ID {token_id} to scheduler: not found in DB")
                return

            next_poll = token.get('next_poll_at')
            address = token.get('address')

            if not next_poll or not address:
                logger.warning(f"[SCHEDULER] Cannot add token ID {token_id} to scheduler: missing next_poll_at or address")
                return

            # Add to heap only if not already scheduled
            if token_id not in self._tokens_in_heap:
                heapq.heappush(self._poll_heap, (next_poll, token_id, address))
                self._tokens_in_heap.add(token_id)
                logger.info(
                    f"[SCHEDULER] Added token {address[:8]}... (ID {token_id}) to scheduler, "
                    f"next poll at {next_poll}"
                )
            else:
                logger.debug(f"[SCHEDULER] Token ID {token_id} already in heap, skipping")

        except Exception as e:
            logger.error(f"Error adding token {token_id} to scheduler: {e}", exc_info=True)

    def _determine_chain_id(self, token: Dict[str, Any], address: str) -> str:
        """
        Determine the DexScreener chain identifier for a token.

        Priority order:
            1. Explicit blockchain value on the token record (if present).
            2. Address heuristic (0x... -> BSC, default -> Solana).
        """
        # Heuristic based on address format
        heuristic = None
        if address.lower().startswith("0x") and len(address) == 42:
            heuristic = "bsc"
        elif len(address) in (32, 44):
            heuristic = "solana"

        blockchain = None
        if token:
            blockchain = token.get("blockchain") or token.get("chain")
        if heuristic:
            return heuristic
        if blockchain:
            return blockchain.upper()
        return "sol"

    async def _fetch_token_data(
        self,
        address: str,
        chain_id: Optional[str] = None,
        use_cache: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch the full list of DexScreener pairs for a token.

        Used by placeholder generators when the Rust service payload is missing.
        """
        normalized_chain: Optional[str] = None
        try:
            normalized_chain = self._normalise_chain_id(chain_id, address)
            pairs = await self.dex_client.fetch_token_pairs(
                address,
                chain_id=normalized_chain,
                use_cache=use_cache,
            )
            if pairs is None:
                return None
            return list(pairs)
        except Exception as exc:
            chain_label = chain_id or normalized_chain or "unknown"
            logger.error(
                "[DEX] Error fetching token pairs for %s:%s: %s",
                chain_label,
                address[:8] + "...",
                exc,
                exc_info=True,
            )
            return None

    def _normalise_chain_id(self, chain_id: Optional[str], address: str) -> str:
        """Normalise various chain identifiers to DexScreener API expectations."""
        if not chain_id:
            if address.lower().startswith("0x") and len(address) == 42:
                candidate = "bsc"
            else:
                candidate = "solana"
        else:
            candidate = chain_id.lower()

        if candidate in ("sol", "solana", "solana-mainnet"):
            return "solana"
        if candidate in ("bsc", "bnb", "bep20", "binance"):
            return "bsc"
        return candidate

    # ==================== INFO & STATS ====================

    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """Return token information from the database."""
        try:
            token = await self.token_model.get_by_address(token_address)
            if not token:
                return {
                    "success": False,
                    "error": "Token not found in database",
                }

            result: Dict[str, Any] = {
                "success": True,
                "token": dict(token),
                "dex_data": None,
            }

            first_seen_mc = token.get("first_seen_mc")
            last_mc = token.get("last_mc")
            if first_seen_mc and last_mc and first_seen_mc > 0:
                result["multiplier"] = float(last_mc / first_seen_mc)

            return result

        except Exception as exc:
            logger.error(f"Error loading token info for {token_address}: {exc}")
            return {
                "success": False,
                "error": str(exc),
            }

    async def get_service_stats(self) -> Dict[str, Any]:
        """Return service statistics including scheduler status."""
        try:
            token_stats = await self.token_model.get_token_stats()
        except Exception as exc:
            logger.error(f"Error fetching token stats: {exc}", exc_info=True)
            token_stats = {}

        return {
            "running": self.running,
            "monitoring_enabled": True,
            "scheduler_active": self._scheduler_task is not None and not self._scheduler_task.done(),
            "tokens_in_queue": len(self._poll_heap),
            "poll_interval": settings.dex_poll_secs,
            "timeout": settings.dex_timeout,
            "max_retries": settings.dex_max_retries,
            "tokens": token_stats,
        }
