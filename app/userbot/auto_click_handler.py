"""
Auto Click Handler - Handles automated button clicking and DM auto-replies
"""

import logging
import json
import asyncio
from app.db import db

logger = logging.getLogger(__name__)


async def handle_auto_click(handler, event):
    """Handle auto-click for tracked messages with button replies."""
    if not event.is_reply:
        return

    reply_to_msg_id = event.message.reply_to_msg_id
    if not reply_to_msg_id:
        return

    # Check if this is a reply to a message we are tracking for auto-click
    tracked_msgs = await db.fetch(
        "SELECT * FROM autoclick_tracked_messages WHERE original_message_id = $1 AND chat_id = $2 AND status = 'tracking'",
        reply_to_msg_id, event.chat_id
    )
    if not tracked_msgs:
        return

    for tracked_msg in tracked_msgs:
        # Ensure this userbot is the one that should be clicking
        if tracked_msg.get('userbot_id') and tracked_msg['userbot_id'] != handler.userbot_id:
            logger.debug(f"Ignoring auto-click for rule {tracked_msg['rule_id']}; userbot {handler.userbot_id} is not the designated clicker.")
            continue

        # Get the rule associated with this tracked message
        rule = await handler.rule_model.get_by_id(tracked_msg['rule_id'])
        if not rule or not rule['enabled']:
            continue

        # Check if the reply is from the correct bot
        if rule['bot_id'] != event.sender_id:
            continue

        logger.info(f"Valid auto-click reply detected for rule {rule['id']}. Searching for button...")

        # Get our client to perform the click
        client = handler.session_manager.get_client()
        if not client:
            logger.error(f"Client not available for button click on rule {rule['id']}")
            await db.execute("UPDATE autoclick_tracked_messages SET status = 'failed' WHERE id = $1", tracked_msg['id'])
            continue

        # Click the button with retry logic
        max_retries = 3
        retry_delay = 2  # seconds
        button_found_and_clicked = False

        if event.buttons:
            for row in event.buttons:
                for button in row:
                    if hasattr(button, 'text') and rule['button_text'] in button.text:
                        # Try clicking with retries using our client
                        click_success = False
                        for attempt in range(max_retries):
                            try:
                                # Refetch the message using our client to get fresh button reference
                                fresh_msg = await client.get_messages(event.chat_id, ids=event.message.id)
                                if not fresh_msg or not fresh_msg.buttons:
                                    logger.error(f"Could not refetch message with buttons for rule {rule['id']}")
                                    break

                                # Find the matching button in the fresh message
                                fresh_button = None
                                for fresh_row in fresh_msg.buttons:
                                    for fb in fresh_row:
                                        if hasattr(fb, 'text') and rule['button_text'] in fb.text:
                                            fresh_button = fb
                                            break
                                    if fresh_button:
                                        break

                                if not fresh_button:
                                    logger.error(f"Button not found in refetched message for rule {rule['id']}")
                                    break

                                # Click using our client
                                await fresh_button.click()
                                logger.info(f"Auto-clicked button '{rule['button_text']}' in chat {event.chat_id} for rule {rule['id']} (attempt {attempt + 1})")
                                click_success = True
                                break  # Success, exit retry loop
                            except Exception as e:
                                logger.error(f"Button click attempt {attempt + 1}/{max_retries} failed for rule {rule['id']}: {e}")
                                if attempt < max_retries - 1:
                                    logger.info(f"Retrying button click in {retry_delay} seconds...")
                                    await asyncio.sleep(retry_delay)
                                else:
                                    logger.error(f"All {max_retries} button click attempts failed for rule {rule['id']}")

                        # Update status based on result
                        if click_success:
                            await db.execute("UPDATE autoclick_tracked_messages SET status = 'processed' WHERE id = $1", tracked_msg['id'])
                        else:
                            await db.execute("UPDATE autoclick_tracked_messages SET status = 'failed' WHERE id = $1", tracked_msg['id'])

                        button_found_and_clicked = True
                        break # Found and processed button for this rule, move to next rule
                if button_found_and_clicked:
                    break

        if not button_found_and_clicked:
            # If we reach here, the button was not found
            logger.warning(f"Reply from bot {event.sender_id} received, but button '{rule['button_text']}' not found for rule {rule['id']}.")


