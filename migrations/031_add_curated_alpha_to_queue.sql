-- Add a column to link call_queue jobs to curated_alpha_rules
ALTER TABLE call_queue
ADD COLUMN curated_alpha_rule_id INTEGER REFERENCES curated_alpha_rules(id) ON DELETE SET NULL;

-- Make the old routing_rule_id nullable to support curated calls
ALTER TABLE call_queue
ALTER COLUMN routing_rule_id DROP NOT NULL;

COMMENT ON COLUMN call_queue.curated_alpha_rule_id IS 'The curated alpha rule that triggered this call, if applicable.';
