-- Add pnl_tracked_messages table for persistent PNL command tracking
CREATE TABLE IF NOT EXISTS pnl_tracked_messages (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES pnl_forwarding_rules(id) ON DELETE CASCADE,
    original_message_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    sender_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'tracking', -- tracking, replied, expired
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(original_message_id, chat_id)
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_pnl_tracked_messages_lookup ON pnl_tracked_messages (original_message_id, chat_id, status);
