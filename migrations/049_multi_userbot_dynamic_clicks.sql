-- Adds support for multiple userbots in dynamic click rules.

-- Step 1: Add the new JSONB column to store an array of userbot IDs.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='clicking_userbot_ids') THEN
        ALTER TABLE auto_button_click_rules ADD COLUMN clicking_userbot_ids JSONB;
    END IF;
END $$;

-- Step 2: Migrate data from the old single-ID column to the new JSONB array column.
-- This converts a single ID like 8 into a JSON array like [8].
-- This block only runs if the old column still exists to ensure idempotency.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='clicking_userbot_id') THEN
        UPDATE auto_button_click_rules
        SET clicking_userbot_ids = jsonb_build_array(clicking_userbot_id)
        WHERE clicking_userbot_id IS NOT NULL AND rule_type = 'dynamic';
    END IF;
END $$;

-- Step 3: Drop the old, now-redundant column.
-- This block is also idempotent.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='auto_button_click_rules' AND column_name='clicking_userbot_id') THEN
        ALTER TABLE auto_button_click_rules DROP COLUMN clicking_userbot_id;
    END IF;
END $$;
