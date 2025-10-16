-- Backfill token_call_history from existing calls table
-- This migration copies historical call data from the old 'calls' table to the new 'token_call_history' table
-- to ensure the inspector shows all historical forwarding activity

-- Insert historical calls from 'calls' table into 'token_call_history'
INSERT INTO token_call_history (
    token_address,
    caller_user_id,
    caller_name,
    source_chat_id,
    source_name,
    source_type,
    target_chat_id,
    forwarding_userbot_id,
    routing_rule_id,
    curated_alpha_rule_id,
    market_cap_at_call,
    call_job_id,
    forwarded_message_id,
    called_at,
    created_at,
    updated_at
)
SELECT
    tt.address AS token_address,
    NULL AS caller_user_id,        -- Not tracked in old calls table
    NULL AS caller_name,            -- Not tracked in old calls table
    COALESCE(g.tg_chat_id, c.group_id) AS source_chat_id,
    COALESCE(g.display_name, g.title, 'Group ' || c.group_id::TEXT) AS source_name,
    'group' AS source_type,         -- Assume all legacy calls were from groups
    t.dest_chat_id AS target_chat_id,
    c.userbot_id AS forwarding_userbot_id,
    NULL AS routing_rule_id,        -- Not tracked in old calls table
    NULL AS curated_alpha_rule_id,  -- Not tracked in old calls table
    NULL AS market_cap_at_call,     -- Not tracked in old calls table
    NULL AS call_job_id,            -- Legacy calls weren't queued
    c.message_id AS forwarded_message_id,
    COALESCE(c.sent_at, c.scheduled_at) AS called_at,
    c.created_at AS created_at,
    c.created_at AS updated_at
FROM calls c
INNER JOIN tokens_tracked tt ON tt.id = c.token_id
LEFT JOIN targets t ON t.id = c.target_id
LEFT JOIN groups g ON g.id = c.group_id
WHERE c.status = 'sent'
  AND c.sent_at IS NOT NULL
  -- Only backfill if this call doesn't already exist in token_call_history
  AND NOT EXISTS (
      SELECT 1
      FROM token_call_history tch
      WHERE tch.token_address = tt.address
        AND tch.target_chat_id = t.dest_chat_id
        AND tch.forwarded_message_id = c.message_id
        AND tch.called_at = COALESCE(c.sent_at, c.scheduled_at)
  );

-- Log the number of records backfilled
DO $$
DECLARE
    backfilled_count INT;
BEGIN
    GET DIAGNOSTICS backfilled_count = ROW_COUNT;
    RAISE NOTICE 'Backfilled % historical call records from calls table to token_call_history', backfilled_count;
END $$;
