-- Add name column to auto_button_click_rules for custom rule identification

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='name') THEN
        ALTER TABLE auto_button_click_rules ADD COLUMN name TEXT;
    END IF;
END $$;
