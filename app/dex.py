"""
DexScreener Token Service with Tier-Based Scheduler

Monitors token market caps using DexScreener API with intelligent tier-based
polling intervals. Handles gain alert triggers and stop-loss conditions.
"""

import asyncio
import heapq
import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings, get_gain_alert_settings
from app.db import db
from app.models import TokenModel
from app.services.dexscreener_api import get_dexscreener_client
from app.services.okx_market_api import get_okx_market_client
from app.utils.tier_calculator import calculate_next_poll_time, get_poll_interval_for_tier

logger = logging.getLogger(__name__)

# Singleton instance for global access
_dex_service_instance: Optional["DexScreenerService"] = None


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
        self.dex_client = get_dexscreener_client()
        self.okx_client = get_okx_market_client()
        self.userbot_manager = None
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
        else:
            logger.info("UserbotManager cleared on Dex service")

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
                    pair_data = await self.dex_client.fetch_token(
                        address,
                        chain_id=chain_id,
                        use_cache=False,
                    )

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
                multiplier = float(current_mc / first_seen_mc)

                # Calculate elapsed time
                elapsed = self._format_elapsed_time(first_seen_at)

                # Format alert message per spec:
                # 🌙${TICKER} {multiplier:.1f}x | 💹From ${old_mc} ↗️ ${new_mc} within {elapsed}
                ticker_display = ticker or address[:8]
                alert_message = (
                    "⚠️ Gain alerts are in beta and may be inaccurate.\n"
                    f"🌙${ticker_display} {multiplier:.1f}x | "
                    f"💹From {self._format_mc_shorthand(first_seen_mc)} ↗️ {self._format_mc_shorthand(current_mc)} within {elapsed}"
                )

                logger.info(f"[GAIN_ALERT] Token {address[:8]}... triggered: {alert_message}")

                # Dispatch alert to target groups
                await self._dispatch_gain_alert(token, alert_message, address, current_mc)

                # Post-alert bookkeeping:
                # 1. Update last_alert_mc = current_mc
                await self.token_model.update_last_alert_mc(token_id, current_mc)

                # 2. Promote to Tier B
                await self.promote_to_tier_b(token_id)

                logger.info(f"[GAIN_ALERT] Token {address[:8]}... bookkeeping complete: last_alert_mc updated, promoted to Tier B")

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

    async def _dispatch_gain_alert(self, token: Dict, alert_message: str, address: str, current_mc: Decimal) -> None:
        """
        Dispatch gain alert to target groups.
        Sends as reply to original message if available, otherwise standalone.
        """
        try:
            token_id = token['id']

            if not self.userbot_manager:
                logger.warning(f"[GAIN_ALERT] No userbot manager set, cannot dispatch alert for {address[:8]}...")
                return

            tracking_groups = await db.fetch(
                """
                SELECT chat_id, original_message_id, first_seen_mc, last_alert_mc
                FROM token_group_alerts
                WHERE token_id = $1
                """,
                token_id,
            )

            if not tracking_groups:
                logger.debug(f"[GROUP_ALERT_FIRE] No monitored groups for token {address[:8]}..., skipping")
                return

            settings_dict = await get_gain_alert_settings()
            gain_threshold_pct = Decimal(str(settings_dict['gain_threshold_pct']))

            for group in tracking_groups:
                chat_id = group['chat_id']
                reply_to_msg_id = group['original_message_id']
                first_seen_mc = Decimal(str(group['first_seen_mc']))
                last_alert_mc = group['last_alert_mc']

                baseline_mc = Decimal(str(last_alert_mc)) if last_alert_mc else first_seen_mc

                if baseline_mc <= 0:
                    logger.debug(
                        f"[GROUP_ALERT_FIRE] Chat {chat_id} baseline invalid "
                        f"(first_seen={first_seen_mc}, last_alert={last_alert_mc}), skipping"
                    )
                    continue

                threshold_mc = baseline_mc * (Decimal(1) + gain_threshold_pct)

                if current_mc < threshold_mc:
                    continue

                alert_id = await db.fetchval("""
                    INSERT INTO alert_queue
                    (token_id, token_address, alert_message, target_chat_id, reply_to_message_id, status)
                    VALUES ($1, $2, $3, $4, $5, 'pending')
                    RETURNING id
                """, token_id, address, alert_message, chat_id, reply_to_msg_id)

                # Get any active worker to send the message
                workers = self.userbot_manager.get_all_workers()
                if not workers:
                    logger.error(f"[GAIN_ALERT] No active workers available to send alert")
                    await db.execute("""
                        UPDATE alert_queue
                        SET status='failed', error='No active workers', attempt_count=1, last_attempt_at=NOW()
                        WHERE id=$1
                    """, alert_id)
                    continue

                # Use first available worker
                worker = list(workers.values())[0]
                executor = worker.call_executor if hasattr(worker, 'call_executor') else None

                if not executor:
                    # Create executor if needed
                    from app.userbot.call_executor import CallExecutor
                    executor = CallExecutor(worker.userbot_id, worker.session_manager)

                # Send alert message
                result = await executor.send_call_message(
                    target_chat_id=chat_id,
                    message=alert_message,
                    token_address=address,
                    reply_to_message_id=reply_to_msg_id
                )

                if result['success']:
                    logger.info(f"[GROUP_ALERT_FIRE] Sent to chat {chat_id}, msg_id={result.get('message_id')}")
                    await db.execute("""
                        UPDATE alert_queue
                        SET status='sent', attempt_count=1, last_attempt_at=NOW()
                        WHERE id=$1
                    """, alert_id)

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
                else:
                    logger.error(f"[GROUP_ALERT_FIRE] Failed to send to chat {chat_id}: {result.get('error')}")
                    await db.execute("""
                        UPDATE alert_queue
                        SET status='failed', error=$2, attempt_count=1, last_attempt_at=NOW()
                        WHERE id=$1
                    """, alert_id, result.get('error'))

        except Exception as e:
            logger.error(f"Error dispatching gain alert for {address[:8]}...: {e}", exc_info=True)

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
