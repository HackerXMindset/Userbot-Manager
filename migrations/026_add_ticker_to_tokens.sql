ALTER TABLE tokens_tracked
ADD COLUMN ticker VARCHAR(32);

CREATE INDEX IF NOT EXISTS idx_tokens_tracked_ticker ON tokens_tracked (ticker);
