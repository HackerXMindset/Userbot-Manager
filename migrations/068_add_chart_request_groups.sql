-- Store list of groups where we can post CA requests
CREATE TABLE IF NOT EXISTS chart_request_groups (
    id SERIAL PRIMARY KEY,
    chat_id BIGINT NOT NULL UNIQUE,
    label TEXT,
    added_at TIMESTAMP DEFAULT NOW()
);
