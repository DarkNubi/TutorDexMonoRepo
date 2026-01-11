from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

try:
    from shared.taxonomy.tutor_types import normalize_label  # type: ignore
except Exception:
    try:
        from TutorDexAggregator.shared.taxonomy.tutor_types import normalize_label  # type: ignore
    except Exception:
        # best-effort fallback: simple local normalizer
        def normalize_label(label: str, agency: Optional[str] = None) -> Tuple[str, str, float]:
            s = (label or "").strip().lower()
            if not s:
                return "unknown", label or "", 0.0
            if "part" in s or s == "pt":
                return "part-timer", label or "", 0.6
            if "full" in s or s == "ft":
                return "full-timer", label or "", 0.6
            if "moe" in s:
                return "moe-exmoe", label or "", 0.6
            return "unknown", label or "", 0.0


_RATE_RE = re.compile(
    r"(?P<prefix>\$?)\s*(?P<min>\d+(?:[\.,]\d+)?)\s*(?:[-–—]\s*(?P<max>\d+(?:[\.,]\d+)?))?\s*(?P<unit>/h|/hr|hr|per hour|p/h|p.h)?", flags=re.IGNORECASE)


def _parse_number(s: str) -> Optional[int]:
    try:
        if s is None:
            return None
        s2 = str(s).replace(",", ".").strip()
        f = float(s2)
        return int(round(f))
    except Exception:
        return None


def extract_tutor_types(*, text: str, parsed: Optional[Dict[str, Any]] = None, agency: Optional[str] = None) -> Dict[str, Any]:
    s = str(text or "")
    out_types: Dict[str, Dict[str, Any]] = {}
    rate_breakdown: Dict[str, Dict[str, Any]] = {}

    # 1) Find all rate-like spans and attempt to associate with nearby type label
    for m in _RATE_RE.finditer(s):
        span = m.span()
        window_start = max(0, span[0] - 40)
        window_end = min(len(s), span[1] + 40)
        window = s[window_start:window_end]
        raw = s[span[0]:span[1]]
        min_n = _parse_number(m.group("min"))
        max_n = _parse_number(m.group("max"))
        if min_n is not None and max_n is None:
            max_n = min_n
        prefix = (m.group("prefix") or "").strip()
        unit = (m.group("unit") or "").strip()
        if not prefix and not unit:
            continue
        if min_n is None and max_n is None:
            continue

        # search for alias tokens in the window
        tokens = re.findall(r"[A-Za-z0-9\-\/]+", window)
        found_canon = None
        found_orig = None
        for i in range(len(tokens)):
            for j in range(i, min(len(tokens), i + 3)):
                phrase = " ".join(tokens[i: j + 1])
                canon, orig, conf = normalize_label(phrase, agency=agency)
                if canon and canon != "unknown":
                    found_canon = canon
                    found_orig = orig
                    break
            if found_canon:
                break

        if found_canon:
            rate_breakdown.setdefault(found_canon, {})
            rate_breakdown[found_canon].update(
                {
                    "min": min_n,
                    "max": max_n,
                    "currency": "$" if prefix == "$" else None,
                    "unit": "hour" if unit else None,
                    "original_text": raw,
                    "confidence": 0.9,
                }
            )
            out_types.setdefault(found_canon, {"canonical": found_canon, "original": found_orig or "", "agency": agency, "confidence": 0.9})

    # 2) Scan whole text for free-standing type mentions (no rate attached)
    words = re.findall(r"[A-Za-z0-9\-\/]+", s)
    for i in range(len(words)):
        for j in range(i, min(len(words), i + 4)):
            phrase = " ".join(words[i: j + 1])
            canon, orig, conf = normalize_label(phrase, agency=agency)
            if canon and canon != "unknown":
                if canon not in out_types:
                    out_types[canon] = {"canonical": canon, "original": orig, "agency": agency, "confidence": 0.6}

    tutor_types_list: List[Dict[str, Any]] = list(out_types.values())

    return {"tutor_types": tutor_types_list, "rate_breakdown": rate_breakdown}


if __name__ == "__main__":
    sample = "FT/EX-MOE $40-55/hr, PT $25-30/hr. Fresh grad (deg) PT $20-25"
    print(extract_tutor_types(text=sample, parsed=None, agency=None))
