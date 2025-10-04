-- Add turn tracking for sequential click-reply flow

DO $$
BEGIN
    -- Add columns to track turn state in pending_dm_replies
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='pending_dm_replies' AND column_name='dm_received') THEN
        ALTER TABLE pending_dm_replies
            ADD COLUMN dm_received BOOLEAN DEFAULT FALSE,
            ADD COLUMN replied BOOLEAN DEFAULT FALSE,
            ADD COLUMN turn_completed_at TIMESTAMP,
            ADD COLUMN message_id BIGINT;
    END IF;
END $$;
