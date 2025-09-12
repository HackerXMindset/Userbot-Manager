-- Simplify PNL forwarding permissions into a single user list
-- 1. Rename the primary user list for clarity
ALTER TABLE pnl_forwarding_rules RENAME COLUMN allowed_pnl_user_ids TO authorized_user_ids;

-- 2. Drop the now-redundant second user list
ALTER TABLE pnl_forwarding_rules DROP COLUMN IF EXISTS allowed_user_ids;

COMMENT ON COLUMN pnl_forwarding_rules.authorized_user_ids IS 'The list of user IDs authorized to initiate a PNL command that will be tracked.';
