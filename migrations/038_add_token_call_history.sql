-- Create token call history table to track all successful calls for {call_history} placeholder
-- This table logs every successful call made to show in template history

CREATE TABLE IF NOT EXISTS token_call_history (
    id BIGSERIAL PRIMARY KEY,
    token_address TEXT NOT NULL,
    caller_user_id BIGINT,
    caller_name TEXT,
    source_chat_id BIGINT NOT NULL,
    source_name TEXT,
    source_type TEXT CHECK (source_type IN ('channel', 'group', 'dm')),
    target_chat_id BIGINT NOT NULL,
    forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    routing_rule_id BIGINT REFERENCES routing_rules(id) ON DELETE SET NULL,
    curated_alpha_rule_id INTEGER REFERENCES curated_alpha_rules(id) ON DELETE SET NULL,
    market_cap_at_call BIGINT, -- Market cap in USD cents for precise storage
    call_job_id BIGINT, -- Reference to the original call_queue job
    called_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Primary indexes for performance
CREATE INDEX IF NOT EXISTS idx_token_call_history_token_address ON token_call_history(token_address);
CREATE INDEX IF NOT EXISTS idx_token_call_history_called_at ON token_call_history(called_at DESC);
CREATE INDEX IF NOT EXISTS idx_token_call_history_token_time ON token_call_history(token_address, called_at DESC);
CREATE INDEX IF NOT EXISTS idx_token_call_history_source_chat ON token_call_history(source_chat_id);

-- Compound index for efficient history queries (token + recent calls)
CREATE INDEX IF NOT EXISTS idx_token_call_history_recent ON token_call_history(token_address, called_at DESC);

-- Table and column comments for documentation
COMMENT ON TABLE token_call_history IS 'Logs all successful token calls for template history display';
COMMENT ON COLUMN token_call_history.token_address IS 'The Solana token address that was called';
COMMENT ON COLUMN token_call_history.caller_user_id IS 'Telegram user ID who initiated the original call';
COMMENT ON COLUMN token_call_history.caller_name IS 'Display name of the caller at time of call';
COMMENT ON COLUMN token_call_history.source_chat_id IS 'Telegram chat ID where the token was originally detected';
COMMENT ON COLUMN token_call_history.source_name IS 'Display name of the source chat at time of call';
COMMENT ON COLUMN token_call_history.source_type IS 'Type of source: channel, group, or dm';
COMMENT ON COLUMN token_call_history.target_chat_id IS 'Telegram chat ID where the call was sent';
COMMENT ON COLUMN token_call_history.market_cap_at_call IS 'Token market cap in USD cents when call was made';
COMMENT ON COLUMN token_call_history.call_job_id IS 'Reference to the call_queue job that generated this call';
COMMENT ON COLUMN token_call_history.called_at IS 'Timestamp when the call was successfully sent';