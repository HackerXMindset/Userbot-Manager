-- Add forwarding mode and keyword filtering to routing rules

ALTER TABLE routing_rules
    ADD COLUMN IF NOT EXISTS forwarding_mode TEXT NOT NULL DEFAULT 'tokens'
        CHECK (forwarding_mode IN ('tokens', 'keywords', 'everything')),
    ADD COLUMN IF NOT EXISTS keyword_filters JSONB NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(keyword_filters) = 'array');

COMMENT ON COLUMN routing_rules.forwarding_mode IS
    'Determines how the route forwards messages: tokens (default), keywords, or everything';

COMMENT ON COLUMN routing_rules.keyword_filters IS
    'JSON array of case-insensitive keyword filters applied when forwarding_mode = keywords';
