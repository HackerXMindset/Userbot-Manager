"""
Gain alert template utilities.

Defines required placeholders, default template text, and helpers for
validating custom templates used by both global and per-source overrides.
"""

from __future__ import annotations

import re
from typing import Set

REQUIRED_GAIN_TEMPLATE_PLACEHOLDERS: Set[str] = set()

# Default template mirrors the legacy hard-coded alert with an added CA line.
DEFAULT_GAIN_ALERT_TEMPLATE = (
    "{gain_emoji} ${token_symbol} {multiplier} | 💹From {first_market_cap} ↗️ {current_market_cap} within {elapsed_time}\n"
    "🔗 CA: {address}\n"
    "⚠️ Gain alerts are in beta and may be inaccurate."
)

_PLACEHOLDER_PATTERN = re.compile(r"{(\w+)}")


def missing_required_placeholders(template_text: str) -> Set[str]:
    """
    Return any required placeholders absent from the provided template.

    Args:
        template_text: Template string to inspect.
    """
    found = set(_PLACEHOLDER_PATTERN.findall(template_text or ""))
    return REQUIRED_GAIN_TEMPLATE_PLACEHOLDERS - found


def normalise_template(template_text: str) -> str:
    """
    Normalise template text before persisting.

    Strips leading/trailing whitespace but preserves intentional newlines
    inside the template body.
    """
    return (template_text or "").strip()
