-- Add columns to support the new two-stage PNL reply logic
ALTER TABLE pnl_tracked_messages ADD COLUMN IF NOT EXISTS reply_sender_id BIGINT;
ALTER TABLE pnl_tracked_messages ADD COLUMN IF NOT EXISTS last_reply_message_id BIGINT;

-- Add index for the new lookup pattern
CREATE INDEX IF NOT EXISTS idx_pnl_awaiting_reply ON pnl_tracked_messages (chat_id, reply_sender_id, status);
