-- Fix missing columns in call_queue table from incomplete migration 027
-- Add missing columns if they don't exist (for existing tables)
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS routing_rule_id BIGINT REFERENCES routing_rules(id) ON DELETE CASCADE;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS target_group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS source_info TEXT;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS additional_info TEXT;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS processed_at TIMESTAMPTZ;
ALTER TABLE call_queue ADD COLUMN IF NOT EXISTS error_message TEXT;