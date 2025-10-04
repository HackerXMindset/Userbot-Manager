-- Create new auto_reply_sessions table with state machine design

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='auto_reply_sessions') THEN
        CREATE TABLE auto_reply_sessions (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER NOT NULL REFERENCES auto_button_click_rules(id) ON DELETE CASCADE,
            message_id INTEGER NOT NULL,
            userbot_id INTEGER NOT NULL,
            bot_user_id BIGINT NOT NULL,
            ticker_value TEXT,

            -- State machine: WAITING | READY_TO_CLICK | CLICKED | DM_RECEIVED | REPLIED | TIMEOUT | FAILED
            state TEXT NOT NULL DEFAULT 'WAITING',

            -- Timestamps for each state transition
            created_at TIMESTAMP DEFAULT NOW(),
            ready_at TIMESTAMP,
            clicked_at TIMESTAMP,
            dm_received_at TIMESTAMP,
            replied_at TIMESTAMP,
            expires_at TIMESTAMP NOT NULL,

            -- Error tracking
            error_message TEXT,
            retry_count INTEGER DEFAULT 0,

            UNIQUE(rule_id, message_id, userbot_id)
        );

        CREATE INDEX idx_auto_reply_state ON auto_reply_sessions(state, expires_at);
        CREATE INDEX idx_auto_reply_lookup ON auto_reply_sessions(userbot_id, bot_user_id, state);
        CREATE INDEX idx_auto_reply_message ON auto_reply_sessions(message_id, rule_id);
    END IF;
END $$;
