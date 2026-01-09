from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

try:
    # When imported as a package module (e.g., `TutorDexAggregator.hard_validator`).
    from .canonicalize import canonicalize  # type: ignore
    from .support_checks import has_remarks_marker, rate_is_quote_like, substring_supported  # type: ignore
except Exception:
    # When running from `TutorDexAggregator/` with that folder on sys.path.
    from canonicalize import canonicalize  # type: ignore
    from support_checks import has_remarks_marker, rate_is_quote_like, substring_supported  # type: ignore


_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")

_TIME_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")


def _violation(path: str, code: str, message: str, evidence: Optional[str] = None) -> Dict[str, Any]:
    v: Dict[str, Any] = {"path": path, "code": code, "message": message}
    if evidence:
        v["evidence"] = evidence[:200]
    return v


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    s = str(value).strip()
    return s or None


def _coerce_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Accept only simple numeric strings.
        if re.fullmatch(r"-?\d+(?:\.\d+)?", s):
            try:
                return float(s)
            except Exception:
                return None
    return None


def _empty_time_availability() -> Dict[str, Any]:
    def _days_obj() -> Dict[str, List[str]]:
        return {d: [] for d in _DAYS}

    return {"explicit": _days_obj(), "estimated": _days_obj(), "note": None}


def _validate_time_slot(slot: Any) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (cleaned_slot, error_message).
    """
    if slot is None:
        return None, "null_slot"
    if not isinstance(slot, str):
        return None, "non_string_slot"
    s = slot.strip()
    if not s:
        return None, "empty_slot"

    # Normalize common non-ASCII dashes to hyphen for safety.
    s = s.replace("–", "-").replace("—", "-").replace("−", "-").replace("‒", "-")
    s = re.sub(r"\s*-\s*", "-", s)

    if not _TIME_RE.match(s):
        return None, "format"

    try:
        start, end = s.split("-", 1)
        sh, sm = start.split(":")
        eh, em = end.split(":")
        sh_i, sm_i, eh_i, em_i = int(sh), int(sm), int(eh), int(em)
        if not (0 <= sh_i <= 23 and 0 <= eh_i <= 23 and 0 <= sm_i <= 59 and 0 <= em_i <= 59):
            return None, "clock"
        if (sh_i, sm_i) > (eh_i, em_i):
            return None, "start_after_end"
    except Exception:
        return None, "parse"

    return s, None


def hard_validate(
    parsed: Dict[str, Any],
    *,
    raw_text: str,
    normalized_text: Optional[str] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Hard validator: null/drop invalid values and record why.

    Output schema hardened here focuses on:
    - learning_mode
    - address/postal_code/nearest_mrt
    - postal_code_estimated (best-effort fallback)
    - lesson_schedule
    - start_date
    - time_availability
    - rate
    - additional_remarks
    """
    data: Dict[str, Any] = deepcopy(parsed or {})
    violations: List[Dict[str, Any]] = []

    # -------------------------
    # Scalar strings
    # -------------------------
    for k in ("assignment_code", "academic_display_text", "start_date"):
        if k in data and data.get(k) is not None and not isinstance(data.get(k), str):
            violations.append(_violation(k, "TYPE", "Expected string or null"))
            data[k] = None
        if k in data:
            data[k] = _safe_str(data.get(k))

    # -------------------------
    # learning_mode
    # -------------------------
    lm = data.get("learning_mode")
    if not isinstance(lm, dict):
        if lm is not None:
            violations.append(_violation("learning_mode", "TYPE", "Expected object"))
        lm = {"mode": None, "raw_text": None}
    mode = lm.get("mode")
    if mode is not None and mode not in {"Online", "Face-to-Face", "Hybrid"}:
        violations.append(_violation("learning_mode.mode", "ENUM", "Invalid mode"))
        mode = None
    raw_lm = lm.get("raw_text")
    if raw_lm is not None and not isinstance(raw_lm, str):
        violations.append(_violation("learning_mode.raw_text", "TYPE", "Expected string or null"))
        raw_lm = None
    data["learning_mode"] = {"mode": mode, "raw_text": _safe_str(raw_lm)}

    # -------------------------
    # list[str] fields
    # -------------------------
    def _clean_str_list(path: str, value: Any) -> Optional[List[str]]:
        if value is None:
            return None
        if not isinstance(value, list):
            violations.append(_violation(path, "TYPE", "Expected list of strings or null"))
            return None
        out: List[str] = []
        for i, item in enumerate(value):
            if not isinstance(item, str):
                violations.append(_violation(f"{path}[{i}]", "TYPE", "Expected string"))
                continue
            s = item.strip()
            if not s:
                continue
            out.append(s)
        return out or None

    for k in ("address", "postal_code", "postal_code_estimated", "nearest_mrt", "lesson_schedule"):
        if k in data:
            data[k] = _clean_str_list(k, data.get(k))

    # -------------------------
    # time_availability structure + slot validation
    # -------------------------
    ta = data.get("time_availability")
    if not isinstance(ta, dict):
        if ta is not None:
            violations.append(_violation("time_availability", "TYPE", "Expected object"))
        ta = _empty_time_availability()

    explicit = ta.get("explicit")
    estimated = ta.get("estimated")
    note = ta.get("note")
    if note is not None and not isinstance(note, str):
        violations.append(_violation("time_availability.note", "TYPE", "Expected string or null"))
        note = None
    note = _safe_str(note)

    def _clean_day_map(path: str, m: Any) -> Dict[str, List[str]]:
        if not isinstance(m, dict):
            violations.append(_violation(path, "TYPE", "Expected object"))
            return {d: [] for d in _DAYS}
        out: Dict[str, List[str]] = {}
        for d in _DAYS:
            val = m.get(d)
            if val is None:
                out[d] = []
                continue
            if not isinstance(val, list):
                violations.append(_violation(f"{path}.{d}", "TYPE", "Expected list"))
                out[d] = []
                continue
            cleaned_slots: List[str] = []
            for i, slot in enumerate(val):
                cleaned, err = _validate_time_slot(slot)
                if err:
                    violations.append(_violation(f"{path}.{d}[{i}]", "TIME", f"Invalid time slot ({err})", evidence=str(slot)))
                    continue
                if cleaned:
                    cleaned_slots.append(cleaned)
            out[d] = cleaned_slots
        return out

    explicit_clean = _clean_day_map("time_availability.explicit", explicit)
    estimated_clean = _clean_day_map("time_availability.estimated", estimated)
    data["time_availability"] = {"explicit": explicit_clean, "estimated": estimated_clean, "note": note}

    # -------------------------
    # rate structure + invariants
    # -------------------------
    rate = data.get("rate")
    if not isinstance(rate, dict):
        if rate is not None:
            violations.append(_violation("rate", "TYPE", "Expected object"))
        rate = {"min": None, "max": None, "raw_text": None}

    rate_raw = rate.get("raw_text")
    if rate_raw is not None and not isinstance(rate_raw, str):
        violations.append(_violation("rate.raw_text", "TYPE", "Expected string or null"))
        rate_raw = None
    rate_raw_s = _safe_str(rate_raw)

    rmin_raw = rate.get("min")
    rmax_raw = rate.get("max")
    rmin = _coerce_number(rmin_raw)
    rmax = _coerce_number(rmax_raw)
    if rmin_raw is not None and rmin is None:
        violations.append(_violation("rate.min", "TYPE", "Expected number or numeric string"))
    if rmax_raw is not None and rmax is None:
        violations.append(_violation("rate.max", "TYPE", "Expected number or numeric string"))

    if (rmin is not None or rmax is not None) and not rate_raw_s:
        violations.append(_violation("rate", "RATE", "min/max present but raw_text is null"))
        rmin, rmax = None, None

    if rate_is_quote_like(rate_raw_s):
        if rmin is not None or rmax is not None:
            violations.append(_violation("rate", "RATE", "Quote-like raw_text; forcing min/max null"))
        rmin, rmax = None, None

    if rmin is not None and rmax is not None and rmin > rmax:
        violations.append(_violation("rate", "RATE", "min > max; forcing both null"))
        rmin, rmax = None, None

    data["rate"] = {"min": rmin, "max": rmax, "raw_text": rate_raw_s}

    # -------------------------
    # tutor_types + rate_breakdown
    # -------------------------
    tt = data.get("tutor_types")
    if tt is None:
        validated_tt = None
    else:
        if not isinstance(tt, list):
            violations.append(_violation("tutor_types", "TYPE", "Expected list or null"))
            validated_tt = None
        else:
            validated_items = []
            for i, item in enumerate(tt):
                if not isinstance(item, dict):
                    violations.append(_violation(f"tutor_types[{i}]", "TYPE", "Expected object"))
                    continue
                canon = _safe_str(item.get("canonical"))
                orig = _safe_str(item.get("original"))
                agency_field = _safe_str(item.get("agency"))
                conf_raw = item.get("confidence")
                try:
                    conf = float(conf_raw) if conf_raw is not None else None
                except Exception:
                    conf = None
                if canon is None:
                    violations.append(_violation(f"tutor_types[{i}].canonical", "REQUIRED", "Missing canonical"))
                    continue
                if conf is not None and not (0.0 <= conf <= 1.0):
                    violations.append(_violation(f"tutor_types[{i}].confidence", "RANGE", "Expected 0.0-1.0"))
                    conf = None
                validated_items.append({"canonical": canon, "original": orig, "agency": agency_field, "confidence": conf})
            validated_tt = validated_items or None
    data["tutor_types"] = validated_tt

    rb = data.get("rate_breakdown")
    if rb is None:
        validated_rb = None
    else:
        if not isinstance(rb, dict):
            violations.append(_violation("rate_breakdown", "TYPE", "Expected object/dict or null"))
            validated_rb = None
        else:
            validated_map: Dict[str, Dict[str, Any]] = {}
            for k, v in rb.items():
                if not isinstance(v, dict):
                    violations.append(_violation(f"rate_breakdown.{k}", "TYPE", "Expected object"))
                    continue
                min_raw = v.get("min")
                max_raw = v.get("max")
                min_n = _coerce_number(min_raw)
                max_n = _coerce_number(max_raw)
                if min_raw is not None and min_n is None:
                    violations.append(_violation(f"rate_breakdown.{k}.min", "TYPE", "Expected number or null"))
                if max_raw is not None and max_n is None:
                    violations.append(_violation(f"rate_breakdown.{k}.max", "TYPE", "Expected number or null"))
                orig_text = _safe_str(v.get("original_text"))
                currency = _safe_str(v.get("currency"))
                unit = _safe_str(v.get("unit"))
                conf_raw = v.get("confidence")
                try:
                    conf = float(conf_raw) if conf_raw is not None else None
                except Exception:
                    conf = None
                if conf is not None and not (0.0 <= conf <= 1.0):
                    violations.append(_violation(f"rate_breakdown.{k}.confidence", "RANGE", "Expected 0.0-1.0"))
                    conf = None
                # enforce min<=max
                if min_n is not None and max_n is not None and min_n > max_n:
                    violations.append(_violation(f"rate_breakdown.{k}", "RATE", "min>max; forcing null"))
                    min_n = None
                    max_n = None
                validated_map[k] = {"min": min_n, "max": max_n, "original_text": orig_text, "currency": currency, "unit": unit, "confidence": conf}
            validated_rb = validated_map or None
    data["rate_breakdown"] = validated_rb

    # -------------------------
    # additional_remarks support guard
    # -------------------------
    if "additional_remarks" in data:
        ar = data.get("additional_remarks")
        if ar is not None and not isinstance(ar, str):
            violations.append(_violation("additional_remarks", "TYPE", "Expected string or null"))
            ar = None
        ar_s = _safe_str(ar)
        if ar_s:
            if not has_remarks_marker(raw_text):
                violations.append(_violation("additional_remarks", "SUPPORT", "No remarks marker in raw; forcing null"))
                ar_s = None
            elif not substring_supported(raw_text, ar_s):
                violations.append(_violation("additional_remarks", "SUPPORT", "Not supported by raw text; forcing null"))
                ar_s = None
        data["additional_remarks"] = ar_s

    # Canonicalize trivial formatting/duplicates after validation.
    data = canonicalize(data)
    return data, violations
