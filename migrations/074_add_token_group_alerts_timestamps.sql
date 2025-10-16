-- Migration 074: Add timestamp tracking to token_group_alerts
-- These columns track when alerts are sent and provide better history tracking

-- Add timestamp columns for better alert tracking
ALTER TABLE token_group_alerts
ADD COLUMN IF NOT EXISTS first_seen_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_alert_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS last_alert_message_id BIGINT;

-- Backfill first_seen_at from created_at for existing records
UPDATE token_group_alerts
SET first_seen_at = created_at
WHERE first_seen_at IS NULL;

-- Add index for efficient time-based queries
CREATE INDEX IF NOT EXISTS idx_token_group_alerts_last_alert_at
ON token_group_alerts(last_alert_at DESC)
WHERE last_alert_at IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN token_group_alerts.first_seen_at IS 'Timestamp when this token was first detected in this source';
COMMENT ON COLUMN token_group_alerts.last_alert_at IS 'Timestamp of the most recent gain alert sent for this token/source combination';
COMMENT ON COLUMN token_group_alerts.last_alert_message_id IS 'Message ID of the last gain alert sent to this source';
