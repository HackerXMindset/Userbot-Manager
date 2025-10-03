-- Make bot_id and button_text nullable to support dynamic rules where they are not used.

ALTER TABLE auto_button_click_rules ALTER COLUMN bot_id DROP NOT NULL;
ALTER TABLE auto_button_click_rules ALTER COLUMN button_text DROP NOT NULL;
