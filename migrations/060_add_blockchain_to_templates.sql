-- 060_add_blockchain_to_templates.sql

-- Ensure templates track blockchain specificity (default SOL)
ALTER TABLE post_templates
ADD COLUMN IF NOT EXISTS blockchain TEXT NOT NULL DEFAULT 'SOL';

-- Normalize existing rows
UPDATE post_templates
SET blockchain = UPPER(COALESCE(blockchain, 'SOL'));

ALTER TABLE post_templates
ALTER COLUMN blockchain SET DEFAULT 'SOL';

-- Allow target assignments to store one template per chain
ALTER TABLE target_template_assignments
ADD COLUMN IF NOT EXISTS blockchain TEXT NOT NULL DEFAULT 'SOL';

UPDATE target_template_assignments
SET blockchain = UPPER(COALESCE(blockchain, 'SOL'));

-- Replace the existing primary key (group_id) with (group_id, blockchain)
ALTER TABLE target_template_assignments
DROP CONSTRAINT IF EXISTS target_template_assignments_pkey;

ALTER TABLE target_template_assignments
ADD CONSTRAINT target_template_assignments_pkey
PRIMARY KEY (group_id, blockchain);
