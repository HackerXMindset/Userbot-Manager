-- Add toggle to control media forwarding per route

ALTER TABLE routing_rules
    ADD COLUMN IF NOT EXISTS forward_media BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN routing_rules.forward_media IS
    'When false, token calls forward only text content; media attachments are skipped.';
