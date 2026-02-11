"""
Test script for Phase 3 chart guardrail evaluation.

Tests various scenarios:
1. All checks pass
2. Single check fails (age too young)
3. Multiple checks fail
4. N-of-M pass logic (checks_required = 3)
5. Missing data handling
"""

import asyncio
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from app.chart_guardrail_evaluator import evaluate_chart_guardrails, format_guardrail_summary


async def test_all_pass():
    """Test scenario where all guardrails pass"""
    print("\n" + "="*60)
    print("TEST 1: All Guardrails Pass")
    print("="*60)

    token_data = {"id": 1, "address": "test123"}
    pair_data = {
        "liquidity": {"usd": 25000},  # > 10k
        "volume": {"h24": 8000},       # > 5k
        "priceChange": {"h24": 15.5},  # < 50%
    }
    guardrails = {
        "min_age_minutes": 5,
        "min_liquidity_usd": 10000,
        "min_volume_usd": 5000,
        "min_multiplier": 1.5,
        "max_price_change_pct": 50,
        "checks_required": 0,  # All must pass
    }
    current_mc = Decimal("150000")
    first_seen_mc = Decimal("50000")
    first_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    address = "test123456"

    result = await evaluate_chart_guardrails(
        token_data=token_data,
        pair_data=pair_data,
        guardrails=guardrails,
        current_mc=current_mc,
        first_seen_mc=first_seen_mc,
        first_seen_at=first_seen_at,
        address=address,
    )

    print(f"\nResult: {result}")
    print(f"Passed: {result.passed}")
    print(f"Checks: {result.checks_passed}/{len(result.checks)}")
    print("\nSummary:")
    print(format_guardrail_summary(result))

    assert result.passed, "Expected all checks to pass"
    print("\n✅ TEST PASSED")


async def test_age_fail():
    """Test scenario where token is too young"""
    print("\n" + "="*60)
    print("TEST 2: Age Check Fails (Token Too Young)")
    print("="*60)

    token_data = {"id": 1, "address": "test123"}
    pair_data = {
        "liquidity": {"usd": 25000},
        "volume": {"h24": 8000},
        "priceChange": {"h24": 15.5},
    }
    guardrails = {
        "min_age_minutes": 10,
        "min_liquidity_usd": 10000,
        "min_volume_usd": 5000,
        "min_multiplier": 1.5,
        "max_price_change_pct": 50,
        "checks_required": 0,
    }
    current_mc = Decimal("150000")
    first_seen_mc = Decimal("50000")
    first_seen_at = datetime.now(timezone.utc) - timedelta(minutes=3)  # Only 3 min old
    address = "test123456"

    result = await evaluate_chart_guardrails(
        token_data=token_data,
        pair_data=pair_data,
        guardrails=guardrails,
        current_mc=current_mc,
        first_seen_mc=first_seen_mc,
        first_seen_at=first_seen_at,
        address=address,
    )

    print(f"\nResult: {result}")
    print(f"Passed: {result.passed}")
    print(f"Checks: {result.checks_passed}/{len(result.checks)}")
    print("\nSummary:")
    print(format_guardrail_summary(result))

    assert not result.passed, "Expected age check to fail"
    failed = result.get_failed_checks()
    assert any(check.name == "age" for check in failed), "Expected age check in failed list"
    print("\n✅ TEST PASSED")


async def test_multiple_fails():
    """Test scenario where multiple checks fail"""
    print("\n" + "="*60)
    print("TEST 3: Multiple Checks Fail")
    print("="*60)

    token_data = {"id": 1, "address": "test123"}
    pair_data = {
        "liquidity": {"usd": 5000},    # < 10k (FAIL)
        "volume": {"h24": 2000},        # < 5k (FAIL)
        "priceChange": {"h24": 75.0},   # > 50% (FAIL)
    }
    guardrails = {
        "min_age_minutes": 5,
        "min_liquidity_usd": 10000,
        "min_volume_usd": 5000,
        "min_multiplier": 1.5,
        "max_price_change_pct": 50,
        "checks_required": 0,
    }
    current_mc = Decimal("150000")
    first_seen_mc = Decimal("50000")
    first_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    address = "test123456"

    result = await evaluate_chart_guardrails(
        token_data=token_data,
        pair_data=pair_data,
        guardrails=guardrails,
        current_mc=current_mc,
        first_seen_mc=first_seen_mc,
        first_seen_at=first_seen_at,
        address=address,
    )

    print(f"\nResult: {result}")
    print(f"Passed: {result.passed}")
    print(f"Checks: {result.checks_passed}/{len(result.checks)}")
    print("\nFailed checks:")
    for check in result.get_failed_checks():
        print(f"  - {check.name}: {check.actual_value} vs {check.threshold_value}")
    print("\nSummary:")
    print(format_guardrail_summary(result))

    assert not result.passed, "Expected multiple checks to fail"
    assert len(result.get_failed_checks()) >= 3, "Expected at least 3 failures"
    print("\n✅ TEST PASSED")


