-- Migration 064: Add Monitored Sources for Gain Alerts
-- Created: 2025-10-15

-- Create monitored_sources table
CREATE TABLE IF NOT EXISTS monitored_sources (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL,
    chat_type TEXT NOT NULL CHECK (chat_type IN ('group', 'channel', 'dm')),
    user_id BIGINT,
    added_by_admin_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (
        (chat_type = 'group' AND user_id IS NOT NULL)
        OR (chat_type IN ('channel', 'dm') AND user_id IS NULL)
    ),
    UNIQUE(chat_id, user_id)
);

-- Create indexes for monitored_sources
CREATE INDEX IF NOT EXISTS idx_monitored_sources_chat ON monitored_sources(chat_id);
CREATE INDEX IF NOT EXISTS idx_monitored_sources_user ON monitored_sources(user_id) WHERE user_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_monitored_sources_unique_channel_dm
    ON monitored_sources(chat_id)
    WHERE user_id IS NULL;

-- Create token_group_alerts table
CREATE TABLE IF NOT EXISTS token_group_alerts (
    id SERIAL PRIMARY KEY,
    token_id INT NOT NULL REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    chat_id BIGINT NOT NULL,
    first_seen_mc NUMERIC(20, 2) NOT NULL,
    last_alert_mc NUMERIC(20, 2),
    original_message_id BIGINT NOT NULL,
    original_user_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(token_id, chat_id)
);

-- Create indexes for token_group_alerts
CREATE INDEX IF NOT EXISTS idx_token_group_alerts_token ON token_group_alerts(token_id);
CREATE INDEX IF NOT EXISTS idx_token_group_alerts_chat ON token_group_alerts(chat_id);
CREATE INDEX IF NOT EXISTS idx_token_group_alerts_lookup ON token_group_alerts(token_id, chat_id);
