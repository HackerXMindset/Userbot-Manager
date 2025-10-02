#!/usr/bin/env python3
"""
Alert System Diagnostic Tool
Identifies why alerts aren't firing and calls aren't being tracked
"""
import asyncio
import asyncpg
from decimal import Decimal
import sys
import os

# Add app to path
sys.path.insert(0, os.path.dirname(__file__))
from app.config import settings

async def diagnose():
    print("🔍 ALERT SYSTEM DIAGNOSTIC\n")

    conn = await asyncpg.connect(settings.supabase_pooler_url)

    try:
        # 1. Check token tracking
        print("=" * 60)
        print("1️⃣  TOKEN TRACKING STATUS")
        print("=" * 60)

        token_stats = await conn.fetchrow("""
            SELECT
                COUNT(*) as total,
                COUNT(source_group_id) as with_group,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN first_seen_mc IS NOT NULL THEN 1 END) as with_baseline
            FROM tokens_tracked
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)

        print(f"📊 Last 24h Tokens:")
        print(f"   Total: {token_stats['total']}")
        print(f"   With source_group_id: {token_stats['with_group']} ⚠️ REQUIRED FOR ALERTS")
        print(f"   Active: {token_stats['active']}")
        print(f"   With baseline MC: {token_stats['with_baseline']}")
        print()

        # 2. Check tokens that SHOULD have fired alerts
        print("=" * 60)
        print("2️⃣  TOKENS ABOVE THRESHOLD (Should have alerted)")
        print("=" * 60)

        high_performers = await conn.fetch("""
            SELECT
                ticker,
                address,
                source_group_id,
                first_seen_mc,
                last_mc,
                peak_mc,
                (last_mc / NULLIF(first_seen_mc, 0)) as current_mult,
                (peak_mc / NULLIF(first_seen_mc, 0)) as peak_mult,
                status
            FROM tokens_tracked
            WHERE created_at > NOW() - INTERVAL '24 hours'
                AND first_seen_mc > 0
                AND last_mc >= first_seen_mc * 2
            ORDER BY (peak_mc / first_seen_mc) DESC
            LIMIT 10
        """)

        for t in high_performers:
            print(f"\n🚀 ${t['ticker'] or t['address'][:8]}")
            print(f"   Current: {float(t['current_mult']):.2f}x | Peak: {float(t['peak_mult']):.2f}x")
            print(f"   source_group_id: {t['source_group_id']} {'❌ MISSING' if not t['source_group_id'] else '✅'}")
            print(f"   Status: {t['status']}")

        if not high_performers:
            print("   ✅ No tokens above 2x (alerts wouldn't fire anyway)")
        print()

        # 3. Check target configuration
        print("=" * 60)
        print("3️⃣  TARGET ALERT CONFIGURATION")
        print("=" * 60)

        targets = await conn.fetch("""
            SELECT
                t.id,
                t.alerts_enabled,
                t.alerts_modes,
                t.alerts_thresholds,
                t.alerts_sensitivity_percent,
                g.title as group_name,
                g.id as group_id
            FROM targets t
            LEFT JOIN groups g ON g.id = t.group_id
        """)

        for t in targets:
            print(f"\n📍 Target {t['id']} - {t['group_name']} (group_id: {t['group_id']})")
            print(f"   alerts_enabled: {t['alerts_enabled']} {'✅' if t['alerts_enabled'] else '❌ DISABLED'}")
            print(f"   alerts_modes: {t['alerts_modes']}")
            print(f"   alerts_thresholds: {t['alerts_thresholds']}")
            print(f"   sensitivity: {t['alerts_sensitivity_percent']}")

        if not targets:
            print("   ❌ NO TARGETS CONFIGURED")
        print()

        # 4. Check alert states
        print("=" * 60)
        print("4️⃣  ALERT STATE TRACKING")
        print("=" * 60)

        alert_states = await conn.fetchrow("""
            SELECT
                COUNT(*) as total_states,
                COUNT(CASE WHEN last_alert_at IS NOT NULL THEN 1 END) as fired_alerts,
                AVG(last_alert_multiplier) as avg_last_mult
            FROM target_token_alert_state
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)

        print(f"📈 Alert States (24h):")
        print(f"   Total states: {alert_states['total_states']}")
        print(f"   Alerts fired: {alert_states['fired_alerts']}")
        print(f"   Avg last multiplier: {float(alert_states['avg_last_mult'] or 0):.2f}x")
        print()

        # 5. Check call queue
        print("=" * 60)
        print("5️⃣  CALL QUEUE STATUS")
        print("=" * 60)

        queue_stats = await conn.fetch("""
            SELECT status, COUNT(*) as count
            FROM call_queue
            WHERE created_at > NOW() - INTERVAL '24 hours'
            GROUP BY status
        """)

        print("📥 Call Queue (24h):")
        for stat in queue_stats:
            print(f"   {stat['status']}: {stat['count']}")

        if not queue_stats:
            print("   ⚠️  NO JOBS IN QUEUE - Alerts not being created!")
        print()

        # 6. Check actual calls logged
        print("=" * 60)
        print("6️⃣  CALLS LOGGED (What analytics shows)")
        print("=" * 60)

        # Check both tables
        calls_old = await conn.fetchval("""
            SELECT COUNT(*) FROM calls
            WHERE sent_at > NOW() - INTERVAL '24 hours'
                AND status = 'sent'
        """)

        try:
            calls_new = await conn.fetchval("""
                SELECT COUNT(*) FROM token_call_history
                WHERE called_at > NOW() - INTERVAL '24 hours'
            """)
        except:
            calls_new = "Table doesn't exist"

        print(f"📊 Calls in 'calls' table: {calls_old} (OLD - was used by analytics)")
        print(f"📊 Calls in 'token_call_history' table: {calls_new} (NEW - now used by analytics)")
        print()

        # 7. Check userbot assignments
        print("=" * 60)
        print("7️⃣  USERBOT ASSIGNMENTS")
        print("=" * 60)

        assignments = await conn.fetch("""
            SELECT
                ua.group_id,
                ua.userbot_id,
                g.title as group_name
            FROM userbot_assignments ua
            LEFT JOIN groups g ON g.id = ua.group_id
        """)

        print(f"🤖 Userbot Assignments:")
        for a in assignments:
            print(f"   Group {a['group_id']} ({a['group_name']}): Userbot {a['userbot_id']}")

        if not assignments:
            print("   ❌ NO USERBOT ASSIGNMENTS - Cannot send alerts!")
        print()

        # 8. DIAGNOSIS SUMMARY
        print("=" * 60)
        print("🔍 DIAGNOSIS SUMMARY")
        print("=" * 60)

        issues = []

        if token_stats['with_group'] < token_stats['total']:
            issues.append(f"⚠️  {token_stats['total'] - token_stats['with_group']} tokens missing source_group_id")

        enabled_targets = sum(1 for t in targets if t['alerts_enabled'])
        if enabled_targets == 0:
            issues.append("❌ NO targets have alerts_enabled=true")

        if not assignments:
            issues.append("❌ NO userbot assignments for forwarding")

        if not queue_stats:
            issues.append("⚠️  No jobs queued - alert detection not triggering")

        if issues:
            print("\n❌ ISSUES FOUND:\n")
            for issue in issues:
                print(f"   {issue}")
        else:
            print("\n✅ No obvious configuration issues found")

        print("\n" + "=" * 60)
        print("💡 NEXT STEPS")
        print("=" * 60)
        print("1. Check logs for [ALERT_SKIP], [ALERT_TRIGGER], [ALERT_FAIL] messages")
        print("2. Ensure tokens have source_group_id set when detected")
        print("3. Configure targets with alerts_enabled=true")
        print("4. Assign userbots to groups for forwarding")
        print()

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(diagnose())