async def handle_dynamic_click(handler, event):
    """Handle dynamic button clicking for monitored users"""
    # Only process messages with buttons
    if not event.buttons:
        return

    # Get dynamic rules for this chat and sender
    rules = await handler.rule_model.get_dynamic_rules_for_chat_and_user(
        event.chat_id,
        event.sender_id
    )

    if not rules:
        return

    # Get our client to perform clicks
    client = handler.session_manager.get_client()
    if not client:
        logger.error(f"[DYNAMIC_CLICK] Client not available for button clicks")
        return

    for rule in rules:
        # clicking_userbot_ids may be a JSON string or already a list.
        clicking_userbot_ids_raw = rule.get('clicking_userbot_ids')
        clicking_userbot_ids = []
        if isinstance(clicking_userbot_ids_raw, str):
            try:
                clicking_userbot_ids = json.loads(clicking_userbot_ids_raw)
            except json.JSONDecodeError:
                logger.warning(f"[DYNAMIC_CLICK] Could not decode clicking_userbot_ids JSON: {clicking_userbot_ids_raw}")
        elif isinstance(clicking_userbot_ids_raw, list):
            clicking_userbot_ids = clicking_userbot_ids_raw

        if not clicking_userbot_ids or handler.userbot_id not in clicking_userbot_ids:
            continue

        message_id = event.message.id

        # Calculate position in sequence for time-based delay
        sorted_ids = sorted(clicking_userbot_ids)
        try:
            my_position = sorted_ids.index(handler.userbot_id)
        except ValueError:
            my_position = 0
            logger.warning(f"[DYNAMIC_CLICK] Could not find userbot {handler.userbot_id} in clicking list")

        # Create auto-reply session if enabled
        session_id = None
        if rule.get('auto_reply_enabled'):
            from app.models.auto_reply_session import AutoReplySessionModel
            session_model = AutoReplySessionModel(handler.db)

            # Get the bot that created the buttons
            bot_user_id = None
            if hasattr(event.message, 'via_bot_id') and event.message.via_bot_id:
                bot_user_id = event.message.via_bot_id
            elif hasattr(event.message, 'via_bot') and event.message.via_bot:
                bot_user_id = event.message.via_bot.id
            else:
                bot_user_id = event.sender_id

            if bot_user_id:
                ticker_value = rule.get('ticker_value', '')
                # Create session in WAITING state
                session_id = await session_model.create_session(
                    rule_id=rule['id'],
                    message_id=message_id,
                    userbot_id=handler.userbot_id,
                    bot_user_id=bot_user_id,
                    ticker_value=ticker_value
                )
                logger.info(f"[AUTO_REPLY] Created session {session_id} for userbot={handler.userbot_id}, position={my_position}")
            else:
                logger.warning(f"[AUTO_REPLY] Could not determine bot ID for rule {rule['id']}")

        # Time-based sequential delay: position * 5 seconds
        delay = my_position * 5
        if delay > 0:
            logger.info(f"[DYNAMIC_CLICK] Userbot {handler.userbot_id} waiting {delay}s (position {my_position}) before clicking")
            await asyncio.sleep(delay)

        # Mark session as ready to click
        if session_id:
            await session_model.mark_ready(session_id)

        button_texts = rule['button_texts']  # JSONB array
        if not button_texts:
            continue

        matched_button_texts = []

        # Find all matching button texts (exact match)
        for row in event.buttons:
            for button in row:
                if hasattr(button, 'text') and button.text in button_texts:
                    matched_button_texts.append(button.text)

        if not matched_button_texts:
            continue

        # Click all matched buttons with retry logic and 1 sec delay between buttons
        max_retries = 3
        retry_delay = 2  # seconds
        clicked_count = 0

        for button_text in set(matched_button_texts): # Use set to avoid clicking the same button twice
            click_success = False
            for attempt in range(max_retries):
                try:
                    # Refetch the message using our client to get fresh button reference
                    fresh_msg = await client.get_messages(event.chat_id, ids=event.message.id)
                    if not fresh_msg or not fresh_msg.buttons:
                        logger.debug(f"[DYNAMIC_CLICK] Button '{button_text}' disappeared for rule {rule['id']}, likely already clicked.")
                        break

                    # Find the matching button in the fresh message
                    fresh_button = None
                    for fresh_row in fresh_msg.buttons:
                        for fb in fresh_row:
                            if hasattr(fb, 'text') and fb.text == button_text:
                                fresh_button = fb
                                break
                        if fresh_button:
                            break

                    if not fresh_button:
                        logger.debug(f"[DYNAMIC_CLICK] Button '{button_text}' not found in refetched message for rule {rule['id']}.")
                        break

                    # Click using our client
                    await fresh_button.click()
                    click_success = True
                    break  # Success, exit retry loop
                except Exception as e:
                    logger.error(f"[DYNAMIC_CLICK] Button click attempt {attempt + 1}/{max_retries} failed for rule {rule['id']}: {e}")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)

            if click_success:
                clicked_count += 1
                # Delay before next button (if there are more buttons)
                if clicked_count < len(matched_button_texts):
                    await asyncio.sleep(1)
            else:
                # This is not necessarily an error if another bot clicked first
                logger.debug(f"[DYNAMIC_CLICK] Could not click button '{button_text}' for rule {rule['id']}. It might have been clicked by another bot.")

        if clicked_count > 0:
            logger.info(f"[DYNAMIC_CLICK] Userbot {handler.userbot_id} successfully clicked {clicked_count}/{len(set(matched_button_texts))} matched buttons for rule {rule['id']} in chat {event.chat_id}")

            # Mark session as clicked
            if session_id:
                await session_model.mark_clicked(session_id)


