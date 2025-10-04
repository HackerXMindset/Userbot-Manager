-- Create table for storing preset reply messages for dynamic auto-click rules

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='dynamic_reply_messages') THEN
        CREATE TABLE dynamic_reply_messages (
            id SERIAL PRIMARY KEY,
            message_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );

        CREATE INDEX idx_dynamic_reply_messages_created
            ON dynamic_reply_messages(created_at);
    END IF;
END $$;
