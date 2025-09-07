-- Add advanced configuration fields to source_chats to match groups functionality

-- Add quota and notification fields to source_chats
ALTER TABLE source_chats ADD COLUMN IF NOT EXISTS daily_cap INT DEFAULT 0;
ALTER TABLE source_chats ADD COLUMN IF NOT EXISTS cooldown_minutes INT DEFAULT 10;
ALTER TABLE source_chats ADD COLUMN IF NOT EXISTS notif_channel_id BIGINT;

-- Extend userbot_assignments to support sources (not just groups)
ALTER TABLE userbot_assignments ADD COLUMN IF NOT EXISTS source_id BIGINT REFERENCES source_chats(id) ON DELETE CASCADE;

-- Remove the unique constraint on group_id since we now support source assignments too
ALTER TABLE userbot_assignments DROP CONSTRAINT IF EXISTS userbot_assignments_group_id_key;

-- Add new constraints: either group_id OR source_id must be set (not both)
ALTER TABLE userbot_assignments ADD CONSTRAINT userbot_assignments_target_check 
CHECK (
    (group_id IS NOT NULL AND source_id IS NULL) OR 
    (group_id IS NULL AND source_id IS NOT NULL)
);

-- Ensure unique assignment per userbot per target (group or source)
CREATE UNIQUE INDEX IF NOT EXISTS userbot_assignments_userbot_group_unique 
ON userbot_assignments(userbot_id, group_id) 
WHERE group_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS userbot_assignments_userbot_source_unique 
ON userbot_assignments(userbot_id, source_id) 
WHERE source_id IS NOT NULL;

-- Create source_schedules table (similar to group_schedules)
CREATE TABLE IF NOT EXISTS source_schedules (
    id BIGSERIAL PRIMARY KEY,
    source_id BIGINT REFERENCES source_chats(id) ON DELETE CASCADE,
    weekdays INT[] NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    max_calls_in_window INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_source_schedules_source_id ON source_schedules(source_id);
CREATE INDEX IF NOT EXISTS idx_userbot_assignments_source_id ON userbot_assignments(source_id);