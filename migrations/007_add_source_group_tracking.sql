-- Add source group tracking to tokens_tracked table
ALTER TABLE tokens_tracked 
ADD COLUMN IF NOT EXISTS source_group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_tokens_source_group ON tokens_tracked(source_group_id);

-- Update existing tokens to NULL (they won't have source group info)
UPDATE tokens_tracked SET source_group_id = NULL WHERE source_group_id IS NULL;