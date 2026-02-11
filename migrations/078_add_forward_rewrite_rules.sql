-- Add text rewrite rules to routing rules for message customization

ALTER TABLE routing_rules
    ADD COLUMN IF NOT EXISTS forward_rewrite_rules JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(forward_rewrite_rules) = 'array');

COMMENT ON COLUMN routing_rules.forward_rewrite_rules IS
    'JSON array of replacement rules applied to message text before forwarding when overrides are enabled';
