-- Add column to store user IDs whose replies should be forwarded
ALTER TABLE pnl_forwarding_rules
ADD COLUMN IF NOT EXISTS allowed_reply_user_ids BIGINT[];

-- Rename for clarity based on new multi-user model
ALTER TABLE pnl_forwarding_rules RENAME COLUMN authorized_user_ids TO allowed_pnl_command_user_ids;


COMMENT ON COLUMN pnl_forwarding_rules.allowed_pnl_command_user_ids IS 'The list of user IDs authorized to initiate a PNL command that will be tracked.';
COMMENT ON COLUMN pnl_forwarding_rules.allowed_reply_user_ids IS 'The list of user IDs whose replies to a tracked PNL command should be forwarded.';
