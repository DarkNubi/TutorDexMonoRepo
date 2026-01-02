from __future__ import annotations

import re
from typing import Optional, Tuple


_LEVEL_CANON: dict[str, str] = {
    "pre-school": "Pre-School",
    "preschool": "Pre-School",
    "primary": "Primary",
    "pri": "Primary",
    "secondary": "Secondary",
    "sec": "Secondary",
    "junior college": "Junior College",
    "jc": "Junior College",
    "ib": "IB",
    "igcse": "IGCSE",
    "poly": "Polytechnic",
    "polytechnic": "Polytechnic",
}


_STREAM_CANON: dict[str, str] = {
    "na": "NA",
    "nt": "NT",
    "ip": "IP",
    "express": "Express",
    "foundation": "Foundation",
    "hl": "HL",
    "sl": "SL",
}


def canonicalize_level_token(token: str) -> Optional[str]:
    s = str(token or "").strip().lower()
    if not s:
        return None
    return _LEVEL_CANON.get(s)


def canonicalize_stream_token(token: str) -> Optional[str]:
    s = str(token or "").strip()
    if not s:
        return None
    sl = s.lower()
    if sl in _STREAM_CANON:
        return _STREAM_CANON[sl]
    m = re.fullmatch(r"g([1-3])", sl)
    if m:
        return f"G{m.group(1)}"
    m = re.fullmatch(r"h([1-3])", sl)
    if m:
        return f"H{m.group(1)}"
    return None


def canonicalize_specific_level(*, kind: str, number: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (level, specific_student_level).
    `kind` is one of: primary|secondary|jc|k|ib|igcse|year_only
    """
    k = (kind or "").strip().lower()
    n = str(number or "").strip()
    if not n:
        return None, None

    def _int_in_range(lo: int, hi: int) -> Optional[int]:
        try:
            i = int(n)
        except Exception:
            return None
        if lo <= i <= hi:
            return i
        return None

    if k == "primary":
        i = _int_in_range(1, 6)
        return ("Primary", f"Primary {i}") if i is not None else (None, None)
    if k == "secondary":
        i = _int_in_range(1, 5)
        return ("Secondary", f"Secondary {i}") if i is not None else (None, None)
    if k == "jc":
        i = _int_in_range(1, 2)
        return ("Junior College", f"JC {i}") if i is not None else (None, None)
    if k == "k":
        i = _int_in_range(1, 2)
        return ("Pre-School", f"Kindergarten {i}") if i is not None else (None, None)
    if k == "ib":
        i = _int_in_range(1, 13)
        return ("IB", f"IB Year {i}") if i is not None else (None, None)
    if k == "igcse":
        i = _int_in_range(6, 12)
        # Treat as "Grade" if it looks like a typical IGCSE year range.
        return ("IGCSE", f"IGCSE Grade {i}") if i is not None else (None, None)
    return None, None

