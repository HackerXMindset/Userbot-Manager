-- Migration 067: Track management bot as gain alert sender option
-- Created: 2025-02-21

ALTER TABLE monitored_sources
    ADD COLUMN IF NOT EXISTS use_management_bot BOOLEAN NOT NULL DEFAULT FALSE;

