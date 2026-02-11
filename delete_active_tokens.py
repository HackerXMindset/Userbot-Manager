#!/usr/bin/env python3
import asyncio
from app.db import db

async def delete_active_tokens():
    await db.connect()
    try:
        # Count before deletion
        count = await db.fetchval("SELECT COUNT(*) FROM tokens_tracked WHERE status = 'active'")
        print(f"🔍 Found {count} active tokens in database")

        if count > 0:
            # Delete all active tokens
            await db.execute("DELETE FROM tokens_tracked WHERE status = 'active'")
            print(f"✅ Deleted {count} active tokens from tokens_tracked table")
        else:
            print("✅ No active tokens found to delete")

    finally:
        await db.disconnect()

asyncio.run(delete_active_tokens())
