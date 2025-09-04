-- Add display_name field to source_chats table for user-friendly source names
ALTER TABLE source_chats ADD COLUMN IF NOT EXISTS display_name TEXT;

-- Set display_name for existing sources using their name or title (if available)
UPDATE source_chats 
SET display_name = CASE 
    WHEN name IS NOT NULL AND name != '' 
        THEN name
    WHEN title IS NOT NULL AND title != ''
        THEN title
    ELSE CONCAT('Source ', source_chat_id)
END
WHERE display_name IS NULL;