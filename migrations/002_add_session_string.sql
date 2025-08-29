-- Add session_string column to bots table for userbot session storage
ALTER TABLE bots ADD COLUMN IF NOT EXISTS session_string TEXT;

-- Add additional userbot info columns
ALTER TABLE bots ADD COLUMN IF NOT EXISTS telegram_id BIGINT;
ALTER TABLE bots ADD COLUMN IF NOT EXISTS username TEXT;
ALTER TABLE bots ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE bots ADD COLUMN IF NOT EXISTS last_name TEXT;

-- Create index on telegram_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_bots_telegram_id ON bots(telegram_id);