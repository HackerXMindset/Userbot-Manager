import json
import logging
import time
import traceback
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


async def can_group_accept_calls(handler, tg_chat_id: int) -> bool:
    """Check if group can accept calls at current time/day"""
    try:
        # Get current time info for cache key
        from app.config import settings

        now = settings.get_local_time()
        current_day = now.weekday() + 1  # Monday = 1
        current_hour = now.hour

        # Check cache first
        cache_key = f"schedule_{tg_chat_id}_{current_day}_{current_hour}"
        if handler.is_fresh(cache_key):
            return handler.cache[cache_key]

        # Get group record
        group = await handler.group_model.get_by_chat_id(tg_chat_id)
        if not group or not group["enabled"]:
            result = False
            handler.cache[cache_key] = result
            handler.cache_time[cache_key] = time.time()
            return result

        current_time = now.time()

        # Check if group has any schedules at all
        all_schedules = await handler.schedule_model.get_by_group(group["id"])

        # If no schedules defined, allow by default (schedules are optional)
        if not all_schedules:
            result = True
        else:
            # Group has schedules - check if any are currently active
            active_schedules = await handler.schedule_model.get_active_schedules(current_day, current_time)
            result = False
            for schedule in active_schedules:
                if schedule["tg_chat_id"] == tg_chat_id:
                    result = True
                    break

        # Cache result for 10 minutes
        handler.cache[cache_key] = result
        handler.cache_time[cache_key] = time.time()
        return result

    except Exception as e:
        logger.error(f"Error checking schedule for group {tg_chat_id}: {e}")
        # Default to allow if schedule check fails
        return True


