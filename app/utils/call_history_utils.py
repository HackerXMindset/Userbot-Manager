"""
Call History Utilities - Formatting functions for call history display
"""

from typing import Optional
from datetime import datetime, timezone


def format_call_history_time(called_at: datetime) -> str:
    """
    Format time for call history display.
    Returns format like "1h:26min ago", "55min ago", "0s ago"
    """
    if not called_at:
        return "N/A"

    # Ensure timezone awareness
    if not called_at.tzinfo:
        called_at = called_at.replace(tzinfo=timezone.utc)

    diff = datetime.now(timezone.utc) - called_at
    total_seconds = int(diff.total_seconds())

    # Handle negative time (future dates)
    if total_seconds < 0:
        return "0s ago"

    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if hours > 0:
        return f"{hours}h:{minutes}min ago"
    elif minutes > 0:
        return f"{minutes}min ago"
    else:
        return f"{seconds}s ago"


def format_call_history_market_cap(market_cap_cents: Optional[int]) -> str:
    """
    Format market cap for call history display.
    Input: market cap in USD cents (for precision)
    Returns format like "@11.26K", "@42.66K"
    """
    if market_cap_cents is None:
        return "@N/A"

    try:
        # Convert cents to dollars
        value = float(market_cap_cents) / 100

        if value >= 1_000_000_000:
            return f"@{value / 1_000_000_000:.2f}B"
        elif value >= 1_000_000:
            return f"@{value / 1_000_000:.2f}M"
        elif value >= 1_000:
            return f"@{value / 1_000:.2f}K"
        else:
            return f"@{value:.2f}"
    except (ValueError, TypeError):
        return "@Invalid"


def format_source_name_with_type(source_name: Optional[str], source_type: Optional[str]) -> str:
    """
    Format source name with type indicator for call history.
    Adds [FC] for channels, keeps groups plain.
    """
    if not source_name:
        return "Unknown Source"

    # Clean up source name
    display_name = source_name.strip()

    # Add type indicator for channels
    if source_type == 'channel':
        return f"{display_name} [FC]"
    elif source_type == 'dm':
        return f"{display_name} [DM]"
    else:
        # Groups and unknown types get no indicator
        return display_name


def get_caller_display_name(caller_name: Optional[str], caller_user_id: Optional[int]) -> str:
    """
    Get display name for caller with fallback handling.
    """
    if caller_name and caller_name.strip():
        return caller_name.strip()
    elif caller_user_id:
        return f"User {caller_user_id}"
    else:
        return "Unknown"


def format_call_history_line(record) -> str:
    """
    Format a single call history record into display line.
    Returns format: "1h:26min ago - Twae_ @11.26K in 101 in the Trenches [FC]"
    """
    time_str = format_call_history_time(record.get('called_at'))
    caller_name = get_caller_display_name(record.get('caller_name'), record.get('caller_user_id'))
    market_cap_str = format_call_history_market_cap(record.get('market_cap_at_call'))
    source_str = format_source_name_with_type(record.get('source_name'), record.get('source_type'))

    return f"{time_str} - {caller_name} {market_cap_str} in {source_str}"