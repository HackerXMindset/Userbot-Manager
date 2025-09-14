-- Add auto_button_click_rules table
CREATE TABLE IF NOT EXISTS auto_button_click_rules (
    id SERIAL PRIMARY KEY,
    target_chat_id BIGINT NOT NULL,
    bot_id BIGINT NOT NULL,
    button_text TEXT NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Add message_id to calls table
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='calls' AND column_name='message_id') THEN
        ALTER TABLE calls ADD COLUMN message_id BIGINT;
    END IF;
END $$;
