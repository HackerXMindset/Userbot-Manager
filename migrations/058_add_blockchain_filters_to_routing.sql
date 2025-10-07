-- Add blockchain filtering to routing rules and call queue
-- Phase 1: Multi-Blockchain Support

-- Add allowed_chains column to routing_rules
ALTER TABLE routing_rules
ADD COLUMN allowed_chains JSONB NOT NULL DEFAULT '["SOL"]'::jsonb
CHECK (jsonb_array_length(allowed_chains) > 0);

-- Add allowed_chains column to curated_alpha_rules
ALTER TABLE curated_alpha_rules
ADD COLUMN allowed_chains JSONB NOT NULL DEFAULT '["SOL"]'::jsonb
CHECK (jsonb_array_length(allowed_chains) > 0);

-- Add blockchain column to call_queue to track which chain each token belongs to
ALTER TABLE call_queue
ADD COLUMN blockchain VARCHAR(10);

-- Create index for faster blockchain filtering queries
CREATE INDEX idx_routing_rules_allowed_chains ON routing_rules USING GIN (allowed_chains);
CREATE INDEX idx_curated_alpha_rules_allowed_chains ON curated_alpha_rules USING GIN (allowed_chains);
CREATE INDEX idx_call_queue_blockchain ON call_queue (blockchain);

-- Add comment for documentation
COMMENT ON COLUMN routing_rules.allowed_chains IS 'JSONB array of allowed blockchain identifiers (e.g., ["SOL", "BNB"])';
COMMENT ON COLUMN curated_alpha_rules.allowed_chains IS 'JSONB array of allowed blockchain identifiers (e.g., ["SOL", "BNB"])';
COMMENT ON COLUMN call_queue.blockchain IS 'Blockchain identifier for the token (SOL, BNB, etc.)';
