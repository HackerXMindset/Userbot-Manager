-- Add monitor and forwarding bot fields to source_chats table
-- This allows setting bots without requiring routing rules (useful for curated alpha)
ALTER TABLE source_chats
ADD COLUMN default_monitoring_userbot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
ADD COLUMN default_forwarding_userbot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL;

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_source_chats_monitoring_bot ON source_chats(default_monitoring_userbot_id);
CREATE INDEX IF NOT EXISTS idx_source_chats_forwarding_bot ON source_chats(default_forwarding_userbot_id);

-- Add comments for clarity
COMMENT ON COLUMN source_chats.default_monitoring_userbot_id IS 'Default userbot to monitor this source (used when no routing rules exist)';
COMMENT ON COLUMN source_chats.default_forwarding_userbot_id IS 'Default userbot to forward from this source (used for curated alpha and fallback)';