-- Re-add a unique constraint on group_id for userbot_assignments
-- This constraint was removed in migration 011, but the assignment logic depends on it.
-- This new index is partial, so it only applies where group_id is not null,
-- allowing source_id assignments (where group_id is null) to work correctly.

CREATE UNIQUE INDEX IF NOT EXISTS userbot_assignments_group_id_unique_not_null
ON userbot_assignments(group_id)
WHERE group_id IS NOT NULL;