async def handle_dm_auto_reply(handler, event):
    """Handle incoming DMs and auto-reply if we're expecting a DM from this bot."""
    try:
        # Only process if it's a DM (private chat)
        if not event.is_private:
            return

        sender_id = event.sender_id
        logger.info(f"[AUTO_REPLY] Processing DM from sender {sender_id} for userbot {handler.userbot_id}")

        # Look up active session for this DM
        from app.models.auto_reply_session import AutoReplySessionModel
        from app.models.dynamic_reply import DynamicReplyModel

        session_model = AutoReplySessionModel(handler.db)
        reply_model = DynamicReplyModel(handler.db)

        session = await session_model.get_session_for_dm(handler.userbot_id, sender_id)

        if not session:
            logger.debug(f"[AUTO_REPLY] No active session for DM from bot {sender_id} -> userbot {handler.userbot_id}")
            return

        logger.info(f"[AUTO_REPLY] Found session {session['id']} for DM (state={session['state']}, rule={session['rule_id']})")

        # Mark DM as received
        await session_model.mark_dm_received(session['id'])

        # Wait 5 seconds before replying (human-like behavior)
        logger.info(f"[AUTO_REPLY] Waiting 5s before replying to session {session['id']}")
        await asyncio.sleep(5)

        # Get random reply message
        reply_data = await reply_model.get_random_reply_for_rule(session['rule_id'])

        if not reply_data:
            logger.warning(f"[AUTO_REPLY] No replies configured for rule {session['rule_id']}")
            await session_model.mark_failed(session['id'], "No reply messages configured")
            return

        # Replace {ticker} placeholder
        ticker_value = session.get('ticker_value', '')
        reply_text = reply_data['message_text'].replace('{ticker}', ticker_value)

        # Send reply
        await event.reply(reply_text)
        logger.info(f"[AUTO_REPLY] Replied to bot {sender_id}: {reply_text[:50]}... (session={session['id']}, rule={session['rule_id']})")

        # Mark session as replied
        await session_model.mark_replied(session['id'])

    except Exception as e:
        logger.error(f"[AUTO_REPLY] Error handling DM auto-reply: {e}", exc_info=True)
