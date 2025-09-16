-- 034_add_sender_toggle_to_templates.sql

ALTER TABLE post_templates
ADD COLUMN IF NOT EXISTS use_management_bot BOOLEAN NOT NULL DEFAULT FALSE;
