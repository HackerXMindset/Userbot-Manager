#!/usr/bin/env python3
"""Debug script to check why call history isn't showing up"""

import asyncio
import sys
from app.db import db

async def main():
    token_address = 'Cm2XEvvh9qD9VNzLmdS8oo1MN88da3gpjzYM6crdpump'

    try:
        await db.connect()

        print("=" * 80)
        print("1. CHECK IF MIGRATION RAN")
        print("=" * 80)
        migrations = await db.fetch("""
            SELECT name, applied_at
            FROM migrations
            WHERE name LIKE '%backfill%' OR name LIKE '%075%'
            ORDER BY applied_at DESC
        """)
        if migrations:
            for m in migrations:
                print(f"✅ Migration: {m['name']} applied at {m['applied_at']}")
        else:
            print("❌ No backfill migration found!")

        print("\n" + "=" * 80)
        print("2. CHECK IF TOKEN EXISTS IN tokens_tracked")
        print("=" * 80)
        token = await db.fetchrow("""
            SELECT id, address, ticker, source_group_id, first_seen_at, last_checked_at
            FROM tokens_tracked
            WHERE address = $1
        """, token_address)
        if token:
            print(f"✅ Token found: ID={token['id']}, Ticker={token['ticker']}, Group={token['source_group_id']}")
        else:
            print("❌ Token NOT found in tokens_tracked!")
            await db.disconnect()
            return

        token_id = token['id']

        print("\n" + "=" * 80)
        print("3. CHECK OLD calls TABLE")
        print("=" * 80)
        old_calls = await db.fetch("""
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
            WHERE c.token_id = $1
        """, token_id)
        if old_calls:
            print(f"✅ Found {len(old_calls)} calls in OLD table:")
            for call in old_calls:
                print(f"   - Call ID={call['id']}, Status={call['status']}, "
                      f"Sent={call['sent_at']}, Target={call['target_id']}, Msg={call['message_id']}")
        else:
            print("❌ No calls found in OLD calls table!")

        print("\n" + "=" * 80)
        print("4. CHECK NEW token_call_history TABLE")
        print("=" * 80)
        new_calls = await db.fetch("""
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
            WHERE token_address = $1
        """, token_address)
        if new_calls:
            print(f"✅ Found {len(new_calls)} calls in NEW table:")
            for call in new_calls:
                print(f"   - ID={call['id']}, Source={call['source_chat_id']}, "
                      f"Target={call['target_chat_id']}, Msg={call['forwarded_message_id']}")
        else:
            print("❌ No calls found in NEW token_call_history table!")

        print("\n" + "=" * 80)
        print("5. CHECK TARGETS TABLE")
        print("=" * 80)
        targets = await db.fetch("""
            SELECT
                t.id,
                t.group_id,
                t.dest_chat_id,
                g.display_name,
                g.tg_chat_id
            FROM targets t
            LEFT JOIN groups g ON g.id = t.group_id
            WHERE t.group_id = $1
        """, token['source_group_id'])
        if targets:
            print(f"✅ Found {len(targets)} targets:")
            for t in targets:
                print(f"   - Target ID={t['id']}, Dest Chat={t['dest_chat_id']}, "
                      f"Group={t['display_name'] or t['group_id']}")
        else:
            print("❌ No targets found for this group!")

        print("\n" + "=" * 80)
        print("6. MIGRATION BLOCKERS")
        print("=" * 80)
        if old_calls:
            for call in old_calls:
                blockers = []
                if call['status'] != 'sent':
                    blockers.append(f"Status is '{call['status']}' not 'sent'")
                if call['sent_at'] is None:
                    blockers.append("sent_at is NULL")
                if call['target_id'] is None:
                    blockers.append("target_id is NULL")

                if blockers:
                    print(f"❌ Call {call['id']}: {', '.join(blockers)}")
                else:
                    print(f"✅ Call {call['id']}: Should have been migrated!")

        await db.disconnect()

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        await db.disconnect()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
