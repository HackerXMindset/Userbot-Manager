-- Convert to global sources system with routing rules

-- Step 1: Make source_chats independent (remove required group_id constraint)
DO $$ 
BEGIN
    BEGIN
        ALTER TABLE source_chats ALTER COLUMN group_id DROP NOT NULL;
    EXCEPTION 
        WHEN OTHERS THEN 
            RAISE NOTICE 'group_id constraint already modified or does not exist';
    END;
END $$;

-- Drop the old unique constraint and create new one for global sources
DO $$ 
BEGIN
    BEGIN
        ALTER TABLE source_chats DROP CONSTRAINT IF EXISTS source_chats_group_id_source_chat_id_key;
        ALTER TABLE source_chats ADD CONSTRAINT source_chats_source_chat_id_key UNIQUE (source_chat_id);
    EXCEPTION 
        WHEN duplicate_table THEN 
            RAISE NOTICE 'Unique constraint already exists';
        WHEN OTHERS THEN 
            RAISE NOTICE 'Constraint modification failed or already done';
    END;
END $$;

-- Step 2: Create routing rules table
CREATE TABLE IF NOT EXISTS routing_rules (
    id BIGSERIAL PRIMARY KEY,
    source_chat_id BIGINT REFERENCES source_chats(id) ON DELETE CASCADE,
    target_group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    enabled BOOLEAN DEFAULT true,
    priority INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_chat_id, target_group_id)
);

-- Step 3: Migrate existing source → group relationships to routing rules
INSERT INTO routing_rules (source_chat_id, target_group_id, enabled, created_at)
SELECT sc.id, sc.group_id, sc.enabled, sc.created_at
FROM source_chats sc
WHERE sc.group_id IS NOT NULL
ON CONFLICT (source_chat_id, target_group_id) DO NOTHING;

-- Step 4: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_routing_rules_source ON routing_rules(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_routing_rules_target ON routing_rules(target_group_id);
CREATE INDEX IF NOT EXISTS idx_routing_rules_enabled ON routing_rules(enabled);

-- Step 5: Add name field to source_chats for better organization
ALTER TABLE source_chats ADD COLUMN IF NOT EXISTS name TEXT;

-- Update names based on existing titles
UPDATE source_chats SET name = title WHERE name IS NULL AND title IS NOT NULL;