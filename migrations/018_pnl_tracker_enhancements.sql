-- Enhance pnl_tracked_messages for the new polling tracker
ALTER TABLE pnl_tracked_messages ADD COLUMN IF NOT EXISTS last_checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Ensure status field can hold new values
-- (No schema change needed if using TEXT, but this is good practice to document)
COMMENT ON COLUMN pnl_tracked_messages.status IS 'Tracking status: tracking, awaiting_final_reply, processing, forwarded, expired';
