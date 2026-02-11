-- Add is_first_message flag to track original forwarded message per token/chat

ALTER TABLE token_call_history
    ADD COLUMN IF NOT EXISTS is_first_message BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_token_call_history_first_msg
    ON token_call_history(token_address, target_chat_id, is_first_message);

UPDATE token_call_history tch
SET is_first_message = TRUE
FROM (
    SELECT token_address, target_chat_id, MIN(called_at) AS first_called
    FROM token_call_history
    WHERE target_chat_id IS NOT NULL
    GROUP BY token_address, target_chat_id
) firsts
WHERE tch.token_address = firsts.token_address
  AND tch.target_chat_id = firsts.target_chat_id
  AND tch.called_at = firsts.first_called;
