-- Debug script to check why call history isn't showing up

-- 1. Check if migration ran
SELECT name, applied_at
FROM migrations
WHERE name LIKE '%backfill%' OR name LIKE '%075%'
ORDER BY applied_at DESC;

-- 2. Check if token exists in tokens_tracked
SELECT id, address, ticker, source_group_id, first_seen_at, last_checked_at
FROM tokens_tracked
WHERE address = 'Cm2XEvvh9qD9VNzLmdS8oo1MN88da3gpjzYM6crdpump';

-- 3. Check if calls exist in OLD calls table
SELECT
    c.id,
    c.group_id,
    c.token_id,
    c.target_id,
    c.userbot_id,
    c.status,
    c.sent_at,
    c.message_id,
    tt.address,
    tt.ticker
FROM calls c
LEFT JOIN tokens_tracked tt ON tt.id = c.token_id
WHERE tt.address = 'Cm2XEvvh9qD9VNzLmdS8oo1MN88da3gpjzYM6crdpump';

-- 4. Check if anything in NEW token_call_history table
SELECT
    id,
    token_address,
    source_chat_id,
    source_name,
    target_chat_id,
    forwarding_userbot_id,
    forwarded_message_id,
    called_at
FROM token_call_history
WHERE token_address = 'Cm2XEvvh9qD9VNzLmdS8oo1MN88da3gpjzYM6crdpump';

-- 5. Check targets table for this group
SELECT
    t.id,
    t.group_id,
    t.dest_chat_id,
    g.display_name,
    g.tg_chat_id
FROM targets t
LEFT JOIN groups g ON g.id = t.group_id
WHERE t.group_id IN (
    SELECT source_group_id FROM tokens_tracked
    WHERE address = 'Cm2XEvvh9qD9VNzLmdS8oo1MN88da3gpjzYM6crdpump'
);

-- 6. Check why migration might have skipped records
SELECT
    c.id as call_id,
    c.status,
    c.sent_at,
    c.message_id,
    tt.address,
    t.dest_chat_id,
    CASE
        WHEN c.status != 'sent' THEN 'Status not sent'
        WHEN c.sent_at IS NULL THEN 'sent_at is NULL'
        WHEN t.dest_chat_id IS NULL THEN 'No target found'
        ELSE 'Should have been migrated'
    END as migration_blocker
FROM calls c
LEFT JOIN tokens_tracked tt ON tt.id = c.token_id
LEFT JOIN targets t ON t.id = c.target_id
WHERE tt.address = 'Cm2XEvvh9qD9VNzLmdS8oo1MN88da3gpjzYM6crdpump';
