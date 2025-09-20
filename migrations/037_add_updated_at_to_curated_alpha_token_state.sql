-- Add missing updated_at column to curated_alpha_token_state table
-- This column is required by the base model for tracking record updates

ALTER TABLE curated_alpha_token_state
ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL;

-- Add index for performance
CREATE INDEX IF NOT EXISTS idx_curated_alpha_token_state_updated_at ON curated_alpha_token_state(updated_at);

-- Add comment for clarity
COMMENT ON COLUMN curated_alpha_token_state.updated_at IS 'Timestamp when the record was last updated';