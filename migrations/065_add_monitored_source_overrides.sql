-- Migration 065: Add per-source override fields and target routing for gain alerts
-- Created: 2025-02-17

-- Add override columns to monitored_sources
ALTER TABLE monitored_sources
    ADD COLUMN IF NOT EXISTS display_name TEXT,
    ADD COLUMN IF NOT EXISTS is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS sensitivity_pct NUMERIC(6, 5),
    ADD COLUMN IF NOT EXISTS assigned_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL;

-- Create table for monitored source targets
CREATE TABLE IF NOT EXISTS monitored_source_targets (
    id SERIAL PRIMARY KEY,
    source_id INT NOT NULL REFERENCES monitored_sources(id) ON DELETE CASCADE,
    target_chat_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_id, target_chat_id)
);

CREATE INDEX IF NOT EXISTS idx_monitored_source_targets_source
    ON monitored_source_targets(source_id);

CREATE INDEX IF NOT EXISTS idx_monitored_source_targets_chat
    ON monitored_source_targets(target_chat_id);
