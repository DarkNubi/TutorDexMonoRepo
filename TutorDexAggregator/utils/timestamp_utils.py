"""
Timestamp utility functions.

Extracted from supabase_persist.py.
Provides ISO 8601 timestamp parsing, formatting, and comparison utilities.
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO 8601 timestamp string into datetime object.

    Handles both 'Z' suffix and '+00:00' timezone format.
    Returns None if parsing fails.
    """
    if not value:
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def coerce_iso_ts(value) -> Optional[str]:
    """
    Coerce value to ISO 8601 timestamp string.

    If value is datetime, converts to UTC ISO format with 'Z' suffix.
    Otherwise converts to string and strips whitespace.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    s = str(value).strip()
    return s or None


def max_iso_ts(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """
    Return the later of two ISO-ish timestamps.

    If parsing fails, prefer a non-empty value deterministically.
    Falls back to 'b' if both are unparseable.
    """
    if not a and not b:
        return None
    if not a:
        return b
    if not b:
        return a
    da = parse_iso_dt(a)
    db = parse_iso_dt(b)
    if da and db:
        return a if da >= db else b
    if da and not db:
        return a
    if db and not da:
        return b
    # Both unparseable: fall back to stable choice.
    return b
