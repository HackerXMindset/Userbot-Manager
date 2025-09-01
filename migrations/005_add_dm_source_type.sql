-- Add DM support to source_type enum
ALTER TABLE source_chats 
DROP CONSTRAINT IF EXISTS source_chats_source_type_check;

ALTER TABLE source_chats 
ADD CONSTRAINT source_chats_source_type_check 
CHECK (source_type IN ('channel', 'group', 'dm'));