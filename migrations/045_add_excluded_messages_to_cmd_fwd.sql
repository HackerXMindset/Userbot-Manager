-- Add excluded message texts blacklist for command forwarding rules
ALTER TABLE command_forwarding_rules
ADD COLUMN IF NOT EXISTS excluded_message_texts TEXT[] DEFAULT '{}';

COMMENT ON COLUMN command_forwarding_rules.excluded_message_texts IS 'List of exact message texts (case-sensitive) that should NOT be forwarded even if they match the reply criteria';
