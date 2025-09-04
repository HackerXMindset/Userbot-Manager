-- Add display_name field to bots table for user-friendly userbot names
ALTER TABLE bots ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Set display_name for existing userbots using their Telegram names
UPDATE bots 
SET display_name = CASE 
    WHEN first_name IS NOT NULL AND last_name IS NOT NULL 
        THEN CONCAT(first_name, ' ', last_name)
    WHEN first_name IS NOT NULL 
        THEN first_name
    WHEN username IS NOT NULL 
        THEN CONCAT('@', username)
    ELSE session_name
END
WHERE kind = 'userbot' AND display_name IS NULL;

-- For any remaining NULL display_names, use session_name as fallback
UPDATE bots SET display_name = session_name WHERE display_name IS NULL;