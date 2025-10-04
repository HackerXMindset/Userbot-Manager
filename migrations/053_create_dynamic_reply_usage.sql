-- Create table for tracking per-rule usage of dynamic reply messages

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name='dynamic_reply_usage') THEN
        CREATE TABLE dynamic_reply_usage (
            id SERIAL PRIMARY KEY,
            rule_id INTEGER NOT NULL REFERENCES auto_button_click_rules(id) ON DELETE CASCADE,
            reply_id INTEGER NOT NULL REFERENCES dynamic_reply_messages(id) ON DELETE CASCADE,
            use_count INTEGER DEFAULT 0,
            last_used_at TIMESTAMP,
            UNIQUE(rule_id, reply_id)
        );

        CREATE INDEX idx_dynamic_reply_usage_rule
            ON dynamic_reply_usage(rule_id);
        CREATE INDEX idx_dynamic_reply_usage_reply
            ON dynamic_reply_usage(reply_id);
    END IF;
END $$;
