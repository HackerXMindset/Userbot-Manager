-- Fix source_chat_id constraint to allow nullable values
-- Some calls may not have a source chat (e.g., manually created calls)

ALTER TABLE token_call_history
ALTER COLUMN source_chat_id DROP NOT NULL;

-- Add comment for clarity
COMMENT ON COLUMN token_call_history.source_chat_id IS 'Telegram chat ID where the token was originally detected (nullable for calls without source)';