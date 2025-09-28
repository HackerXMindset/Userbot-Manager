-- Phase 1: Database & Model Foundations for Sensitivity-Based Gain Alerts
-- Add per-target alert configuration and target+token alert state tracking

-- Step 1: Add alert configuration columns to targets table
ALTER TABLE targets
ADD COLUMN IF NOT EXISTS alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE targets
ADD COLUMN IF NOT EXISTS alerts_modes JSONB NOT NULL DEFAULT '{"pnl": true, "dynamic": true, "threshold": true, "sensitivity": true}';

ALTER TABLE targets
ADD COLUMN IF NOT EXISTS alerts_thresholds JSONB NOT NULL DEFAULT '[2,7,25]';

ALTER TABLE targets
ADD COLUMN IF NOT EXISTS alerts_sensitivity_percent NUMERIC(6,4) NOT NULL DEFAULT 0.50;

-- Update existing targets with default values (idempotent)
UPDATE targets SET
    alerts_enabled = COALESCE(alerts_enabled, TRUE),
    alerts_modes = COALESCE(alerts_modes, '{"pnl": true, "dynamic": true, "threshold": true, "sensitivity": true}'::jsonb),
    alerts_thresholds = COALESCE(alerts_thresholds, '[2,7,25]'::jsonb),
    alerts_sensitivity_percent = COALESCE(alerts_sensitivity_percent, 0.50)
WHERE alerts_enabled IS NULL
   OR alerts_modes IS NULL
   OR alerts_thresholds IS NULL
   OR alerts_sensitivity_percent IS NULL;

-- Step 2: Create target_token_alert_state table for tracking alert history per target+token pair
CREATE TABLE IF NOT EXISTS target_token_alert_state (
    id BIGSERIAL PRIMARY KEY,
    target_id BIGINT REFERENCES targets(id) ON DELETE CASCADE,
    token_id BIGINT REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    first_message_id BIGINT,
    first_sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    initial_market_cap NUMERIC,
    last_alert_multiplier NUMERIC NOT NULL DEFAULT 1,
    last_alert_at TIMESTAMPTZ,
    UNIQUE(target_id, token_id)
);

-- Add index on token_id to accelerate Dex scan lookups
CREATE INDEX IF NOT EXISTS idx_target_token_alert_state_token_id
ON target_token_alert_state(token_id);

-- Add index on target_id for per-target queries
CREATE INDEX IF NOT EXISTS idx_target_token_alert_state_target_id
ON target_token_alert_state(target_id);

-- Add comments for documentation
COMMENT ON COLUMN targets.alerts_enabled IS 'Enable/disable all alerts for this target';
COMMENT ON COLUMN targets.alerts_modes IS 'JSON object controlling which alert types are enabled: {"pnl": bool, "dynamic": bool, "threshold": bool, "sensitivity": bool}';
COMMENT ON COLUMN targets.alerts_thresholds IS 'JSON array of threshold multipliers for traditional alerts: [2,7,25]';
COMMENT ON COLUMN targets.alerts_sensitivity_percent IS 'Sensitivity percentage for dynamic alerts (0.50 = 50% = alerts at 1.5x, 2.25x, 3.375x, etc.)';

COMMENT ON TABLE target_token_alert_state IS 'Tracks alert state per target+token pair for sensitivity-based alerts';
COMMENT ON COLUMN target_token_alert_state.first_message_id IS 'Message ID of first call sent to this target for this token (for reply threading)';
COMMENT ON COLUMN target_token_alert_state.initial_market_cap IS 'Market cap when first call was sent (baseline for sensitivity calculations)';
COMMENT ON COLUMN target_token_alert_state.last_alert_multiplier IS 'Last multiplier at which an alert was sent (for sensitivity progression)';