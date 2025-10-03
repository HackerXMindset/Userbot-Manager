-- Add userbot_id to autoclick_tracked_messages to specify which bot should click
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='autoclick_tracked_messages' AND column_name='userbot_id') THEN
        ALTER TABLE autoclick_tracked_messages ADD COLUMN userbot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Add an index for faster lookups
CREATE INDEX IF NOT EXISTS idx_autoclick_tracked_messages_userbot_id ON autoclick_tracked_messages(userbot_id);
