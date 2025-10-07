-- Add blockchain column to forwarded_tokens_log for proper cross-chain deduplication
-- Phase 1.5: Multi-Blockchain Support - Deduplication Enhancement

-- Add blockchain column to forwarded_tokens_log
ALTER TABLE forwarded_tokens_log
ADD COLUMN blockchain VARCHAR(10);

-- Drop old constraint/index if exists
ALTER TABLE forwarded_tokens_log
DROP CONSTRAINT IF EXISTS forwarded_tokens_log_token_address_source_chat_id_key;

DROP INDEX IF EXISTS idx_forwarded_tokens_log_recent;

-- Create new unique constraint with blockchain
CREATE UNIQUE INDEX idx_forwarded_tokens_unique_blockchain
ON forwarded_tokens_log(token_address, source_chat_id, blockchain);

-- Create index for recent lookups with blockchain
CREATE INDEX idx_forwarded_tokens_log_recent_blockchain
ON forwarded_tokens_log(token_address, source_chat_id, blockchain, forwarded_at);

-- Add comment for documentation
COMMENT ON COLUMN forwarded_tokens_log.blockchain IS 'Blockchain identifier (SOL, BNB, etc.) - ensures proper deduplication across chains';