async def handle_source_message(handler, event, is_edit: bool = False):
    """Handle messages from source chats - extract tokens and route to targets"""
    try:
        logger.info(
            f"[SPLIT-RESP] Processing source message - Chat: {event.chat_id}, Userbot: {handler.userbot_id}, Edit: {is_edit}"
        )

        # Validate source permissions
        permission_check = await handler.source_manager.validate_source_permissions(event)
        logger.debug(f"[SPLIT-RESP] Source permission check result: {permission_check}")

        if not permission_check["allowed"]:
            logger.debug(f"[SPLIT-RESP] Source message rejected: {permission_check['reason']}")
            return

        source = permission_check["source"]
        live_source_name = handler.utils.get_chat_title(getattr(event, "chat", None))

        source_type_value = source.get("source_type")
        if not source_type_value:
            if event.is_private:
                source_type_value = "dm"
            elif event.is_channel:
                source_type_value = "channel"
            else:
                source_type_value = "group"

        if live_source_name:
            try:
                await handler.source_model.update(source["id"], {"display_name": live_source_name})
                source["display_name"] = live_source_name
            except Exception as update_error:
                logger.debug(f"[SPLIT-RESP] Unable to update source display name: {update_error}")

        logger.info(
            f"[SPLIT-RESP] Source validated - ID: {source['id']}, Name: "
            f"{live_source_name or source.get('display_name') or source.get('name', 'N/A')}"
        )

        routing_rules: List[Dict[str, Any]] = await handler.source_model.get_routing_rules(source["id"])
        logger.info(f"[SPLIT-RESP] Found {len(routing_rules)} routing rules for source {source['id']}")

        source_monitor_bot = source.get("default_monitoring_userbot_id")
        source_forward_bot = source.get("default_forwarding_userbot_id")

        monitoring_allowed = False
        primary_monitor_id = None
        designated_monitors = set()

        if source_monitor_bot:
            primary_monitor_id = source_monitor_bot
            if handler.userbot_id == source_monitor_bot:
                monitoring_allowed = True
                logger.info(
                    f"[SPLIT-RESP] Userbot {handler.userbot_id} is the source-level designated monitor for source {source['id']}"
                )
            else:
                logger.debug(
                    f"[SPLIT-RESP] Userbot {handler.userbot_id} not source-level monitor (assigned: {source_monitor_bot})"
                )
        else:
            designated_monitors = {
                rule["monitoring_userbot_id"] for rule in routing_rules if rule["monitoring_userbot_id"] is not None
            }
            logger.debug(f"[SPLIT-RESP] Designated monitors for source {source['id']}: {designated_monitors}")

            if designated_monitors:
                primary_monitor_id = min(designated_monitors)
                if handler.userbot_id == primary_monitor_id:
                    monitoring_allowed = True
                    logger.info(
                        f"[SPLIT-RESP] Userbot {handler.userbot_id} is the designated primary monitor (min ID) for source {source['id']}"
                    )
                else:
                    logger.debug(
                        f"[SPLIT-RESP] Userbot {handler.userbot_id} not primary monitor (primary: {primary_monitor_id})"
                    )
            else:
                if routing_rules and routing_rules[0]["forwarding_userbot_id"]:
                    primary_monitor_id = routing_rules[0]["forwarding_userbot_id"]
                    if handler.userbot_id == primary_monitor_id:
                        monitoring_allowed = True
                        logger.info(
                            f"[SPLIT-RESP] Userbot {handler.userbot_id} assigned as monitor by backward compatibility rule "
                            f"(first forwarder) for source {source['id']}"
                        )
                    else:
                        logger.debug(
                            f"[SPLIT-RESP] Userbot {handler.userbot_id} not assigned as backward compatibility monitor "
                            f"(assigned: {primary_monitor_id})"
                        )
                else:
                    logger.warning(
                        f"[SPLIT-RESP] No routing rules or forwarding userbot found for source {source['id']}"
                    )

        if not monitoring_allowed:
            logger.debug(
                f"[SPLIT-RESP] ⏭️ Userbot {handler.userbot_id} SKIPPING - not designated monitor for source {event.chat_id}"
            )
            logger.debug(
                f"[SPLIT-RESP] Designated monitors: {designated_monitors}, Primary: "
                f"{primary_monitor_id if designated_monitors else 'source-level or backward compatibility'}"
            )
            return
        logger.debug(f"[SPLIT-RESP] ✅ Userbot {handler.userbot_id} IS designated monitor for source {event.chat_id}")

        # Get all target groups for this source using routing rules
        target_groups = await handler.source_manager.get_target_groups_for_source(event.chat_id)

        # Process message for tokens regardless of routing rules (needed for curated alpha)
        tagged_addresses: List[Tuple[str, str]] = await handler.token_monitor.process_source_message(
            event, event.chat_id, target_groups or []
        )

        # Handle Curated Alpha logic independently (works without routing rules)
        if tagged_addresses:
            await handler._handle_curated_alpha(tagged_addresses, event.chat_id, event)

        # Early return if no routing rules for regular forwarding
        if not target_groups:
            logger.warning(
                f"[SPLIT-RESP] No target groups found for source {event.chat_id} - skipping regular forwarding"
            )
            return

        logger.info(
            "[SPLIT-RESP] Found %d target groups: %s",
            len(target_groups),
            [f"{g['title']}({g['id']})" for g in target_groups],
        )

        if not tagged_addresses:
            logger.debug("[SPLIT-RESP] No token addresses found in message")
            return

        logger.info(
            f"[SPLIT-RESP] Extracted {len(tagged_addresses)} token addresses: "
            f"{[(addr[:8] + '...', chain) for addr, chain in tagged_addresses]}"
        )

        # Filter out recently forwarded tokens
        unseen_tagged_addresses = []
        for address, blockchain in tagged_addresses:
            recently_forwarded = await handler.db.fetchval(
                """
                    SELECT 1 FROM forwarded_tokens_log
                    WHERE token_address = $1 AND source_chat_id = $2 AND blockchain = $3
                    AND forwarded_at > NOW() - INTERVAL '24 hours'
                    LIMIT 1
                """,
                address,
                event.chat_id,
                blockchain,
            )

            if recently_forwarded:
                logger.info(
                    f"Token {address[:8]}... ({blockchain}) from source {event.chat_id} was already forwarded recently. Skipping."
                )
            else:
                unseen_tagged_addresses.append((address, blockchain))

        if not unseen_tagged_addresses:
            logger.info("All extracted tokens were recently forwarded. Nothing to do.")
            return

        addresses_to_forward = unseen_tagged_addresses
        logger.info(
            f"[SPLIT-RESP] Starting job queue population for {len(addresses_to_forward)} new tokens across "
            f"{len(target_groups)} target groups"
        )

        # Queue tokens for all target groups
        total_queued = 0
        total_failed = 0

        for target_group in target_groups:
            logger.debug(f"[SPLIT-RESP] Processing target group: {target_group['title']}({target_group['id']})")

            # Check if group can accept calls at current time/day
            if not await can_group_accept_calls(handler, target_group["tg_chat_id"]):
                logger.info(
                    f"[SPLIT-RESP] Skipping group {target_group['tg_chat_id']} - outside schedule window"
                )
                continue

            group_queued = 0
            group_failed = 0

            # Find routing rule and forwarding userbot for this target group
            routing_rule = None
            forwarding_userbot_id = None

            for rule in routing_rules:
                if rule["target_group_id"] == target_group["id"] and rule["enabled"]:
                    routing_rule = rule
                    forwarding_userbot_id = rule["forwarding_userbot_id"]
                    logger.debug(
                        f"[SPLIT-RESP] Matched routing rule {rule['id']} for group {target_group['id']}, "
                        f"forwarding_userbot: {forwarding_userbot_id}"
                    )
                    break

            if not routing_rule:
                logger.warning(
                    f"[SPLIT-RESP] No routing rule found for target group {target_group['id']} - SKIPPING"
                )
                continue

            if not forwarding_userbot_id:
                forwarding_userbot_id = handler.userbot_id
                logger.info(
                    f"[SPLIT-RESP] No forwarding userbot assigned, using current userbot {handler.userbot_id} "
                    "(backward compatibility)"
                )
            else:
                logger.info(f"[SPLIT-RESP] Using assigned forwarding userbot {forwarding_userbot_id}")

            # Queue each token for this target group
            for address, blockchain in addresses_to_forward:
                try:
                    # Check blockchain filter
                    allowed_chains = routing_rule.get("allowed_chains", ["SOL"])
                    if blockchain not in allowed_chains:
                        logger.info(
                            f"[CHAIN_FILTER] Rule {routing_rule['id']} allows {allowed_chains}, token is {blockchain} - SKIPPED"
                        )
                        continue

                    logger.debug(
                        f"[CHAIN_FILTER] Rule {routing_rule['id']} allows {allowed_chains}, token is {blockchain} - ALLOWED"
                    )

                    # Get source info for the call
                    display_source_name = (
                        live_source_name or source.get("display_name") or source.get("name") or source.get("title")
                    )
                    source_info = f"From {display_source_name or event.chat_id}"
                    additional_info_dict = {
                        "message_text": handler.utils.get_message_text(event.message)
                        if hasattr(event, "message")
                        else "",
                        "caller_name": handler.utils.get_user_name(event.sender),
                        "source_name": display_source_name,
                        "source_type": source_type_value,
                        "source_chat_id": event.chat_id,
                        "seen_sources": [
                            {
                                "chat_id": event.chat_id,
                                "name": display_source_name,
                                "source_type": source_type_value,
                                "caller_name": handler.utils.get_user_name(event.sender),
                                "caller_user_id": event.sender_id,
                            }
                        ],
                        "caller_user_id": event.sender_id,
                        "blockchain": blockchain,
                    }

                    logger.debug(
                        f"[SPLIT-RESP] Queueing token {address[:8]}... ({blockchain}) for target "
                        f"{target_group['id']} via userbot {forwarding_userbot_id}"
                    )

                    # Add job to call queue with blockchain info
                    job = await handler.call_queue_model.add_job(
                        routing_rule_id=routing_rule["id"],
                        token_address=address,
                        blockchain=blockchain,
                        source_message_id=event.id,
                        source_chat_id=event.chat_id,
                        source_user_id=event.sender_id,
                        target_group_id=target_group["id"],
                        target_chat_id=target_group["tg_chat_id"],
                        forwarding_userbot_id=forwarding_userbot_id,
                        source_info=json.dumps(source_info),
                        additional_info=json.dumps(additional_info_dict),
                    )

                    if job:
                        group_queued += 1
                        total_queued += 1
                        logger.debug(
                            f"[SPLIT-RESP] ✅ Job {job['id']} created for {address[:8]}... ({blockchain}) → {target_group['title']}"
                        )
                    else:
                        group_failed += 1
                        total_failed += 1
                        logger.warning(
                            f"[SPLIT-RESP] ❌ Failed to queue {address[:8]}... ({blockchain}) "
                            f"for {target_group['title'] or target_group['tg_chat_id']}"
                        )

                except Exception as token_error:
                    group_failed += 1
                    total_failed += 1
                    logger.error(
                        f"[SPLIT-RESP] ❌ Error queuing token {address[:8]}... ({blockchain}) for target "
                        f"{target_group['tg_chat_id']} via userbot {handler.userbot_id}: {token_error}"
                    )
                    logger.error(f"[SPLIT-RESP] Full traceback: {traceback.format_exc()}")

            if group_queued > 0:
                logger.info(f"[SPLIT-RESP] ✅ Group {target_group['title']}: {group_queued} tokens queued")
            if group_failed > 0:
                logger.warning(f"[SPLIT-RESP] ❌ Group {target_group['title']}: {group_failed} tokens failed")

        logger.info(
            f"[SPLIT-RESP] 🎯 QUEUE SUMMARY: {total_queued} jobs created, {total_failed} failed "
            f"across {len(target_groups)} target groups by userbot {handler.userbot_id}"
        )

        # After successfully queuing the jobs, log the new tokens as forwarded
        if total_queued > 0:
            try:
                payload = [(addr, event.chat_id, blockchain) for addr, blockchain in addresses_to_forward]
                pool = getattr(handler.db, "pool", None)
                if pool and hasattr(pool, "executemany"):
                    await pool.executemany(
                        """
                            INSERT INTO forwarded_tokens_log (token_address, source_chat_id, blockchain)
                            VALUES ($1, $2, $3)
                        """,
                        payload,
                    )
                else:
                    for addr, blockchain in addresses_to_forward:
                        await handler.db.execute(
                            """
                                INSERT INTO forwarded_tokens_log (token_address, source_chat_id, blockchain)
                                VALUES ($1, $2, $3)
                            """,
                            addr,
                            event.chat_id,
                            blockchain,
                        )
                logger.info(
                    f"Logged {len(addresses_to_forward)} new tokens to forwarded_tokens_log for source {event.chat_id}"
                )
            except Exception as log_error:
                logger.error(f"Failed to log forwarded tokens: {log_error}")

        # Update bot last seen
        await handler.bot_model.update_last_seen(handler.userbot_id)

    except Exception as e:
        logger.error(
            f"[SPLIT-RESP] ❌ Critical error handling source message in chat {event.chat_id} "
            f"by userbot {handler.userbot_id}: {e}"
        )
        logger.error(f"[SPLIT-RESP] Full traceback: {traceback.format_exc()}")
