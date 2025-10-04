-- Create table for tracking pending DM auto-replies after button clicks

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='pending_dm_replies') THEN
        CREATE TABLE pending_dm_replies (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER NOT NULL REFERENCES auto_button_click_rules(id) ON DELETE CASCADE,
            userbot_id INTEGER NOT NULL,
            expected_bot_user_id BIGINT NOT NULL,
            ticker_value TEXT,
            clicked_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP NOT NULL,
            UNIQUE(rule_id, userbot_id, expected_bot_user_id)
        );

        CREATE INDEX idx_pending_dm_replies_expires
            ON pending_dm_replies(expires_at);
        CREATE INDEX idx_pending_dm_replies_userbot
            ON pending_dm_replies(userbot_id, expected_bot_user_id);
    END IF;
END $$;
