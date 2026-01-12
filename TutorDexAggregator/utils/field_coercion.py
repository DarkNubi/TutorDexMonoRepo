"""
Field coercion and normalization utilities.

Extracted from supabase_persist.py.
Provides type conversion, validation, and normalization functions for various data types.
"""

import math
import re
from typing import Any, List, Optional

# Singapore postal code pattern (6 digits)
_SG_POSTAL_RE = re.compile(r"\b(\d{6})\b")


def truthy(value: Optional[str]) -> bool:
    """
    Check if string value represents a truthy value.
    
    Returns True for: "1", "true", "yes", "y", "on" (case insensitive).
    Returns False for None or any other value.
    """
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def safe_str(value: Any) -> Optional[str]:
    """
    Convert value to string, stripping whitespace.
    
    Returns None if value is None or empty after stripping.
    """
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def normalize_sg_postal_code(value: Any) -> Optional[str]:
    """
    Normalize Singapore postal code to 6-digit format.
    
    Extracts 6-digit sequence from input, ignoring other characters.
    Returns None if no valid postal code found.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    digits = re.sub(r"\D+", "", s)
    m = _SG_POSTAL_RE.search(digits)
    return m.group(1) if m else None


def coerce_int_like(value: Any) -> Optional[int]:
    """
    Convert values like 45, 45.0, "45", "45.0" into an int.
    
    Returns None if the value is not safely representable as an integer (e.g. 45.5).
    Handles int, float, str, and other numeric types.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            return None
        rounded = round(value)
        if abs(value - rounded) < 1e-9:
            return int(rounded)
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            f = float(s)
        except Exception:
            return None
        if not math.isfinite(f):
            return None
        rounded = round(f)
        if abs(f - rounded) < 1e-9:
            return int(rounded)
        return None
    # Best-effort fallback for numerics (e.g. Decimal)
    try:
        f2 = float(value)
    except Exception:
        return None
    if not math.isfinite(f2):
        return None
    rounded2 = round(f2)
    if abs(f2 - rounded2) < 1e-9:
        return int(rounded2)
    return None


def first_text(value: Any) -> Optional[str]:
    """
    Extract first non-empty text value from nested structure.
    
    Recursively searches lists/tuples for first non-empty string.
    Returns None if no text found.
    """
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            s = first_text(item)
            if s:
                return s
        return None
    return safe_str(value)


def coerce_text_list(value: Any) -> List[str]:
    """
    Convert value to list of non-empty unique strings.
    
    Handles:
    - None → []
    - str → [str] (if non-empty)
    - list/tuple → flattened list of strings
    
    Preserves order while removing duplicates.
    """
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(coerce_text_list(x))
        # de-dup preserve order
        seen = set()
        uniq: List[str] = []
        for t in out:
            s = str(t).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            uniq.append(s)
        return uniq
    v = str(value).strip()
    return [v] if v else []


def truthy_text(value: Any) -> bool:
    """
    Check if value contains any non-empty text.
    
    Returns True if coerce_text_list returns a non-empty list.
    """
    return any(coerce_text_list(value))
