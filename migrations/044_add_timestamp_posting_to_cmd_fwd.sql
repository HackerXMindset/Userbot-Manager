-- Add timestamp posting toggle and timezone selection
ALTER TABLE command_forwarding_rules
ADD COLUMN IF NOT EXISTS post_timestamp BOOLEAN DEFAULT false,
ADD COLUMN IF NOT EXISTS timestamp_timezone VARCHAR(50) DEFAULT 'IST';

COMMENT ON COLUMN command_forwarding_rules.post_timestamp IS 'When enabled, bot will post a timestamp after forwarding the reply message';
COMMENT ON COLUMN command_forwarding_rules.timestamp_timezone IS 'Timezone for timestamp display (IST, UTC, EST, PST, etc.)';