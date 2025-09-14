-- Add autoclick_tracked_messages table
CREATE TABLE IF NOT EXISTS autoclick_tracked_messages (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER REFERENCES auto_button_click_rules(id) ON DELETE CASCADE,
    original_message_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    status TEXT DEFAULT 'tracking', -- tracking, processed, expired
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_autoclick_tracked_messages_status ON autoclick_tracked_messages(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_autoclick_tracked_message_chat_rule ON autoclick_tracked_messages(original_message_id, chat_id, rule_id);
