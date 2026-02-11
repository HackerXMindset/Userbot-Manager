-- Add per-route summary reply toggle for forwards

ALTER TABLE routing_rules
    ADD COLUMN IF NOT EXISTS forward_summary BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN routing_rules.forward_summary IS
    'When true, forward bots send a follow-up summary message after forwarding';
