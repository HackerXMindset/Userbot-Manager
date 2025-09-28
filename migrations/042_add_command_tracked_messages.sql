-- Command tracked messages table for tracking custom commands awaiting replies
CREATE TABLE IF NOT EXISTS command_tracked_messages (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES command_forwarding_rules(id) ON DELETE CASCADE,
    original_message_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    sender_id BIGINT NOT NULL,
    command_text TEXT NOT NULL, -- Store the actual command that was sent
    status TEXT NOT NULL DEFAULT 'tracking', -- tracking, forwarded, expired
    reply_sender_id BIGINT, -- ID of user who replied (when forwarded)
    last_reply_message_id BIGINT, -- Message ID of the reply that was forwarded
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure uniqueness per rule to prevent duplicate tracking
    UNIQUE(original_message_id, chat_id, rule_id)
);

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_command_tracked_messages_lookup ON command_tracked_messages (original_message_id, chat_id, status);
CREATE INDEX IF NOT EXISTS idx_command_tracked_messages_rule ON command_tracked_messages (rule_id, status);
CREATE INDEX IF NOT EXISTS idx_command_tracked_messages_cleanup ON command_tracked_messages (created_at) WHERE status IN ('tracking');

-- Comments for clarity
COMMENT ON TABLE command_tracked_messages IS 'Tracks custom commands that are awaiting replies for forwarding';
COMMENT ON COLUMN command_tracked_messages.command_text IS 'The actual command text that was sent and is being tracked';
COMMENT ON COLUMN command_tracked_messages.status IS 'Current status: tracking (awaiting reply), forwarded (reply sent), expired (too old)';