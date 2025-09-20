-- Add required_mentions column to curated_alpha_rules
-- This allows specifying a minimum number of source mentions to trigger a rule,
-- instead of requiring all of them.
-- A NULL or 0 value indicates that all sources are required (maintaining backward compatibility).
ALTER TABLE curated_alpha_rules
ADD COLUMN IF NOT EXISTS required_mentions INTEGER;
