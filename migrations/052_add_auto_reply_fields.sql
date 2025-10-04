-- Add auto-reply fields to auto_button_click_rules table

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='auto_reply_enabled') THEN
        ALTER TABLE auto_button_click_rules
            ADD COLUMN auto_reply_enabled BOOLEAN DEFAULT FALSE,
            ADD COLUMN ticker_value TEXT;

        CREATE INDEX idx_auto_button_click_rules_auto_reply
            ON auto_button_click_rules(auto_reply_enabled)
            WHERE auto_reply_enabled = TRUE;
    END IF;
END $$;
