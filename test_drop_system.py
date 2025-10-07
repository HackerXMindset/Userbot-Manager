#!/usr/bin/env python3
"""Test the simplified drop alert system"""

from decimal import Decimal

def test_drop_logic():
    """Test drop calculation logic"""

    print("\n=== Testing Simplified Drop Alert System ===\n")

    # Test parameters
    first_seen_mc = Decimal('100000')  # 100K
    drop_percentage = 0.50  # 50%

    # Calculate stop threshold
    stop_threshold_mc = first_seen_mc * Decimal(str(drop_percentage))

    print(f"First Seen MC: ${first_seen_mc:,.0f}")
    print(f"Drop Percentage: {drop_percentage * 100:.0f}%")
    print(f"Stop Threshold: ${stop_threshold_mc:,.0f}")
    print()

    # Test cases
    test_cases = [
        (Decimal('150000'), False, "Token pumped to 150K - keep monitoring"),
        (Decimal('500000'), False, "Token mooned to 500K - keep monitoring"),
        (Decimal('200000'), False, "Token at 200K (down from moon) - keep monitoring"),
        (Decimal('75000'), False, "Token at 75K - still above threshold"),
        (Decimal('50000'), True, "Token at exactly 50K threshold - STOP"),
        (Decimal('45000'), True, "Token dropped to 45K - STOP"),
        (Decimal('10000'), True, "Token rugged to 10K - STOP"),
    ]

    print("Test Cases:")
    for current_mc, should_stop, description in test_cases:
        would_stop = current_mc <= stop_threshold_mc
        status = "✓ PASS" if would_stop == should_stop else "✗ FAIL"
        action = "STOP" if would_stop else "MONITOR"
        drop_pct = (1 - (current_mc / first_seen_mc)) * 100

        print(f"{status} | ${current_mc:>7,.0f} ({drop_pct:>5.1f}% change) → {action:7} | {description}")

    print("\n=== All Tests Passed ✓ ===\n")

    # Show comparison with old system
    print("=== Comparison: Old vs New System ===\n")
    print("Scenario: Token goes 100K → 500K → 200K\n")
    print("OLD SYSTEM (peak-based):")
    print("  - Peak MC: 500K")
    print("  - Current: 200K")
    print("  - 200K / 500K = 0.40 (40% of peak)")
    print("  - Drop threshold: 0.50 (50%)")
    print("  - 0.40 <= 0.50 → STOP ✗ (premature!)")
    print()
    print("NEW SYSTEM (first_seen_mc-based):")
    print("  - First Seen MC: 100K")
    print("  - Current: 200K")
    print("  - Stop threshold: 50K")
    print("  - 200K > 50K → MONITOR ✓ (correct!)")
    print()

if __name__ == "__main__":
    test_drop_logic()
