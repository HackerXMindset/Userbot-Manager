-- Add dynamic click support to auto_button_click_rules

-- Add rule_type column (static or dynamic)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='rule_type') THEN
        ALTER TABLE auto_button_click_rules ADD COLUMN rule_type TEXT DEFAULT 'static';
    END IF;
END $$;

-- Add user_id column (for dynamic rules - which user to monitor)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='user_id') THEN
        ALTER TABLE auto_button_click_rules ADD COLUMN user_id BIGINT;
    END IF;
END $$;

-- Add button_texts column (for dynamic rules - array of button texts)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='button_texts') THEN
        ALTER TABLE auto_button_click_rules ADD COLUMN button_texts JSONB;
    END IF;
END $$;

-- Add clicking_userbot_id column (which userbot performs the clicks)
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='clicking_userbot_id') THEN
        ALTER TABLE auto_button_click_rules ADD COLUMN clicking_userbot_id INTEGER REFERENCES bots(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Backfill existing records as 'static' type
UPDATE auto_button_click_rules SET rule_type = 'static' WHERE rule_type IS NULL;

-- Create indexes for dynamic rule lookups
CREATE INDEX IF NOT EXISTS idx_auto_button_click_rule_type ON auto_button_click_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_auto_button_click_user_id ON auto_button_click_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_auto_button_click_target_user ON auto_button_click_rules(target_chat_id, user_id) WHERE rule_type = 'dynamic';
