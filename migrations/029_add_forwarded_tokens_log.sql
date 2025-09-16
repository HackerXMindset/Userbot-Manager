CREATE TABLE IF NOT EXISTS forwarded_tokens_log (
    id SERIAL PRIMARY KEY,
    token_address TEXT NOT NULL,
    source_chat_id BIGINT NOT NULL,
    forwarded_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_forwarded_tokens_log_address_chat_id
ON forwarded_tokens_log (token_address, source_chat_id);

COMMENT ON TABLE forwarded_tokens_log IS 'Logs tokens that have been forwarded from a source to prevent duplicates.';
COMMENT ON COLUMN forwarded_tokens_log.token_address IS 'The Solana token address that was forwarded.';
COMMENT ON COLUMN forwarded_tokens_log.source_chat_id IS 'The source chat from which the token was detected.';
COMMENT ON COLUMN forwarded_tokens_log.forwarded_at IS 'The timestamp when the token was forwarded.';
