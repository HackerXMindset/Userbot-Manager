-- Migration 073: Add last_guardrail_result column to monitored_sources table
-- Created: 2025-10-16
-- Purpose: Store the result of the last guardrail evaluation for admin visibility

-- Add the column to monitored_sources table
ALTER TABLE monitored_sources
ADD COLUMN IF NOT EXISTS last_guardrail_result JSONB;

-- Add comment to document the column
COMMENT ON COLUMN monitored_sources.last_guardrail_result IS 'Stores the result of the last chart guardrail evaluation (pass/fail, checks summary)';