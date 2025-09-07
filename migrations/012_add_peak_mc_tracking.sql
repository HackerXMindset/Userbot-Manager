-- Add peak market cap tracking for stop-loss functionality
ALTER TABLE tokens_tracked 
ADD COLUMN IF NOT EXISTS peak_mc NUMERIC DEFAULT 0;

-- Initialize peak_mc for existing tokens
UPDATE tokens_tracked 
SET peak_mc = GREATEST(COALESCE(first_seen_mc, 0), COALESCE(last_mc, 0))
WHERE peak_mc = 0;