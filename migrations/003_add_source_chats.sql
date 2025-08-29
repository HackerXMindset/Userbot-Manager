-- Add source chats table for monitoring channels/groups
CREATE TABLE IF NOT EXISTS source_chats (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    source_chat_id BIGINT NOT NULL,
    source_type TEXT CHECK (source_type IN ('channel', 'group')) NOT NULL,
    title TEXT,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, source_chat_id)
);

-- Add source chat users for filtering group messages by specific users
CREATE TABLE IF NOT EXISTS source_chat_users (
    id BIGSERIAL PRIMARY KEY,
    source_chat_id BIGINT REFERENCES source_chats(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    username TEXT,
    first_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(source_chat_id, user_id)
);

-- Create indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_source_chats_group_id ON source_chats(group_id);
CREATE INDEX IF NOT EXISTS idx_source_chats_enabled ON source_chats(enabled);
CREATE INDEX IF NOT EXISTS idx_source_chat_users_source ON source_chat_users(source_chat_id);
CREATE INDEX IF NOT EXISTS idx_source_chat_users_user ON source_chat_users(user_id);