-- PNL forwarding rules table
CREATE TABLE IF NOT EXISTS pnl_forwarding_rules (
    id BIGSERIAL PRIMARY KEY,
    source_group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    destination_channel_id BIGINT NOT NULL,
    allowed_user_ids BIGINT[] NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for efficient lookups by source group
CREATE INDEX idx_pnl_forwarding_source_group ON pnl_forwarding_rules(source_group_id);

-- Index for enabled rules
CREATE INDEX idx_pnl_forwarding_enabled ON pnl_forwarding_rules(enabled);