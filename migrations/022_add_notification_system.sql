-- Add notification_settings table
CREATE TABLE IF NOT EXISTS notification_settings (
    id SERIAL PRIMARY KEY,
    notification_channel_id BIGINT
);

-- Add notification_blacklist table
CREATE TABLE IF NOT EXISTS notification_blacklist (
    user_id BIGINT PRIMARY KEY
);

-- Add username to bots table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='bots' AND column_name='username') THEN
        ALTER TABLE bots ADD COLUMN username VARCHAR(255);
    END IF;
END $$;
