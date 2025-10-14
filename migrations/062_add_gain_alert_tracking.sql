-- Phase 1: Add columns for gain alert tracking and tier-based monitoring

-- Add new columns to tokens_tracked table
ALTER TABLE tokens_tracked
ADD COLUMN IF NOT EXISTS last_alert_mc NUMERIC(24,6),
ADD COLUMN IF NOT EXISTS current_tier TEXT DEFAULT 'tier_a',
ADD COLUMN IF NOT EXISTS next_poll_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS stop_reason TEXT,
ADD COLUMN IF NOT EXISTS dex_screener_refreshed_at TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS original_message_id BIGINT;

-- Create index on next_poll_at for scheduler efficiency
CREATE INDEX IF NOT EXISTS idx_tokens_next_poll ON tokens_tracked(next_poll_at) WHERE status = 'active' AND next_poll_at IS NOT NULL;

-- Create index on current_tier for tier-based queries
CREATE INDEX IF NOT EXISTS idx_tokens_current_tier ON tokens_tracked(current_tier) WHERE status = 'active';

-- Initialize last_alert_mc for existing active tokens (set to first_seen_mc as baseline)
UPDATE tokens_tracked
SET last_alert_mc = COALESCE(first_seen_mc, 0)
WHERE status = 'active' AND last_alert_mc IS NULL;

-- Initialize next_poll_at for existing active tokens (set to NOW + 10 seconds for Tier A)
UPDATE tokens_tracked
SET next_poll_at = NOW() + INTERVAL '10 seconds'
WHERE status = 'active' AND next_poll_at IS NULL;

-- Add constraint to ensure current_tier has valid values
ALTER TABLE tokens_tracked
ADD CONSTRAINT check_valid_tier
CHECK (current_tier IN ('tier_a', 'tier_b', 'tier_c', 'tier_d', 'tier_e', 'tier_f') OR current_tier IS NULL);

-- Seed default gain alert settings
INSERT INTO settings (key, value) VALUES
    ('gain_threshold_pct', '0.30'),
    ('drop_threshold_pct', '0.70'),
    ('drop_floor_mc', '8000')
ON CONFLICT (key) DO NOTHING;
