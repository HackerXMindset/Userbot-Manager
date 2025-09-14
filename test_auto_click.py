
import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

# Setup project path
import sys
from pathlib import Path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db import db
from app.userbot.message_handler import MessageHandler
from app.models.auto_button_click import AutoButtonClickRuleModel

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Mock Objects ---

class MockButton:
    def __init__(self, text):
        self.text = text
        self.clicked = False

    async def click(self):
        self.clicked = True
        logger.info(f"SUCCESS: Mock button '{self.text}' was clicked.")

class MockMessage:
    def __init__(self, id, reply_to_msg_id, sender_id, buttons):
        self.id = id
        self.reply_to_msg_id = reply_to_msg_id
        self.sender_id = sender_id
        self.buttons = [[b] for b in buttons] # Mimic Telethon's structure
        self.is_reply = True

class MockEvent:
    def __init__(self, chat_id, message):
        self.chat_id = chat_id
        self.message = message
        self.is_reply = message.is_reply
        self.sender_id = message.sender_id
        self.buttons = message.buttons

# --- Test Runner ---

async def run_test():
    """Simulates the auto-click workflow."""
    logger.info("--- Starting Auto-Click Verification Test ---")
    
    # Test data
    TEST_TARGET_CHAT_ID = -100987654321
    TEST_BOT_ID = 123456789  # The bot that replies
    TEST_BUTTON_TEXT = "Click Me!"
    TEST_USERBOT_MESSAGE_ID = 111
    TEST_REPLY_MESSAGE_ID = 222

    # 1. Connect to the database
    await db.connect()
    rule_model = AutoButtonClickRuleModel(db)
    
    # Mock SessionManager and its client
    mock_session_manager = MagicMock()
    
    # Instantiate the handler with the mock session
    handler = MessageHandler(userbot_id=1, session_manager=mock_session_manager)

    test_rule_id = None
    test_call_id = None
    
    try:
        # 2. Create test data in the database
        logger.info("Step 1: Creating test data in the database...")
        
        # Create a rule
        rule = await rule_model.create({
            'target_chat_id': TEST_TARGET_CHAT_ID,
            'bot_id': TEST_BOT_ID,
            'button_text': TEST_BUTTON_TEXT
        })
        test_rule_id = rule['id']
        logger.info(f"  - Created auto_click_rule with ID: {test_rule_id}")

        # Create a fake 'call' record to simulate a message our userbot sent
        # We need a target_id first. Let's create a dummy target and group.
        group = await db.fetchrow("INSERT INTO groups (tg_chat_id, title) VALUES ($1, $2) RETURNING id", TEST_TARGET_CHAT_ID, 'Test Group')
        target = await db.fetchrow("INSERT INTO targets (group_id, dest_chat_id) VALUES ($1, $2) RETURNING id", group['id'], TEST_TARGET_CHAT_ID)
        
        call = await db.fetchrow(
            "INSERT INTO calls (group_id, target_id, userbot_id, status, message_id, scheduled_at) VALUES ($1, $2, $3, $4, $5, NOW()) RETURNING id",
            group['id'], target['id'], 1, 'sent', TEST_USERBOT_MESSAGE_ID
        )
        test_call_id = call['id']
        logger.info(f"  - Created 'call' record with ID: {test_call_id} for message_id {TEST_USERBOT_MESSAGE_ID}")

        # 3. Create mock Telegram event objects
        logger.info("Step 2: Simulating a bot reply event...")
        mock_button = MockButton(TEST_BUTTON_TEXT)
        mock_message = MockMessage(
            id=TEST_REPLY_MESSAGE_ID,
            reply_to_msg_id=TEST_USERBOT_MESSAGE_ID,
            sender_id=TEST_BOT_ID,
            buttons=[mock_button]
        )
        mock_event = MockEvent(chat_id=TEST_TARGET_CHAT_ID, message=mock_message)
        logger.info("  - Mock event created.")

        # 4. Run the handler
        logger.info("Step 3: Invoking the auto_click handler...")
        await handler._handle_auto_click(mock_event)

        # 5. Verify the result
        logger.info("Step 4: Verifying the result...")
        if mock_button.clicked:
            logger.info("✅ PASSED: The button was clicked successfully.")
        else:
            logger.error("❌ FAILED: The button was not clicked.")

    except Exception as e:
        logger.error(f"An error occurred during the test: {e}", exc_info=True)
    finally:
        # 6. Clean up test data
        logger.info("Step 5: Cleaning up test data...")
        
        # Use the test constants to ensure cleanup even if creation failed
        group_to_delete = await db.fetchrow("SELECT id FROM groups WHERE tg_chat_id = $1", TEST_TARGET_CHAT_ID)
        if group_to_delete:
            # Find target associated with the group
            target_to_delete = await db.fetchrow("SELECT id FROM targets WHERE group_id = $1", group_to_delete['id'])
            if target_to_delete:
                # Delete calls associated with the target
                await db.execute("DELETE FROM calls WHERE target_id = $1", target_to_delete['id'])
            
            # Delete the target itself
            await db.execute("DELETE FROM targets WHERE group_id = $1", group_to_delete['id'])
            
            # Finally, delete the group
            await db.execute("DELETE FROM groups WHERE id = $1", group_to_delete['id'])
            logger.info(f"  - Cleaned up test group and associated data for chat id {TEST_TARGET_CHAT_ID}.")

        # Cleanup rule by test data to be safe
        await db.execute("DELETE FROM auto_button_click_rules WHERE target_chat_id = $1 AND bot_id = $2", TEST_TARGET_CHAT_ID, TEST_BOT_ID)
        logger.info("  - Cleaned up test rule.")
            
        # Disconnect from the database
        await db.disconnect()
        logger.info("--- Test Finished ---")


if __name__ == "__main__":
    asyncio.run(run_test())
