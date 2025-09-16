-- Table to store the "Curate Alpha" rules
CREATE TABLE IF NOT EXISTS curated_alpha_rules (
    id SERIAL PRIMARY KEY,
    name TEXT,
    required_source_chat_ids BIGINT[] NOT NULL,
    destination_chat_id BIGINT NOT NULL,
    forwarding_userbot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL,
    forward_pnl_alerts BOOLEAN DEFAULT FALSE NOT NULL,
    time_window_seconds INTEGER DEFAULT 300 NOT NULL,
    enabled BOOLEAN DEFAULT TRUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_curated_alpha_rules_enabled ON curated_alpha_rules (enabled);
COMMENT ON TABLE curated_alpha_rules IS 'Stores rules for conditional forwarding based on a token appearing in multiple sources.';
COMMENT ON COLUMN curated_alpha_rules.required_source_chat_ids IS 'Array of source chat IDs where a token must appear.';
COMMENT ON COLUMN curated_alpha_rules.time_window_seconds IS 'Time in seconds to wait for a token to appear in all required sources.';


-- Table to track the real-time state of tokens against the rules
CREATE TABLE IF NOT EXISTS curated_alpha_token_state (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES curated_alpha_rules(id) ON DELETE CASCADE,
    token_address TEXT NOT NULL,
    seen_in_source_chat_ids BIGINT[] NOT NULL,
    first_seen_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    status TEXT NOT NULL DEFAULT 'tracking', -- tracking, triggered, expired
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_curated_alpha_token_state_rule_token ON curated_alpha_token_state (rule_id, token_address);
CREATE INDEX IF NOT EXISTS idx_curated_alpha_token_state_status ON curated_alpha_token_state (status);
CREATE INDEX IF NOT EXISTS idx_curated_alpha_token_state_first_seen ON curated_alpha_token_state (first_seen_at);
COMMENT ON TABLE curated_alpha_token_state IS 'Tracks the state of tokens as they are detected against curated alpha rules.';
COMMENT ON COLUMN curated_alpha_token_state.status IS 'The current state of the token for this rule: tracking, triggered, or expired.';
