from __future__ import annotations

from typing import Any, Dict, List, Optional


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    s = value.strip()
    return s or None


def _dedupe_str_list(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else None
    if not isinstance(value, list):
        return None
    out: List[str] = []
    seen = set()
    for item in value:
        s = _safe_str(item)
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out or None


def canonicalize(parsed: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic canonicalization: trim strings, de-dupe arrays, drop empty strings.
    Does not infer new values or reformat authoritative raw snippets.
    """
    data: Dict[str, Any] = dict(parsed or {})

    for k in ("assignment_code", "academic_display_text", "start_date", "additional_remarks"):
        if k in data:
            data[k] = _safe_str(data.get(k))

    # address-like lists
    for k in ("address", "postal_code", "nearest_mrt", "lesson_schedule"):
        if k in data:
            data[k] = _dedupe_str_list(data.get(k))

    # nested objects
    lm = data.get("learning_mode")
    if isinstance(lm, dict):
        data["learning_mode"] = {
            "mode": lm.get("mode"),
            "raw_text": _safe_str(lm.get("raw_text")),
        }

    rate = data.get("rate")
    if isinstance(rate, dict):
        data["rate"] = {
            "min": rate.get("min"),
            "max": rate.get("max"),
            "raw_text": _safe_str(rate.get("raw_text")),
        }

    ta = data.get("time_availability")
    if isinstance(ta, dict):
        note = _safe_str(ta.get("note"))
        data["time_availability"] = {
            "explicit": ta.get("explicit"),
            "estimated": ta.get("estimated"),
            "note": note,
        }

    return data

