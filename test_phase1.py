#!/usr/bin/env python3
"""
Test script for Phase 1 - Chart Guardrails Configuration
Tests config helpers and database schema changes
"""
import asyncio
import sys
from app.config import (
    get_chart_guardrails,
    set_chart_guardrails,
    resolve_chart_guardrails,
    DEFAULT_CHART_GUARDRAILS,
)
from app.db import db


async def test_phase1():
    """Test Phase 1 implementation"""
    print("=" * 60)
    print("Phase 1 Testing: Chart Guardrails Configuration")
    print("=" * 60)

    # Test 1: Load default global guardrails
    print("\n[Test 1] Loading global chart guardrails from database...")
    guardrails = await get_chart_guardrails()
    print(f"✓ Loaded guardrails: {guardrails}")
    assert guardrails["min_age_minutes"] == 5, "Expected min_age_minutes=5"
    assert guardrails["min_liquidity_usd"] == 10000, "Expected min_liquidity_usd=10000"
    assert guardrails["min_volume_usd"] == 5000, "Expected min_volume_usd=5000"
    assert guardrails["min_multiplier"] == 1.5, "Expected min_multiplier=1.5"
    assert guardrails["max_price_change_pct"] == 50, "Expected max_price_change_pct=50"
    assert guardrails["checks_required"] == 0, "Expected checks_required=0"
    print("✓ All default values match expected")

    # Test 2: Update global guardrails
    print("\n[Test 2] Updating global chart guardrails...")
    new_guardrails = {
        "min_age_minutes": 10,
        "min_liquidity_usd": 20000,
        "checks_required": 3,
    }
    await set_chart_guardrails(new_guardrails)
    print(f"✓ Updated guardrails: {new_guardrails}")

    # Test 3: Verify update
    print("\n[Test 3] Verifying updated guardrails...")
    updated = await get_chart_guardrails()
    print(f"✓ Loaded updated guardrails: {updated}")
    assert updated["min_age_minutes"] == 10, "Expected updated min_age_minutes=10"
    assert updated["min_liquidity_usd"] == 20000, "Expected updated min_liquidity_usd=20000"
    assert updated["checks_required"] == 3, "Expected updated checks_required=3"
    # Check that unspecified values retained defaults
    assert updated["min_volume_usd"] == 5000, "Expected min_volume_usd to retain default"
    print("✓ Updates applied correctly, defaults retained for unspecified values")

    # Test 4: Resolve without source override (should use global)
    print("\n[Test 4] Resolving guardrails without source overrides...")
    resolved = await resolve_chart_guardrails()
    print(f"✓ Resolved guardrails: {resolved}")
    assert resolved == updated, "Should match global settings"
    print("✓ Correctly resolved to global defaults")

    # Test 5: Resolve with source overrides
    print("\n[Test 5] Resolving guardrails with source overrides...")
    mock_source = {
        "id": 999,
        "chart_min_age_minutes": 3,
        "chart_min_liquidity_usd": 5000,
        "chart_min_volume_usd": None,  # Should use global
        "chart_min_multiplier": 2.0,
        "chart_max_price_change_pct": None,  # Should use global
        "chart_checks_required": None,  # Should use global
    }
    resolved_with_override = await resolve_chart_guardrails(mock_source)
    print(f"✓ Resolved with overrides: {resolved_with_override}")
    assert resolved_with_override["min_age_minutes"] == 3, "Should use source override"
    assert resolved_with_override["min_liquidity_usd"] == 5000, "Should use source override"
    assert resolved_with_override["min_multiplier"] == 2.0, "Should use source override"
    assert resolved_with_override["min_volume_usd"] == 5000, "Should use global default"
    assert resolved_with_override["checks_required"] == 3, "Should use global default"
    print("✓ Correctly applied source overrides and fell back to globals")

    # Test 6: Restore original defaults
    print("\n[Test 6] Restoring original defaults...")
    await set_chart_guardrails(DEFAULT_CHART_GUARDRAILS)
    restored = await get_chart_guardrails()
    print(f"✓ Restored guardrails: {restored}")
    assert restored == DEFAULT_CHART_GUARDRAILS, "Should match defaults"
    print("✓ Successfully restored defaults")

    # Test 7: Verify schema changes
    print("\n[Test 7] Verifying database schema changes...")
    # Check monitored_sources columns exist
    columns = await db.fetch("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = 'monitored_sources'
        AND column_name LIKE 'chart_%'
        ORDER BY column_name
    """)
    expected_columns = {
        'chart_bot_id',
        'chart_checks_required',
        'chart_enabled',
        'chart_max_price_change_pct',
        'chart_mc_threshold',
        'chart_min_age_minutes',
        'chart_min_liquidity_usd',
        'chart_min_multiplier',
        'chart_min_volume_usd',
    }
    actual_columns = {col['column_name'] for col in columns}
    print(f"✓ Found columns: {actual_columns}")
    assert expected_columns.issubset(actual_columns), f"Missing columns: {expected_columns - actual_columns}"
    print("✓ All expected columns present in monitored_sources table")

    # Test 8: Verify constraints
    print("\n[Test 8] Verifying database constraints...")
    constraints = await db.fetch("""
        SELECT constraint_name
        FROM information_schema.table_constraints
        WHERE table_name = 'monitored_sources'
        AND constraint_name LIKE 'chart_%'
        ORDER BY constraint_name
    """)
    constraint_names = {c['constraint_name'] for c in constraints}
    expected_constraints = {
        'chart_checks_required_valid',
        'chart_max_price_change_valid',
        'chart_mc_threshold_positive',
        'chart_min_age_positive',
        'chart_min_liquidity_positive',
        'chart_min_multiplier_valid',
        'chart_min_volume_positive',
    }
    print(f"✓ Found constraints: {constraint_names}")
    assert expected_constraints.issubset(constraint_names), f"Missing constraints: {expected_constraints - constraint_names}"
    print("✓ All expected constraints present")

    print("\n" + "=" * 60)
    print("✅ Phase 1 Tests PASSED - All functionality working correctly!")
    print("=" * 60)


async def main():
    try:
        await db.connect()
        await test_phase1()
        return 0
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    finally:
        await db.disconnect()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