async def test_n_of_m_logic():
    """Test N-of-M pass logic (3 of 5 checks must pass)"""
    print("\n" + "="*60)
    print("TEST 4: N-of-M Logic (3 of 5 required)")
    print("="*60)

    token_data = {"id": 1, "address": "test123"}
    pair_data = {
        "liquidity": {"usd": 5000},    # FAIL
        "volume": {"h24": 8000},        # PASS
        "priceChange": {"h24": 15.0},   # PASS
    }
    guardrails = {
        "min_age_minutes": 5,
        "min_liquidity_usd": 10000,
        "min_volume_usd": 5000,
        "min_multiplier": 1.5,
        "max_price_change_pct": 50,
        "checks_required": 3,  # Only 3 of 5 must pass
    }
    current_mc = Decimal("150000")
    first_seen_mc = Decimal("50000")
    first_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    address = "test123456"

    result = await evaluate_chart_guardrails(
        token_data=token_data,
        pair_data=pair_data,
        guardrails=guardrails,
        current_mc=current_mc,
        first_seen_mc=first_seen_mc,
        first_seen_at=first_seen_at,
        address=address,
    )

    print(f"\nResult: {result}")
    print(f"Passed: {result.passed}")
    print(f"Checks: {result.checks_passed}/{len(result.checks)} (need {result.checks_required})")
    print(f"\nPassed checks: {[c.name for c in result.get_passed_checks()]}")
    print(f"Failed checks: {[c.name for c in result.get_failed_checks()]}")
    print("\nSummary:")
    print(format_guardrail_summary(result))

    # Should pass because we have >= 3 checks passing
    assert result.checks_passed >= 3, "Should have at least 3 passing checks"
    print("\n✅ TEST PASSED")


async def test_missing_data():
    """Test handling of missing data"""
    print("\n" + "="*60)
    print("TEST 5: Missing Data Handling")
    print("="*60)

    token_data = {"id": 1, "address": "test123"}
    pair_data = None  # No pair data available
    guardrails = {
        "min_age_minutes": 5,
        "min_liquidity_usd": 10000,
        "min_volume_usd": 5000,
        "min_multiplier": 1.5,
        "max_price_change_pct": 50,
        "checks_required": 0,
    }
    current_mc = Decimal("150000")
    first_seen_mc = Decimal("50000")
    first_seen_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    address = "test123456"

    result = await evaluate_chart_guardrails(
        token_data=token_data,
        pair_data=pair_data,
        guardrails=guardrails,
        current_mc=current_mc,
        first_seen_mc=first_seen_mc,
        first_seen_at=first_seen_at,
        address=address,
    )

    print(f"\nResult: {result}")
    print(f"Passed: {result.passed}")
    print(f"Checks: {result.checks_passed}/{len(result.checks)}")
    print("\nFailed checks:")
    for check in result.get_failed_checks():
        print(f"  - {check.name}: {check.actual_value} (reason: {check.reason})")

    # Should fail because liquidity, volume, and price_stability checks need pair data
    assert not result.passed, "Expected to fail with missing pair data"
    failed_names = [c.name for c in result.get_failed_checks()]
    assert "liquidity" in failed_names, "Expected liquidity check to fail"
    assert "volume_24h" in failed_names, "Expected volume check to fail"
    print("\n✅ TEST PASSED")


async def main():
    """Run all tests"""
    print("\n" + "#"*60)
    print("# Phase 3 Guardrail Evaluation Tests")
    print("#"*60)

    try:
        await test_all_pass()
        await test_age_fail()
        await test_multiple_fails()
        await test_n_of_m_logic()
        await test_missing_data()

        print("\n" + "#"*60)
        print("# ALL TESTS PASSED ✅")
        print("#"*60)
        return 0
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
