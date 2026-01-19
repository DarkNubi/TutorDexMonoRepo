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
    for k in ("address", "postal_code", "postal_code_estimated", "nearest_mrt", "lesson_schedule"):
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

    # Tutor types canonicalization: normalize labels via shared taxonomy
    try:
        try:
            from shared.taxonomy.tutor_types import normalize_label  # type: ignore
        except Exception:
            from TutorDexAggregator.shared.taxonomy.tutor_types import normalize_label  # type: ignore
    except Exception:
        normalize_label = None  # type: ignore

    tt = data.get("tutor_types")
    if isinstance(tt, list) and normalize_label is not None:
        out_tt: List[Dict[str, Optional[str]]] = []
        seen = set()
        for item in tt:
            if not isinstance(item, dict):
                continue
            orig = None
            if item.get("original"):
                orig = _safe_str(item.get("original"))
            elif item.get("label"):
                orig = _safe_str(item.get("label"))
            elif item.get("raw"):
                orig = _safe_str(item.get("raw"))
            else:
                # as a last resort, try `name` key
                orig = _safe_str(item.get("name"))
            canon = None
            conf = None
            agency = _safe_str(item.get("agency")) if isinstance(item.get("agency"), str) else None
            if orig:
                try:
                    c, o, cf = normalize_label(orig, agency=agency)
                    canon = c
                    conf = float(cf) if cf is not None else None
                except Exception:
                    canon = None
            # fall back to provided canonical if present
            if not canon and item.get("canonical"):
                canon = _safe_str(item.get("canonical"))
            if not canon:
                canon = "unknown"
            key = str(canon).lower()
            if key in seen:
                continue
            seen.add(key)
            out_tt.append({"canonical": canon, "original": orig, "agency": agency, "confidence": conf})
        data["tutor_types"] = out_tt or None

    # Rate breakdown normalization: ensure numeric mins/max and string fields
    rb = data.get("rate_breakdown")
    if isinstance(rb, dict):
        out_rb: Dict[str, Dict[str, Optional[object]]] = {}
        for k, v in rb.items():
            if not isinstance(v, dict):
                continue
            try:
                min_v = v.get("min")
                v.get("max")
                min_n = int(min_v) if min_v is not None else None
            except Exception:
                try:
                    min_n = int(float(str(v.get("min"))))
                except Exception:
                    min_n = None
            try:
                max_n = int(v.get("max")) if v.get("max") is not None else None
            except Exception:
                try:
                    max_n = int(float(str(v.get("max"))))
                except Exception:
                    max_n = None
            out_rb[k] = {
                "min": min_n,
                "max": max_n,
                "original_text": _safe_str(v.get("original_text")),
                "currency": _safe_str(v.get("currency")),
                "unit": _safe_str(v.get("unit")),
                "confidence": (float(v.get("confidence")) if v.get("confidence") is not None else None),
            }
        data["rate_breakdown"] = out_rb or None

    return data
