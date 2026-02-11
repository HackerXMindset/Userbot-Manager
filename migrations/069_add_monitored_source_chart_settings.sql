-- Add chart-related columns to monitored_sources
ALTER TABLE monitored_sources
ADD COLUMN IF NOT EXISTS chart_enabled BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS chart_bot_id BIGINT,
ADD COLUMN IF NOT EXISTS chart_mc_threshold NUMERIC(20, 2) DEFAULT 100000.00;

-- Index for chart bot queries
CREATE INDEX IF NOT EXISTS idx_monitored_sources_chart_bot ON monitored_sources(chart_bot_id) WHERE chart_bot_id IS NOT NULL;
