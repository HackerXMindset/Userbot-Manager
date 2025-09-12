-- Drop the old unique constraint
ALTER TABLE pnl_tracked_messages DROP CONSTRAINT IF EXISTS pnl_tracked_messages_original_message_id_chat_id_key;

-- Add the new unique constraint
ALTER TABLE pnl_tracked_messages ADD CONSTRAINT pnl_tracked_messages_original_message_id_chat_id_rule_id_key UNIQUE (original_message_id, chat_id, rule_id);
