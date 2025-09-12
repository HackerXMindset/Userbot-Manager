-- Add allowed PNL user IDs to forwarding rules
ALTER TABLE pnl_forwarding_rules 
ADD COLUMN IF NOT EXISTS allowed_pnl_user_ids BIGINT[] NOT NULL DEFAULT '{}';