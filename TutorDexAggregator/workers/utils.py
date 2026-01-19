"""
Utility functions for the extraction worker.

Contains helper functions for text processing, hashing, and data coercion.
"""

import hashlib
import re
from typing import Any, List, Optional


def sha256_hash(text: str) -> str:
    """Generate SHA256 hash of text."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def extract_sg_postal_codes(text: str) -> List[str]:
    """
    Extract Singapore postal codes (6-digit numbers) from text.

    Returns deduplicated list preserving order.
    """
    try:
        codes = re.findall(r"\b(\d{6})\b", str(text or ""))
    except Exception:
        codes = []

    # Deduplicate while preserving order
    seen = set()
    out: List[str] = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def coerce_list_of_str(value: Any) -> Optional[List[str]]:
    """
    Coerce value to list of strings.

    Handles:
    - None -> None
    - str -> [str] (if non-empty)
    - list/tuple -> flattened list of strings
    - other -> [str(value)] (if non-empty)

    Returns deduplicated list preserving order, or None if empty.
    """
    if value is None:
        return None

    if isinstance(value, str):
        s = value.strip()
        return [s] if s else None

    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(coerce_list_of_str(x) or [])

        # Deduplicate while preserving order
        seen = set()
        uniq: List[str] = []
        for s in out:
            ss = str(s).strip()
            if not ss or ss in seen:
                continue
            seen.add(ss)
            uniq.append(ss)
        return uniq or None

    s2 = str(value).strip()
    return [s2] if s2 else None


def build_message_link(channel_link: str, message_id: str) -> Optional[str]:
    """
    Build Telegram message link from channel and message ID.

    Args:
        channel_link: Channel link (e.g., "t.me/channel" or "https://t.me/channel")
        message_id: Message ID

    Returns:
        Full message link or None if invalid
    """
    cl = str(channel_link or "").strip()
    mid = str(message_id or "").strip()

    if not cl or not mid:
        return None

    if cl.startswith("t.me/"):
        return f"https://{cl}/{mid}"

    if cl.startswith("https://t.me/") or cl.startswith("http://t.me/"):
        cl2 = cl.replace("https://", "").replace("http://", "")
        return f"https://{cl2}/{mid}"

    return None


def utc_now_iso() -> str:
    """Get current UTC timestamp in ISO format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
