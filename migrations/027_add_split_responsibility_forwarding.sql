-- Add monitoring and forwarding userbot assignments to routing rules
ALTER TABLE routing_rules
ADD COLUMN IF NOT EXISTS monitoring_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
ADD COLUMN IF NOT EXISTS forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL;

-- Create call queue table for job management
CREATE TABLE IF NOT EXISTS call_queue (
    id BIGSERIAL PRIMARY KEY,
    routing_rule_id BIGINT REFERENCES routing_rules(id) ON DELETE CASCADE,
    token_address TEXT NOT NULL,
    source_message_id BIGINT,
    source_chat_id BIGINT,
    target_group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    source_info TEXT,
    additional_info TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    error_message TEXT
);

-- Add missing columns if they don't exist (for existing tables)
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS routing_rule_id BIGINT REFERENCES routing_rules(id) ON DELETE CASCADE;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS target_group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS source_info TEXT;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS additional_info TEXT;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS error_message TEXT;

-- Indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_routing_rules_monitoring_userbot ON routing_rules(monitoring_userbot_id);
CREATE INDEX IF NOT EXISTS idx_routing_rules_forwarding_userbot ON routing_rules(forwarding_userbot_id);
CREATE INDEX IF NOT EXISTS idx_call_queue_status ON call_queue(status);
CREATE INDEX IF NOT EXISTS idx_call_queue_forwarding_userbot ON call_queue(forwarding_userbot_id);
CREATE INDEX IF NOT EXISTS idx_call_queue_priority_created ON call_queue(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_call_queue_pending ON call_queue(status, created_at) WHERE status = 'pending';