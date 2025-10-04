-- Add missing columns to pending_dm_replies table

DO $$
BEGIN
    -- Add message_id column to track which source message triggered the click
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pending_dm_replies' AND column_name='message_id'
    ) THEN
        ALTER TABLE pending_dm_replies ADD COLUMN message_id INTEGER;
        CREATE INDEX idx_pending_dm_replies_message ON pending_dm_replies(message_id);
    END IF;

    -- Add dm_received column to track if DM was received
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pending_dm_replies' AND column_name='dm_received'
    ) THEN
        ALTER TABLE pending_dm_replies ADD COLUMN dm_received BOOLEAN DEFAULT FALSE;
    END IF;

    -- Add replied column to track if we've replied to the DM
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pending_dm_replies' AND column_name='replied'
    ) THEN
        ALTER TABLE pending_dm_replies ADD COLUMN replied BOOLEAN DEFAULT FALSE;
    END IF;

    -- Add turn_completed_at column for multi-userbot coordination
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='pending_dm_replies' AND column_name='turn_completed_at'
    ) THEN
        ALTER TABLE pending_dm_replies ADD COLUMN turn_completed_at TIMESTAMP;
        CREATE INDEX idx_pending_dm_replies_turn ON pending_dm_replies(turn_completed_at);
    END IF;
END $$;
