"""
Tier Calculator - Determines monitoring tier based on token age
Tier-based polling intervals for efficient market cap monitoring
"""

from datetime import datetime, timedelta, timezone
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


# Tier definitions: (tier_name, max_age_seconds, poll_interval_seconds)
TIER_DEFINITIONS = [
    ('tier_a', 10 * 60, 10),           # 0-10 min: poll every 10s
    ('tier_b', 30 * 60, 30),           # 10-30 min: poll every 30s
    ('tier_c', 2 * 60 * 60, 3 * 60),   # 30 min-2 hr: poll every 3 min
    ('tier_d', 6 * 60 * 60, 5 * 60),   # 2-6 hr: poll every 5 min
    ('tier_e', 24 * 60 * 60, 10 * 60), # 6-24 hr: poll every 10 min
    ('tier_f', 7 * 24 * 60 * 60, 30 * 60), # 1-7 days: poll every 30 min
]


def calculate_tier_from_age(first_seen_at: datetime, current_time: Optional[datetime] = None) -> Tuple[str, int]:
    """
    Calculate tier and poll interval based on token age

    Args:
        first_seen_at: When the token was first detected (timezone-aware)
        current_time: Current time (defaults to now if not provided, timezone-aware)

    Returns:
        Tuple of (tier_name, poll_interval_seconds)
        Example: ('tier_b', 30) means Tier B with 30 second polls
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware for comparison
    if first_seen_at.tzinfo is None:
        first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    # Calculate age in seconds
    age_seconds = (current_time - first_seen_at).total_seconds()

    # Find appropriate tier based on age
    for tier_name, max_age, poll_interval in TIER_DEFINITIONS:
        if age_seconds < max_age:
            return (tier_name, poll_interval)

    # If older than 7 days, archive or use 1 hour polling
    logger.debug(f"Token age {age_seconds}s exceeds all tiers, using 1h polling")
    return ('tier_f', 60 * 60)  # 1 hour polling for very old tokens


def get_poll_interval_for_tier(tier: str) -> int:
    """
    Get poll interval (in seconds) for a given tier

    Args:
        tier: Tier name (tier_a, tier_b, etc.)

    Returns:
        Poll interval in seconds
    """
    for tier_name, _, poll_interval in TIER_DEFINITIONS:
        if tier_name == tier:
            return poll_interval

    # Default to 1 hour if tier not found
    logger.warning(f"Unknown tier '{tier}', defaulting to 1h poll interval")
    return 60 * 60


def calculate_next_poll_time(first_seen_at: datetime, current_time: Optional[datetime] = None) -> Tuple[str, datetime]:
    """
    Calculate tier and next poll time for a token

    Args:
        first_seen_at: When the token was first detected (timezone-aware)
        current_time: Current time (defaults to now if not provided, timezone-aware)

    Returns:
        Tuple of (tier_name, next_poll_datetime) - both timezone-aware
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Ensure timezone-aware
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    tier_name, poll_interval = calculate_tier_from_age(first_seen_at, current_time)
    next_poll = current_time + timedelta(seconds=poll_interval)

    return (tier_name, next_poll)


def should_archive_token(first_seen_at: datetime, current_time: Optional[datetime] = None) -> bool:
    """
    Determine if a token should be archived based on age

    Args:
        first_seen_at: When the token was first detected (timezone-aware)
        current_time: Current time (defaults to now if not provided, timezone-aware)

    Returns:
        True if token should be archived (older than 7 days)
    """
    if current_time is None:
        current_time = datetime.now(timezone.utc)

    # Ensure both datetimes are timezone-aware for comparison
    if first_seen_at.tzinfo is None:
        first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    age_seconds = (current_time - first_seen_at).total_seconds()
    max_tier_age = TIER_DEFINITIONS[-1][1]  # tier_f max age (7 days)

    return age_seconds > max_tier_age


def get_tier_info(tier_name: str) -> dict:
    """
    Get information about a specific tier

    Args:
        tier_name: Tier name (tier_a, tier_b, etc.)

    Returns:
        Dict with tier info: {name, max_age_seconds, poll_interval_seconds}
    """
    for tier, max_age, poll_interval in TIER_DEFINITIONS:
        if tier == tier_name:
            return {
                'name': tier,
                'max_age_seconds': max_age,
                'poll_interval_seconds': poll_interval,
                'poll_interval_human': format_duration(poll_interval),
                'max_age_human': format_duration(max_age),
            }

    return {
        'name': tier_name,
        'max_age_seconds': None,
        'poll_interval_seconds': None,
        'error': 'Unknown tier'
    }


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to human-readable string

    Args:
        seconds: Duration in seconds

    Returns:
        Human-readable string like "10s", "3m", "2h", "5d"
    """
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"


def get_all_tiers_info() -> list:
    """
    Get information about all tiers

    Returns:
        List of dicts with tier info
    """
    return [
        {
            'name': tier,
            'max_age_seconds': max_age,
            'poll_interval_seconds': poll_interval,
            'poll_interval_human': format_duration(poll_interval),
            'max_age_human': format_duration(max_age),
        }
        for tier, max_age, poll_interval in TIER_DEFINITIONS
    ]
