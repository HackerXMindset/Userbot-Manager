-- Add alert queue table for reliable alert delivery with retry support

CREATE TABLE IF NOT EXISTS alert_queue (
    id SERIAL PRIMARY KEY,
    token_id INT REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    token_address TEXT NOT NULL,
    alert_message TEXT NOT NULL,
    target_chat_id BIGINT NOT NULL,
    reply_to_message_id BIGINT,
    attempt_count INT DEFAULT 0,
    last_attempt_at TIMESTAMPTZ,
    status TEXT DEFAULT 'pending',
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS idx_alert_queue_status ON alert_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_alert_queue_token_id ON alert_queue(token_id);
CREATE INDEX IF NOT EXISTS idx_alert_queue_pending ON alert_queue(created_at) WHERE status = 'pending';

-- Add constraint for valid status values
ALTER TABLE alert_queue
ADD CONSTRAINT check_alert_queue_status
CHECK (status IN ('pending', 'sent', 'failed'));
