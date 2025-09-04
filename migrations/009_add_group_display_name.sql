-- Add display_name field to groups table for user-friendly group names
ALTER TABLE groups ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Set display_name for existing groups using their title (if available)
UPDATE groups 
SET display_name = CASE 
    WHEN title IS NOT NULL AND title != '' 
        THEN title
    ELSE CONCAT('Group ', tg_chat_id)
END
WHERE display_name IS NULL;