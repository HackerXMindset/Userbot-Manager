-- Migration 071: Add Chart Guardrails Configuration (Phase 1)
-- Created: 2025-10-16
-- Purpose: Introduce additional guardrails (age, liquidity, volume, stability)
-- before fetching charts for gain alerts

-- Step 1: Add chart_guardrails JSONB to settings table
-- This will store global defaults:
-- {
--   "min_age_minutes": number,
--   "min_liquidity_usd": number,
--   "min_volume_usd": number,
--   "min_multiplier": number,
--   "max_price_change_pct": number,
--   "checks_required": number (how many checks must pass, 0 = all must pass)
-- }
-- This setting will be loaded via config helpers and managed through management bot UI

-- Step 2: Add nullable override columns to monitored_sources
-- These allow per-source fine-tuning of chart guardrails
ALTER TABLE monitored_sources
    ADD COLUMN IF NOT EXISTS chart_min_age_minutes INT,
    ADD COLUMN IF NOT EXISTS chart_min_liquidity_usd NUMERIC(20, 2),
    ADD COLUMN IF NOT EXISTS chart_min_volume_usd NUMERIC(20, 2),
    ADD COLUMN IF NOT EXISTS chart_min_multiplier NUMERIC(10, 5),
    ADD COLUMN IF NOT EXISTS chart_max_price_change_pct NUMERIC(6, 3),
    ADD COLUMN IF NOT EXISTS chart_checks_required INT;

-- Add constraints to ensure sensible values
DO $$
BEGIN
    -- Age must be positive
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_min_age_positive'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_min_age_positive
        CHECK (chart_min_age_minutes IS NULL OR chart_min_age_minutes >= 0);
    END IF;

    -- Liquidity must be positive
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_min_liquidity_positive'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_min_liquidity_positive
        CHECK (chart_min_liquidity_usd IS NULL OR chart_min_liquidity_usd >= 0);
    END IF;

    -- Volume must be positive
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_min_volume_positive'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_min_volume_positive
        CHECK (chart_min_volume_usd IS NULL OR chart_min_volume_usd >= 0);
    END IF;

    -- Multiplier must be >= 1.0
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_min_multiplier_valid'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_min_multiplier_valid
        CHECK (chart_min_multiplier IS NULL OR chart_min_multiplier >= 1.0);
    END IF;

    -- Price change pct must be between 0 and 100
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_max_price_change_valid'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_max_price_change_valid
        CHECK (chart_max_price_change_pct IS NULL OR (chart_max_price_change_pct >= 0 AND chart_max_price_change_pct <= 100));
    END IF;

    -- Checks required must be between 0 and 6 (we have 6 checks total)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_checks_required_valid'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_checks_required_valid
        CHECK (chart_checks_required IS NULL OR (chart_checks_required >= 0 AND chart_checks_required <= 6));
    END IF;
END $$;

-- Create indexes for override queries (optional, for performance)
CREATE INDEX IF NOT EXISTS idx_monitored_sources_chart_overrides
    ON monitored_sources(id)
    WHERE chart_min_age_minutes IS NOT NULL
       OR chart_min_liquidity_usd IS NOT NULL
       OR chart_min_volume_usd IS NOT NULL
       OR chart_min_multiplier IS NOT NULL
       OR chart_max_price_change_pct IS NOT NULL
       OR chart_checks_required IS NOT NULL;

-- Insert default global chart_guardrails if not exists
-- Setting lenient defaults to avoid disruption during rollout
INSERT INTO settings (key, value) VALUES (
    'chart_guardrails',
    jsonb_build_object(
        'min_age_minutes', 5,           -- Token must be at least 5 minutes old
        'min_liquidity_usd', 10000,     -- $10k minimum liquidity
        'min_volume_usd', 5000,         -- $5k minimum 24h volume
        'min_multiplier', 1.5,          -- At least 1.5x from first seen
        'max_price_change_pct', 50,     -- Max 50% price change (volatility check)
        'checks_required', 0            -- 0 = all checks must pass (strictest)
    )
)
ON CONFLICT (key) DO NOTHING;
