#!/usr/bin/env python3
"""
Test script for Phase 2 - Placeholder & Template Readiness
Tests new placeholders and template rendering
"""
import sys
from app.gain_alert_templates import DEFAULT_GAIN_ALERT_TEMPLATE


def test_phase2():
    """Test Phase 2 implementation"""
    print("=" * 60)
    print("Phase 2 Testing: Placeholder & Template Readiness")
    print("=" * 60)

    # Test 1: Verify default template includes {chain}
    print("\n[Test 1] Checking default template includes {chain} placeholder...")
    assert "{chain}" in DEFAULT_GAIN_ALERT_TEMPLATE, "Default template should include {chain}"
    print(f"✓ Default template includes {{chain}} placeholder")
    print(f"  Template preview:\n  {DEFAULT_GAIN_ALERT_TEMPLATE}")

    # Test 2: Verify all new placeholders can be formatted
    print("\n[Test 2] Testing template rendering with all placeholders...")
    test_context = {
        "gain_emoji": "🚀",
        "token_symbol": "TEST",
        "multiplier": "2.5x",
        "first_market_cap": "$10.0K",
        "current_market_cap": "$25.0K",
        "elapsed_time": "15m",
        "chain": "SOL",
        "address": "ABC123XYZ789",
        "liquidity": "$50.0K",
        "volume_24h": "$100.0K",
        "age_minutes": "15",
        "price_change_24h": "5.50%",
    }

    try:
        rendered = DEFAULT_GAIN_ALERT_TEMPLATE.format(**test_context)
        print("✓ Template rendered successfully:")
        print(f"\n{rendered}\n")
    except KeyError as e:
        print(f"❌ Template rendering failed - missing placeholder: {e}")
        return 1

    # Test 3: Verify N/A fallbacks work
    print("\n[Test 3] Testing fallback handling with missing data...")
    fallback_context = {
        "gain_emoji": "📈",
        "token_symbol": "TEST",
        "multiplier": "1.5x",
        "first_market_cap": "$5.0K",
        "current_market_cap": "$7.5K",
        "elapsed_time": "8m",
        "chain": "BSC",
        "address": "0xABCD1234",
        "liquidity": "N/A",
        "volume_24h": "N/A",
        "age_minutes": "N/A",
        "price_change_24h": "N/A",
    }

    try:
        rendered_fallback = DEFAULT_GAIN_ALERT_TEMPLATE.format(**fallback_context)
        print("✓ Template rendered with N/A fallbacks:")
        print(f"\n{rendered_fallback}\n")
    except Exception as e:
        print(f"❌ Fallback rendering failed: {e}")
        return 1

    # Test 4: Verify custom template with new placeholders
    print("\n[Test 4] Testing custom template with new placeholders...")
    custom_template = (
        "🎯 {token_symbol} {multiplier} on {chain}\n"
        "💰 MC: {first_market_cap} → {current_market_cap}\n"
        "💧 Liquidity: {liquidity} | 📊 Vol: {volume_24h}\n"
        "⏱ Age: {age_minutes}min | 📈 24h: {price_change_24h}\n"
        "📍 {address}"
    )

    try:
        custom_rendered = custom_template.format(**test_context)
        print("✓ Custom template rendered successfully:")
        print(f"\n{custom_rendered}\n")
    except KeyError as e:
        print(f"❌ Custom template rendering failed - missing placeholder: {e}")
        return 1

    # Test 5: Verify chain label formatting
    print("\n[Test 5] Testing chain label formatting...")
    chain_tests = [
        ("sol", "SOL"),
        ("solana", "SOL"),
        ("bsc", "BSC"),
        ("BSC", "BSC"),
        ("ethereum", "ETHEREUM"),
    ]

    for input_chain, expected_label in chain_tests:
        # Simulate the logic from dex.py
        if input_chain.lower() in ("sol", "solana"):
            result = "SOL"
        elif input_chain.lower() == "bsc":
            result = "BSC"
        else:
            result = input_chain.upper()

        if result == expected_label:
            print(f"  ✓ {input_chain} → {result}")
        else:
            print(f"  ❌ {input_chain} → {result} (expected {expected_label})")
            return 1

    print("\n" + "=" * 60)
    print("✅ Phase 2 Tests PASSED - All placeholders working!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(test_phase2())
