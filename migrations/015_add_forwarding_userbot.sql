-- Add forwarding userbot to PNL forwarding rules
ALTER TABLE pnl_forwarding_rules 
ADD COLUMN IF NOT EXISTS forwarding_userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL;

-- Index for efficient lookups by forwarding userbot
CREATE INDEX IF NOT EXISTS idx_pnl_forwarding_userbot ON pnl_forwarding_rules(forwarding_userbot_id);