from __future__ import annotations

import re
from typing import Optional, Tuple


def _norm_token_key(value: str) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    # Normalize common separators and punctuation into spaces so that:
    # - "pre-u" == "pre u"
    # - "o-level" == "o level"
    # - "j.c." == "jc"
    s = s.replace("_", " ").replace("-", " ")
    s = re.sub(r"[./()]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_LEVEL_CANON: dict[str, str] = {
    # Pre-school
    "pre school": "Pre-School",
    "preschool": "Pre-School",
    "pre-school": "Pre-School",
    "kindergarten": "Pre-School",
    "kinder": "Pre-School",
    "kg": "Pre-School",
    "nursery": "Pre-School",
    "childcare": "Pre-School",
    "child care": "Pre-School",
    "pre k": "Pre-School",
    "prek": "Pre-School",
    # Primary
    "primary": "Primary",
    "primary school": "Primary",
    "pri": "Primary",
    "psle": "Primary",
    "p s l e": "Primary",
    # Secondary
    "secondary": "Secondary",
    "secondary school": "Secondary",
    "sec": "Secondary",
    "o level": "Secondary",
    "o levels": "Secondary",
    "olevel": "Secondary",
    "olevels": "Secondary",
    "n level": "Secondary",
    "n levels": "Secondary",
    "nlevel": "Secondary",
    "nlevels": "Secondary",
    # Junior College / pre-U
    "junior college": "Junior College",
    "juniorcollege": "Junior College",
    "jc": "Junior College",
    "a level": "Junior College",
    "a levels": "Junior College",
    "alevel": "Junior College",
    "alevels": "Junior College",
    "pre u": "Junior College",
    "pre uni": "Junior College",
    "pre university": "Junior College",
    "preuniversity": "Junior College",
    "pre university": "Junior College",
    # International
    "ib": "IB",
    "i b": "IB",
    "international baccalaureate": "IB",
    "ib dp": "IB",
    "ibdp": "IB",
    "ib diploma": "IB",
    "diploma programme": "IB",
    "diploma program": "IB",
    "igcse": "IGCSE",
    "i g c s e": "IGCSE",
    "cambridge igcse": "IGCSE",
    "cigcse": "IGCSE",
    # Tertiary (kept for completeness; taxonomy may not map subjects for these)
    "poly": "Polytechnic",
    "polytechnic": "Polytechnic",
    "uni": "University",
    "university": "University",
    "undergraduate": "University",
    "undergrad": "University",
    "degree": "University",
    "postgraduate": "Postgraduate",
    "postgrad": "Postgraduate",
    "masters": "Postgraduate",
    "master": "Postgraduate",
    "phd": "Postgraduate",
}


_STREAM_CANON: dict[str, str] = {
    "na": "NA",
    "nt": "NT",
    "ip": "IP",
    "express": "Express",
    "exp": "Express",
    "normal academic": "NA",
    "normal acad": "NA",
    "normal technical": "NT",
    "normal tech": "NT",
    "integrated programme": "IP",
    "integrated program": "IP",
    "foundation": "Foundation",
    "hl": "HL",
    "sl": "SL",
    "higher level": "HL",
    "standard level": "SL",
    "subject based banding": "SBB",
    "sbb": "SBB",
    "arts stream": "Arts",
    "science stream": "Science",
    "commerce stream": "Commerce",
}


def canonicalize_level_token(token: str) -> Optional[str]:
    s = _norm_token_key(token)
    if not s:
        return None
    if s in _LEVEL_CANON:
        return _LEVEL_CANON[s]
    # Some sources include a trailing plural "s" ("o levels", "a levels") or punctuation.
    s2 = s[:-1].strip() if s.endswith("s") else s
    return _LEVEL_CANON.get(s2)


def canonicalize_stream_token(token: str) -> Optional[str]:
    s = _norm_token_key(token)
    if not s:
        return None
    if s in _STREAM_CANON:
        return _STREAM_CANON[s]

    m = re.fullmatch(r"g\s*([1-3])", s)
    if m:
        return f"G{m.group(1)}"
    m = re.fullmatch(r"h\s*([1-3])", s)
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
    if k == "nursery":
        i = _int_in_range(1, 2)
        return ("Pre-School", f"Nursery {i}") if i is not None else (None, None)
    if k == "ib":
        i = _int_in_range(1, 13)
        return ("IB", f"IB Year {i}") if i is not None else (None, None)
    if k == "igcse":
        i = _int_in_range(6, 12)
        # Treat as "Grade" if it looks like a typical IGCSE year range.
        return ("IGCSE", f"IGCSE Grade {i}") if i is not None else (None, None)
    return None, None
