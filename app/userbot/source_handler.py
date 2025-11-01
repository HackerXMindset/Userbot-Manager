import json
import logging
import os
import shutil
import time
import traceback
from pathlib import Path
from typing import Dict, Any, List, Tuple
import tempfile

from telethon import utils as telethon_utils

logger = logging.getLogger(__name__)

MEDIA_CACHE_ROOT = Path(tempfile.gettempdir()) / "callbot_media"
MEDIA_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

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


def apply_rewrite_rules(text: str, rewrite_rules: List[Dict[str, str]]) -> tuple[str, bool]:
    """Apply rewrite rules to text, returning modified text and change flag."""
    if not text or not rewrite_rules:
        return text, False

    modified = text
    changed = False
    for rule in rewrite_rules:
        source_value = rule.get("source")
        target_value = rule.get("target", "")
        if not source_value:
            continue
        if source_value in modified:
            modified = modified.replace(source_value, target_value)
            changed = True
    return modified, changed


async def _cache_media_for_forwarding(client, source_chat_id: int, source_message_id: int) -> Dict[str, Any]:
    """Download media to a cache directory and return metadata for dispatcher."""
    if client is None:
        return {}

    try:
        message = await client.get_messages(source_chat_id, ids=source_message_id)
        if isinstance(message, list):
            message = message[0] if message else None
        if not message or not getattr(message, "media", None):
            return {}

        media_messages = [message]

        if getattr(message, "grouped_id", None):
            grouped_id = message.grouped_id
            related: List[Any] = []
            async for sibling in client.iter_messages(
                source_chat_id,
                min_id=message.id - 20,
                max_id=message.id + 20,
            ):
                if sibling.id == message.id:
                    continue
                if getattr(sibling, "grouped_id", None) == grouped_id and getattr(sibling, "media", None):
                    related.append(sibling)
            media_messages.extend(related)
            media_messages = sorted(media_messages, key=lambda msg: msg.id)

        cache_key = f"{source_chat_id}_{source_message_id}_{int(time.time())}"
        cache_dir = MEDIA_CACHE_ROOT / cache_key
        cache_dir.mkdir(parents=True, exist_ok=True)

        files: List[Dict[str, str]] = []
        for msg in media_messages:
            if not getattr(msg, "media", None):
                continue

            extension = ""
            try:
                extension = telethon_utils.get_extension(msg.media) or ""
            except Exception:
                extension = ""
            if extension and not extension.startswith("."):
                extension = f".{extension}"

            filename = f"{msg.id}{extension or '.bin'}"
            file_path = cache_dir / filename
            try:
                await client.download_media(msg, file=str(file_path))
            except Exception as download_error:
                logger.warning(
                    f"[FORWARD] Failed to download media {source_chat_id}:{msg.id} - {download_error}"
                )
                continue

            if not file_path.exists() or file_path.stat().st_size == 0:
                continue

            files.append({"name": filename})

        if not files:
            shutil.rmtree(cache_dir, ignore_errors=True)
            return {}

        logger.debug(
            "[FORWARD] Cached %d media attachment(s) for %s:%s at %s",
            len(files),
            source_chat_id,
            source_message_id,
            cache_dir,
        )

        return {"dir": cache_key, "files": files}
    except Exception as media_error:
        logger.warning(
            f"[FORWARD] Failed to cache media for {source_chat_id}:{source_message_id} - {media_error}"
        )
        return {}


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

        routing_rules_raw: List[Dict[str, Any]] = await handler.source_model.get_routing_rules(source["id"])
        logger.info(f"[SPLIT-RESP] Found {len(routing_rules_raw)} routing rules for source {source['id']}")

        routing_rules: List[Dict[str, Any]] = []
        route_by_group_id: Dict[int, Dict[str, Any]] = {}
        keyword_route_ids: List[int] = []
        everything_route_ids: List[int] = []

        for raw_rule in routing_rules_raw:
            if not raw_rule["enabled"]:
                continue

            rule = dict(raw_rule)
            forwarding_mode = (rule.get("forwarding_mode") or "tokens").lower()
            allowed_chains = rule.get("allowed_chains", ["SOL"])
            if isinstance(allowed_chains, str):
                try:
                    allowed_chains = json.loads(allowed_chains)
                except Exception:
                    allowed_chains = ["SOL"]
            keyword_filters = rule.get("keyword_filters", [])
            if isinstance(keyword_filters, str):
                try:
                    keyword_filters = json.loads(keyword_filters)
                except Exception:
                    keyword_filters = []
            keyword_filters = [kw.strip().lower() for kw in keyword_filters if kw]

            rewrite_rules = rule.get("forward_rewrite_rules", [])
            if isinstance(rewrite_rules, str):
                try:
                    rewrite_rules = json.loads(rewrite_rules)
                except Exception:
                    rewrite_rules = []
            normalized_rewrites: List[Dict[str, str]] = []
            for entry in rewrite_rules:
                if not isinstance(entry, dict):
                    continue
                source_value = (entry.get("source") or "").strip()
                target_value = (entry.get("target") or "").strip()
                if not source_value:
                    continue
                normalized_rewrites.append({"source": source_value, "target": target_value})

            rule["forwarding_mode"] = forwarding_mode
            rule["allowed_chains"] = allowed_chains
            rule["keyword_filters"] = keyword_filters
            rule["forward_rewrite_rules"] = normalized_rewrites

            routing_rules.append(rule)
            route_by_group_id[rule["target_group_id"]] = rule

            if forwarding_mode == "keywords":
                keyword_route_ids.append(rule["id"])
            elif forwarding_mode == "everything":
                everything_route_ids.append(rule["id"])

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

        message_obj = event.message if hasattr(event, "message") else event
        grouped_id = getattr(message_obj, "grouped_id", None)
        if grouped_id:
            album_guard = getattr(handler, "_album_guard", {})
            now = time.time()
            # evict stale entries (>120s)
            stale_cutoff = now - 120
            for key, ts in list(album_guard.items()):
                if ts < stale_cutoff:
                    album_guard.pop(key, None)
            album_key = (event.chat_id, grouped_id)
            if album_key in album_guard:
                logger.debug(
                    f"[SPLIT-RESP] Skipping duplicate album message for source {event.chat_id} group {grouped_id}"
                )
                return
            album_guard[album_key] = now
            handler._album_guard = album_guard

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

        forwarded_groups = set()
        target_groups_by_id = {group["id"]: group for group in target_groups}
        message_text = handler.utils.get_message_text(event.message) if hasattr(event, "message") else ""
        message_text_lower = message_text.lower() if message_text else ""

        async def forward_full_message(route: Dict[str, Any], group: Dict[str, Any], reason: str) -> None:
            if not group:
                return
            if route["target_group_id"] in forwarded_groups:
                return

            forwarding_userbot_id = (
                route.get("forwarding_userbot_id")
                or source_forward_bot
                or handler.userbot_id
            )

            chat_username = None
            chat_obj = getattr(event, "chat", None)
            if chat_obj and getattr(chat_obj, "username", None):
                chat_username = chat_obj.username

            rewrite_rules = route.get("forward_rewrite_rules", [])
            message_for_delivery = message_text
            apply_rewrite = False
            if rewrite_rules and message_text:
                message_for_delivery, apply_rewrite = apply_rewrite_rules(message_text, rewrite_rules)

            raw_media = getattr(event, "media", None)
            message_media = getattr(getattr(event, "message", None), "media", None)
            has_media = bool(raw_media or message_media)
            client = handler.session_manager.get_client()

            logger.debug(
                f"[FORWARD] Route {route['id']} media detection: raw_media={'yes' if raw_media else 'no'}, "
                f"message_media={'yes' if message_media else 'no'}, has_media={has_media}, "
                f"forward_bot={forwarding_userbot_id}, monitor_bot={handler.userbot_id}"
            )

            if not await can_group_accept_calls(handler, group["tg_chat_id"]):
                logger.info(
                    f"[FORWARD] Skipping group {group['tg_chat_id']} for route {route['id']} ({reason}) - outside schedule window"
                )
                return

            if forwarding_userbot_id != handler.userbot_id:
                logger.debug(
                    f"[FORWARD] Queueing forward job for route {route['id']} via forwarding userbot {forwarding_userbot_id}"
                )
            else:
                logger.debug(
                    f"[FORWARD] No dedicated forward bot assigned for route {route['id']} — using monitoring userbot {handler.userbot_id}"
                )

            display_source_name = (
                live_source_name or source.get("display_name") or source.get("name") or source.get("title")
            )
            source_info = f"From {display_source_name or event.chat_id}"
            allow_media = bool(route.get("forward_media", True))

            additional_info_dict = {
                "message_text": message_for_delivery,
                "caller_name": handler.utils.get_user_name(event.sender),
                "source_name": display_source_name,
                "source_type": source_type_value,
                "source_chat_id": event.chat_id,
                "source_chat_username": chat_username,
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
                "forward_original": True,
                "forward_reason": reason,
                "monitor_userbot_id": handler.userbot_id,
                "source_message_id": event.id,
            }
            if route.get("forward_summary"):
                additional_info_dict["forward_summary"] = True

            queue_source_chat_id = event.chat_id
            queue_source_message_id = event.id
            forward_original_flag = (
                forwarding_userbot_id == handler.userbot_id and not apply_rewrite and allow_media
            )
            copy_message_flag = not forward_original_flag
            copy_media_flag = has_media and not forward_original_flag and allow_media

            if forward_original_flag:
                additional_info_dict["forward_original"] = True
            else:
                additional_info_dict.pop("forward_original", None)
            additional_info_dict["copy_message"] = copy_message_flag
            additional_info_dict.pop("message_override", None)
            if apply_rewrite:
                additional_info_dict["message_override"] = message_for_delivery
                copy_media_flag = has_media and allow_media
            
            if copy_media_flag and has_media and forwarding_userbot_id != handler.userbot_id:
                try:
                    media_cache_info = await _cache_media_for_forwarding(
                        client,
                        event.chat_id,
                        event.id,
                    )
                    if media_cache_info:
                        additional_info_dict["media_cache"] = media_cache_info
                except Exception as cache_error:
                    logger.warning(
                        f"[FORWARD] Failed to cache media for route {route['id']}: {cache_error}"
                    )
            
            additional_info_dict["copy_media"] = copy_media_flag

            token_stub = f"MSG-{event.id}-{route['id']}"
            job = None
            try:
                job = await handler.call_queue_model.add_job(
                    routing_rule_id=route["id"],
                    token_address=token_stub,
                    source_message_id=queue_source_message_id,
                    source_chat_id=queue_source_chat_id,
                    source_user_id=event.sender_id,
                    target_group_id=group["id"],
                    target_chat_id=group["tg_chat_id"],
                    forwarding_userbot_id=forwarding_userbot_id,
                    source_info=json.dumps(source_info),
                    additional_info=json.dumps(additional_info_dict),
                    priority=5,
                )
            except Exception as queue_error:
                logger.error(
                    f"[FORWARD] ❌ Failed to enqueue forward job for route {route['id']} (reason: {reason}): {queue_error}"
                )
                job = None

            if job:
                forwarded_groups.add(route["target_group_id"])
                logger.info(
                    f"[FORWARD] Queued message forward job {job['id']} for route {route['id']} → target {group['tg_chat_id']} ({reason})"
                )
            else:
                logger.warning(
                    f"[FORWARD] ❌ Call queue returned no job for route {route['id']} ({reason})"
                )
                if forwarding_userbot_id != handler.userbot_id:
                    logger.warning(
                        f"[FORWARD] Attempting direct forward fallback via monitoring userbot {handler.userbot_id}"
                    )
                client = handler.session_manager.get_client()
                if not client:
                    logger.error(f"[FORWARD] No client available for fallback forward on route {route['id']}")
                    return
                if not hasattr(event, "message") or event.message is None:
                    logger.debug(f"[FORWARD] Event has no message to forward during fallback for route {route['id']}")
                    return
                try:
                    if allow_media:
                        await client.forward_messages(group["tg_chat_id"], event.message)
                    else:
                        if message_for_delivery:
                            await client.send_message(group["tg_chat_id"], message_for_delivery)
                        else:
                            logger.info(
                                f"[FORWARD] Skipping media-only fallback for route {route['id']} (media disabled and no text)"
                            )
                            return
                    forwarded_groups.add(route["target_group_id"])
                    logger.info(
                        f"[FORWARD] ✅ Fallback forward succeeded via monitoring userbot {handler.userbot_id}"
                    )
                except Exception as forward_error:
                    logger.error(
                        f"[FORWARD] ❌ Fallback forward failed for route {route['id']} to {group['tg_chat_id']}: {forward_error}"
                    )

        # Forward-everything routes
        for route_id in everything_route_ids:
            route = next((r for r in routing_rules if r["id"] == route_id), None)
            if not route:
                continue
            group = target_groups_by_id.get(route["target_group_id"])
            await forward_full_message(route, group, "forward_everything")

        # Keyword routes
        if message_text_lower:
            for route_id in keyword_route_ids:
                route = next((r for r in routing_rules if r["id"] == route_id), None)
                if not route:
                    continue
                keywords = route.get("keyword_filters") or []
                if not keywords:
                    logger.debug(f"[FORWARD] Route {route_id} set to keyword mode without keywords")
                    continue
                if any(keyword in message_text_lower for keyword in keywords):
                    group = target_groups_by_id.get(route["target_group_id"])
                    await forward_full_message(route, group, "keyword_match")
                else:
                    logger.debug(
                        f"[FORWARD] Keyword route {route_id} did not match message text in source {event.chat_id}"
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

            route = route_by_group_id.get(target_group["id"])
            if not route:
                logger.warning(
                    f"[SPLIT-RESP] No routing rule found for target group {target_group['id']} - SKIPPING"
                )
                continue

            if route["forwarding_mode"] != "tokens":
                logger.debug(
                    f"[SPLIT-RESP] Skipping token queue for group {target_group['id']} (mode={route['forwarding_mode']})"
                )
                continue

            if not await can_group_accept_calls(handler, target_group["tg_chat_id"]):
                logger.info(
                    f"[SPLIT-RESP] Skipping group {target_group['tg_chat_id']} - outside schedule window"
                )
                continue

            group_queued = 0
            group_failed = 0

            forwarding_userbot_id = route.get("forwarding_userbot_id")
            if not forwarding_userbot_id:
                forwarding_userbot_id = handler.userbot_id
                logger.info(
                    f"[SPLIT-RESP] No forwarding userbot assigned, using current userbot {handler.userbot_id} "
                    "(backward compatibility)"
                )
            else:
                logger.info(f"[SPLIT-RESP] Using assigned forwarding userbot {forwarding_userbot_id}")

            for address, blockchain in addresses_to_forward:
                try:
                    allowed_chains = route.get("allowed_chains", ["SOL"])
                    if blockchain not in allowed_chains:
                        logger.info(
                            f"[CHAIN_FILTER] Rule {route['id']} allows {allowed_chains}, token is {blockchain} - SKIPPED"
                        )
                        continue

                    logger.debug(
                        f"[CHAIN_FILTER] Rule {route['id']} allows {allowed_chains}, token is {blockchain} - ALLOWED"
                    )

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

                    job = await handler.call_queue_model.add_job(
                        routing_rule_id=route["id"],
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
