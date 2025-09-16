-- 033_add_user_id_to_call_queue.sql

ALTER TABLE call_queue
ADD COLUMN IF NOT EXISTS source_user_id BIGINT;
