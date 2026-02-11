-- Remove market cap alert system artifacts

-- Drop alert configuration columns from targets table
ALTER TABLE targets
    DROP COLUMN IF EXISTS alerts_enabled,
    DROP COLUMN IF EXISTS alerts_modes,
    DROP COLUMN IF EXISTS alerts_thresholds,
    DROP COLUMN IF EXISTS alerts_sensitivity_percent;

-- Drop alert state tracking table and indexes
DROP INDEX IF EXISTS idx_target_token_alert_state_token_id;
DROP INDEX IF EXISTS idx_target_token_alert_state_target_id;
DROP TABLE IF EXISTS target_token_alert_state;

-- Remove legacy drop percentage setting
DELETE FROM settings WHERE key = 'drop_percentage';
