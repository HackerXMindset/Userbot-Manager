-- Bots table
CREATE TABLE IF NOT EXISTS bots (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT CHECK (kind IN ('management', 'userbot')) NOT NULL,
    session_name TEXT UNIQUE,
    status TEXT DEFAULT 'unknown',
    last_seen TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Groups table
CREATE TABLE IF NOT EXISTS groups (
    id BIGSERIAL PRIMARY KEY,
    tg_chat_id BIGINT UNIQUE NOT NULL,
    title TEXT,
    enabled BOOLEAN DEFAULT true,
    daily_cap INT DEFAULT 0,
    cooldown_minutes INT DEFAULT 10,
    notif_channel_id BIGINT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Group schedules
CREATE TABLE IF NOT EXISTS group_schedules (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    weekdays INT[] NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    max_calls_in_window INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Targets
CREATE TABLE IF NOT EXISTS targets (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    dest_chat_id BIGINT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, dest_chat_id)
);

-- Settings
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Insert default settings
INSERT INTO settings (key, value) VALUES
    ('gain_multipliers', '[5, 10, 15, 20, 50]'),
    ('drop_percentage', '0.70'),
    ('timezone', '"Asia/Kolkata"'),
    ('dex_poll_secs', '5'),
    ('admin_id', 'null'),
    ('default_notif_channel_id', 'null')
ON CONFLICT (key) DO NOTHING;

-- Tokens tracked
CREATE TABLE IF NOT EXISTS tokens_tracked (
    id BIGSERIAL PRIMARY KEY,
    address TEXT UNIQUE NOT NULL,
    source_group_id BIGINT REFERENCES groups(id) ON DELETE SET NULL,
    first_seen_mc NUMERIC,
    last_mc NUMERIC,
    status TEXT DEFAULT 'active',
    last_hit_multiplier NUMERIC DEFAULT 1,
    first_seen_at TIMESTAMPTZ DEFAULT NOW(),
    last_checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- Calls
CREATE TABLE IF NOT EXISTS calls (
    id BIGSERIAL PRIMARY KEY,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    token_id BIGINT REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    target_id BIGINT REFERENCES targets(id) ON DELETE SET NULL,
    userbot_id BIGINT REFERENCES bots(id) ON DELETE SET NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    status TEXT DEFAULT 'queued',
    reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_calls_scheduled ON calls(scheduled_at);
CREATE INDEX idx_calls_status ON calls(status);
CREATE INDEX idx_calls_group_sent ON calls(group_id, sent_at);
CREATE INDEX idx_tokens_source_group ON tokens_tracked(source_group_id);

-- Alerts
CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    token_id BIGINT REFERENCES tokens_tracked(id) ON DELETE CASCADE,
    alert_type TEXT,
    multiplier NUMERIC,
    threshold NUMERIC,
    triggered_at TIMESTAMPTZ DEFAULT NOW(),
    posted_msg_id BIGINT,
    channel_id BIGINT
);

-- Events
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    kind TEXT,
    src_chat_id BIGINT,
    src_msg_id BIGINT,
    user_id BIGINT,
    token_id BIGINT REFERENCES tokens_tracked(id) ON DELETE SET NULL,
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    routed_to_channel_id BIGINT
);

-- Userbot assignments
CREATE TABLE IF NOT EXISTS userbot_assignments (
    id BIGSERIAL PRIMARY KEY,
    userbot_id BIGINT REFERENCES bots(id) ON DELETE CASCADE,
    group_id BIGINT REFERENCES groups(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(userbot_id, group_id),
    UNIQUE(group_id)
);