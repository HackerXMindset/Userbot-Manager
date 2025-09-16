-- 032_add_custom_post_templates.sql

-- Table to store custom template definitions
CREATE TABLE IF NOT EXISTS post_templates (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    template_text TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Table to assign a template to a target group
CREATE TABLE IF NOT EXISTS target_template_assignments (
    group_id INTEGER PRIMARY KEY,
    template_id INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_group
        FOREIGN KEY(group_id)
        REFERENCES groups(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_template
        FOREIGN KEY(template_id)
        REFERENCES post_templates(id)
        ON DELETE CASCADE
);
