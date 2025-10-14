-- Adds forwarded_message_id column to token_call_history for gain-alert threading

ALTER TABLE token_call_history
    ADD COLUMN IF NOT EXISTS forwarded_message_id BIGINT;

CREATE INDEX IF NOT EXISTS idx_token_call_history_target_msg
    ON token_call_history(target_chat_id, forwarded_message_id);

COMMENT ON COLUMN token_call_history.forwarded_message_id
    IS 'Message ID of the forwarded token call inside the target chat for threaded gain alerts';
