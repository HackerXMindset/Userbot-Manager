-- Command forwarding rules table for dynamic command forwarding and scheduling
CREATE TABLE IF NOT EXISTS command_forwarding_rules (
    id BIGSERIAL PRIMARY KEY,
    source_group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    command_text TEXT NOT NULL, -- The exact command to monitor (e.g., "/lb 1h", "/dp", "any custom text")
    destination_channel_id BIGINT NOT NULL,
    allowed_command_user_ids BIGINT[], -- User IDs who can send the command that will be tracked
    allowed_reply_user_ids BIGINT[], -- User IDs whose replies to the command should be forwarded
    forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,

    -- Scheduling configuration
    schedule_enabled BOOLEAN DEFAULT false,
    schedule_interval_minutes INTEGER, -- Interval in minutes (60=1h, 360=6h, 1440=24h, etc.)
    last_scheduled_at TIMESTAMPTZ,
    next_scheduled_at TIMESTAMPTZ,

    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for efficient lookups
CREATE INDEX idx_command_forwarding_source_group ON command_forwarding_rules(source_group_id);
CREATE INDEX idx_command_forwarding_enabled ON command_forwarding_rules(enabled);
CREATE INDEX idx_command_forwarding_schedule ON command_forwarding_rules(schedule_enabled, next_scheduled_at) WHERE schedule_enabled = true;
CREATE INDEX idx_command_forwarding_userbot ON command_forwarding_rules(forwarding_userbot_id);

-- Comments for clarity
COMMENT ON TABLE command_forwarding_rules IS 'Rules for forwarding replies to custom commands and scheduling automatic command sending';
COMMENT ON COLUMN command_forwarding_rules.command_text IS 'The exact command text to monitor (e.g., "/lb 1h", "/dp", "custom command")';
COMMENT ON COLUMN command_forwarding_rules.allowed_command_user_ids IS 'User IDs authorized to send the command that will be tracked';
COMMENT ON COLUMN command_forwarding_rules.allowed_reply_user_ids IS 'User IDs whose replies to tracked commands should be forwarded';
COMMENT ON COLUMN command_forwarding_rules.schedule_interval_minutes IS 'How often to automatically send the command (in minutes)';