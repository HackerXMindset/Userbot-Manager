-- Migration 072: Fix Chart Guardrails Issues
-- Created: 2025-10-16
-- Purpose: Fix useless partial index and incorrect check count constraint

-- Drop the useless partial index on id (primary key already covers lookups)
DROP INDEX IF EXISTS idx_monitored_sources_chart_overrides;

-- Fix chart_checks_required constraint to cap at 5 (actual number of checks)
-- We have 5 checks: age, liquidity, volume, multiplier, price_change
ALTER TABLE monitored_sources
DROP CONSTRAINT IF EXISTS chart_checks_required_valid;

ALTER TABLE monitored_sources
ADD CONSTRAINT chart_checks_required_valid
CHECK (chart_checks_required IS NULL OR (chart_checks_required >= 0 AND chart_checks_required <= 5));
