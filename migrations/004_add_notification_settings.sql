-- Notification settings table
CREATE TABLE IF NOT EXISTS notification_settings (
    id BIGSERIAL PRIMARY KEY,
    notification_channel_id BIGINT,
    blacklisted_user_ids BIGINT[] DEFAULT '{}',
    event_types_enabled JSONB DEFAULT '{"reply": true, "mention": true, "dm": true, "token_call": false}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default notification settings
INSERT INTO notification_settings (notification_channel_id, blacklisted_user_ids, event_types_enabled)
VALUES (NULL, '{}', '{"reply": true, "mention": true, "dm": true, "token_call": false}')
ON CONFLICT DO NOTHING;

-- Add index for faster lookups
CREATE INDEX IF NOT EXISTS idx_notification_settings_channel ON notification_settings(notification_channel_id);