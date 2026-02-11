import json
import logging
from typing import List, Tuple
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def handle_curated_alpha(handler, tagged_addresses: List[Tuple[str, str]], source_chat_id: int, event):
    """
    Processes tokens against Curated Alpha rules.
    Args:
        tagged_addresses: List of (address, blockchain) tuples
    """
    try:
        logger.debug(f"[CuratedAlpha] Processing event for source chat ID: {source_chat_id}")
        # Find all enabled rules that require this source chat
        rules = await handler.curated_alpha_rule_model.db.fetch(
            """
                SELECT * FROM curated_alpha_rules
                WHERE $1 = ANY(required_source_chat_ids) AND enabled = true
            """,
            source_chat_id,
        )

        if not rules:
            logger.debug(f"[CuratedAlpha] No active rules found for source_chat_id: {source_chat_id}")
            return  # No rules care about this source

        logger.debug(f"[CuratedAlpha] Source {source_chat_id} is part of {len(rules)} rule(s).")

        source_record = await handler.source_model.get_source_by_chat_id(source_chat_id)
        source_type_value = (
            source_record.get("source_type")
            if source_record and source_record.get("source_type")
            else ("dm" if event.is_private else "channel" if event.is_channel else "group")
        )
        current_source_name = handler.utils.get_chat_title(getattr(event, "chat", None))

        for address, blockchain in tagged_addresses:
            for rule in rules:
                # Check blockchain filter
                allowed_chains = rule.get("allowed_chains", ["SOL"])
                if blockchain not in allowed_chains:
                    logger.debug(
                        f"[CuratedAlpha] Rule {rule['id']} allows {allowed_chains}, token is {blockchain} - SKIPPED"
                    )
                    continue
                rule_id = rule["id"]
                logger.debug(
                    f"[CuratedAlpha] Checking token {address[:8]} against rule {rule_id} ('{rule['name']}')"
                )
                logger.debug(
                    f"[CuratedAlpha] Rule requirements: Mentions={rule.get('required_mentions', 'All')}, Sources={rule['required_source_chat_ids']}"
                )

                # Check if this token has already been triggered for this rule
                existing_state = await handler.curated_alpha_token_state_model.db.fetchrow(
                    """
                        SELECT * FROM curated_alpha_token_state
                        WHERE rule_id = $1 AND token_address = $2
                    """,
                    rule_id,
                    address,
                )

                if existing_state and existing_state["status"] in ("triggered", "expired"):
                    logger.debug(f"[CuratedAlpha] Found existing state for token: {dict(existing_state)}")
                    logger.debug(
                        f"[CuratedAlpha] Token {address[:8]} already '{existing_state['status']}' for rule {rule_id}. Skipping."
                    )
                    continue

                if existing_state:
                    logger.debug(
                        f"[CuratedAlpha] Found existing 'tracking' state for token {address[:8]} in rule {rule_id}."
                    )
                    # It's being tracked, let's update it
                    if source_chat_id in existing_state["seen_in_source_chat_ids"]:
                        logger.debug(
                            f"[CuratedAlpha] Token {address[:8]} already seen in this source for rule {rule_id}. Skipping."
                        )
                        continue

                    # Check if time window has expired
                    time_since_first_seen = (
                        datetime.now(timezone.utc) - existing_state["first_seen_at"]
                    ).total_seconds()
                    if time_since_first_seen > rule["time_window_seconds"]:
                        await handler.curated_alpha_token_state_model.update(
                            existing_state["id"], {"status": "expired"}
                        )
                        logger.info(f"[CuratedAlpha] Token {address[:8]}... expired for rule {rule_id}.")
                        continue

                    # Add the new source and get the updated list
                    updated_seen_sources = existing_state["seen_in_source_chat_ids"] + [source_chat_id]
                    await handler.curated_alpha_token_state_model.update(
                        existing_state["id"], {"seen_in_source_chat_ids": updated_seen_sources}
                    )
                    logger.debug(
                        f"[CuratedAlpha] Updated token {address[:8]} state for rule {rule_id}. Seen in: {updated_seen_sources}"
                    )

                    # Check if we reached required mentions
                    seen_in_rule_sources = set(updated_seen_sources)
                    required_mentions = rule.get("required_mentions")
                    if required_mentions is None or required_mentions <= 1:
                        # If no specific requirement, trigger on second unique source (current one)
                        should_trigger = len(seen_in_rule_sources) >= 1
                    else:
                        should_trigger = len(seen_in_rule_sources) >= required_mentions

                    if should_trigger:
                        logger.info(
                            f"[CuratedAlpha] Token {address[:8]} reached required mentions ({len(seen_in_rule_sources)}) for rule {rule_id}."
                        )
                        await handler.curated_alpha_token_state_model.update(
                            existing_state["id"], {"status": "triggered"}
                        )

                        source_info = f"Curated Alpha: Rule '{rule.get('name', rule_id)}'"

                        # Gather friendly names for all contributing sources
                        seen_source_details = [
                            {
                                "chat_id": source_chat_id,
                                "name": current_source_name,
                                "source_type": source_type_value,
                                "caller_name": handler.utils.get_user_name(event.sender),
                                "caller_user_id": event.sender_id,
                            }
                        ]
                        try:
                            ordered_seen_sources = sorted(seen_in_rule_sources)
                        except TypeError:
                            ordered_seen_sources = list(seen_in_rule_sources)

                        for seen_chat_id in ordered_seen_sources:
                            try:
                                seen_chat_id_int = int(seen_chat_id)
                            except (TypeError, ValueError):
                                seen_chat_id_int = seen_chat_id

                            if seen_chat_id_int == source_chat_id:
                                continue

                            seen_source_record = await handler.source_model.get_source_by_chat_id(seen_chat_id_int)
                            if seen_source_record:
                                display_name = (
                                    seen_source_record.get("display_name")
                                    or seen_source_record.get("name")
                                    or seen_source_record.get("title")
                                )
                                seen_source_type = seen_source_record.get("source_type")
                            else:
                                display_name = f"Chat {seen_chat_id_int}"
                                seen_source_type = "group"

                            seen_source_details.append(
                                {
                                    "chat_id": seen_chat_id_int,
                                    "name": display_name,
                                    "source_type": seen_source_type,
                                }
                            )

                        # Look up target group ID for template support
                        target_group_id = None
                        try:
                            group_record = await handler.db.fetchrow(
                                "SELECT id FROM groups WHERE tg_chat_id = $1",
                                rule["destination_chat_id"],
                            )
                            if group_record:
                                target_group_id = group_record["id"]
                        except Exception as group_lookup_error:
                            logger.debug(
                                f"Could not find group for destination chat {rule['destination_chat_id']}: {group_lookup_error}"
                            )

                        additional_info_dict = {
                            "message_text": handler.utils.get_message_text(event.message)
                            if hasattr(event, "message")
                            else "",
                            "target_group_id_fallback": target_group_id,
                            "caller_name": handler.utils.get_user_name(event.sender),
                            "source_name": current_source_name,
                            "source_type": source_type_value,
                            "source_chat_id": source_chat_id,
                            "seen_sources": seen_source_details,
                            "caller_user_id": event.sender_id,
                            "blockchain": blockchain,
                        }
                        additional_info = json.dumps(additional_info_dict)

                        await handler.call_queue_model.add_job(
                            curated_alpha_rule_id=rule_id,
                            token_address=address,
                            blockchain=blockchain,
                            source_message_id=event.id,
                            source_chat_id=source_chat_id,
                            source_user_id=event.sender_id,
                            target_group_id=target_group_id,
                            target_chat_id=rule["destination_chat_id"],
                            forwarding_userbot_id=rule["forwarding_userbot_id"],
                            source_info=json.dumps(source_info),
                            additional_info=additional_info,
                            priority=10,  # Higher priority for curated calls
                        )
                        logger.info(
                            f"[CuratedAlpha] Queued call for {address[:8]}... ({blockchain}) to {rule['destination_chat_id']}"
                        )

                    continue  # Move to next token/rule after updating state

                # No existing state — create tracking state
                seen_sources = [source_chat_id]
                await handler.curated_alpha_token_state_model.create(
                    {
                        "rule_id": rule_id,
                        "token_address": address,
                        "status": "tracking",
                        "first_seen_at": datetime.now(timezone.utc),
                        "seen_in_source_chat_ids": seen_sources,
                    }
                )
                logger.info(
                    f"[CuratedAlpha] Started tracking token {address[:8]} for rule {rule_id} in source {source_chat_id}"
                )

                # If rule requires only one mention, trigger immediately
                required_mentions = rule.get("required_mentions")
                should_trigger_immediately = required_mentions in (None, 0, 1)

                if should_trigger_immediately:
                    logger.info(
                        f"[CuratedAlpha] Rule {rule_id} requires only {required_mentions or 1} mention(s). Triggering immediately."
                    )
                    state_record = await handler.curated_alpha_token_state_model.db.fetchrow(
                        """
                            SELECT id FROM curated_alpha_token_state
                            WHERE rule_id = $1 AND token_address = $2
                        """,
                        rule_id,
                        address,
                    )
                    if state_record:
                        await handler.curated_alpha_token_state_model.update(
                            state_record["id"], {"status": "triggered"}
                        )

                    seen_source_details = [
                        {
                            "chat_id": source_chat_id,
                            "name": current_source_name,
                            "source_type": source_type_value,
                            "caller_name": handler.utils.get_user_name(event.sender),
                            "caller_user_id": event.sender_id,
                        }
                    ]

                    target_group_id = None
                    try:
                        group_record = await handler.db.fetchrow(
                            "SELECT id FROM groups WHERE tg_chat_id = $1",
                            rule["destination_chat_id"],
                        )
                        if group_record:
                            target_group_id = group_record["id"]
                    except Exception as group_lookup_error:
                        logger.debug(
                            f"Could not find group for destination chat {rule['destination_chat_id']}: {group_lookup_error}"
                        )

                    additional_info_dict = {
                        "message_text": handler.utils.get_message_text(event.message)
                        if hasattr(event, "message")
                        else "",
                        "target_group_id_fallback": target_group_id,
                        "caller_name": handler.utils.get_user_name(event.sender),
                        "source_name": current_source_name,
                        "source_type": source_type_value,
                        "source_chat_id": source_chat_id,
                        "seen_sources": seen_source_details,
                        "caller_user_id": event.sender_id,
                        "blockchain": blockchain,
                    }
                    additional_info = json.dumps(additional_info_dict)

                    await handler.call_queue_model.add_job(
                        curated_alpha_rule_id=rule_id,
                        token_address=address,
                        blockchain=blockchain,
                        source_message_id=event.id,
                        source_chat_id=source_chat_id,
                        source_user_id=event.sender_id,
                        target_group_id=target_group_id,
                        target_chat_id=rule["destination_chat_id"],
                        forwarding_userbot_id=rule["forwarding_userbot_id"],
                        source_info=json.dumps(f"Curated Alpha: Rule '{rule.get('name', rule_id)}'"),
                        additional_info=additional_info,
                        priority=10,
                    )
                    logger.info(
                        f"[CuratedAlpha] (Immediate) Queued call for {address[:8]}... ({blockchain}) to {rule['destination_chat_id']}"
                    )

    except Exception as e:
        logger.error(f"Error in handle_curated_alpha: {e}", exc_info=True)
