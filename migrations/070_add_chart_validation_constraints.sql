-- Migration 070: Add validation constraints for chart settings
-- Created: 2025-10-15

-- Ensure chart MC threshold is positive
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_mc_threshold_positive'
    ) THEN
        ALTER TABLE monitored_sources
        ADD CONSTRAINT chart_mc_threshold_positive CHECK (chart_mc_threshold IS NULL OR chart_mc_threshold > 0);
    END IF;
END $$;

-- Ensure chat_id is negative (Telegram groups use negative IDs)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'chart_request_groups_chat_id_negative'
    ) THEN
        ALTER TABLE chart_request_groups
        ADD CONSTRAINT chart_request_groups_chat_id_negative CHECK (chat_id < 0);
    END IF;
END $$;
