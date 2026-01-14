"""
Row Builder Service

Builds assignment row dictionaries from raw payloads for database persistence.
Handles field extraction, sanitization, geocoding, and signal computation.
"""
import json
import hashlib
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timezone
from shared.config import load_aggregator_config

try:
    from utils.field_coercion import (
        safe_str, normalize_sg_postal_code, coerce_int_like,
        first_text, coerce_text_list, truthy_text, truthy
    )
    from utils.timestamp_utils import coerce_iso_ts
    from geo_enrichment import enrich_from_coords
except Exception:
    from TutorDexAggregator.utils.field_coercion import (
        safe_str, normalize_sg_postal_code, coerce_int_like,
        first_text, coerce_text_list, truthy_text, truthy
    )
    from TutorDexAggregator.utils.timestamp_utils import coerce_iso_ts
    from TutorDexAggregator.geo_enrichment import enrich_from_coords


def _freshness_enabled() -> bool:
    """Check if freshness tier feature is enabled."""
    return bool(load_aggregator_config().freshness_tier_enabled)


def derive_agency(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract agency name and link from payload.
    
    Returns (agency_name, agency_link) tuple.
    """
    link = safe_str(payload.get("channel_link")) or safe_str(payload.get("channel_username"))
    title = safe_str(payload.get("channel_title"))
    if link and not link.startswith("t.me/") and not link.startswith("http"):
        link = link.lstrip("@")
        link = f"t.me/{link}"
    return title, link


def derive_external_id(payload: Dict[str, Any]) -> str:
    """
    Derive external_id from payload.
    
    Priority:
    1. assignment_code from parsed data
    2. tg:channel_id:message_id
    3. message_link
    4. cid
    5. fallback to unknown:{timestamp}
    """
    parsed = payload.get("parsed") or {}
    assignment_code = safe_str(parsed.get("assignment_code"))
    if assignment_code:
        return assignment_code

    channel_id = payload.get("channel_id")
    message_id = payload.get("message_id")
    if channel_id is not None and message_id is not None:
        return f"tg:{channel_id}:{message_id}"

    message_link = safe_str(payload.get("message_link"))
    if message_link:
        return message_link

    cid = safe_str(payload.get("cid"))
    if cid:
        return cid

    return f"unknown:{int(datetime.now(timezone.utc).timestamp())}"


def compute_parse_quality(row_like: Dict[str, Any]) -> int:
    """
    Simple heuristic score used to prevent low-quality reposts from overwriting richer data.
    
    Scores:
    - academic_display_text: +3
    - assignment_code: +1
    - signals_subjects: +2
    - signals_levels or signals_specific_student_levels: +1
    - location (address/postal/mrt): +2
    - rate info: +1
    - lesson_schedule: +1
    - time_availability: +1
    - region: +1
    - nearest_mrt_computed: +1
    """
    score = 0
    if truthy_text(row_like.get("academic_display_text")):
        score += 3
    if truthy_text(row_like.get("assignment_code")):
        score += 1
    if truthy_text(row_like.get("signals_subjects")):
        score += 2
    if truthy_text(row_like.get("signals_levels")) or truthy_text(row_like.get("signals_specific_student_levels")):
        score += 1
    if truthy_text(row_like.get("address")) or truthy_text(row_like.get("postal_code")) or truthy_text(row_like.get("postal_code_estimated")) or truthy_text(row_like.get("nearest_mrt")):
        score += 2
    if row_like.get("rate_min") is not None or row_like.get("rate_max") is not None or truthy_text(row_like.get("rate_raw_text")):
        score += 1
    if truthy_text(row_like.get("lesson_schedule")):
        score += 1
    if row_like.get("time_availability_explicit") is not None or row_like.get("time_availability_estimated") is not None or truthy_text(row_like.get("time_availability_note")):
        score += 1
    if truthy_text(row_like.get("region")):
        score += 1
    if truthy_text(row_like.get("nearest_mrt_computed")):
        score += 1
    return int(score)


def sanitize_tutor_types(tt: Any) -> Optional[List[Dict[str, Any]]]:
    """
    Sanitize tutor_types to ensure list of dicts with canonical, original, agency, confidence(float).
    """
    if not tt:
        return None
    if not isinstance(tt, (list, tuple)):
        return None
    out = []
    for item in tt:
        if not isinstance(item, dict):
            continue
        canonical = safe_str(item.get("canonical") or item.get("canonical_name") or item.get("canonical"))
        if not canonical:
            continue
        original = safe_str(item.get("original") or item.get("label") or item.get("raw"))
        agency = safe_str(item.get("agency"))
        conf = None
        try:
            if item.get("confidence") is not None:
                conf = float(item.get("confidence"))
        except Exception:
            conf = None
        out.append({
            "canonical": canonical,
            "original": original,
            "agency": agency,
            "confidence": conf,
        })
    return out or None


def sanitize_rate_breakdown(rb: Any) -> Optional[Dict[str, Dict[str, Any]]]:
    """
    Sanitize rate_breakdown to ensure dict of dicts with min, max, currency, unit, original_text, confidence.
    """
    if not rb:
        return None
    if not isinstance(rb, dict):
        return None
    out = {}
    for k, v in rb.items():
        if not isinstance(v, dict):
            continue
        try:
            min_v = coerce_int_like(v.get("min"))
        except Exception:
            min_v = None
        try:
            max_v = coerce_int_like(v.get("max"))
        except Exception:
            max_v = None
        currency = safe_str(v.get("currency"))
        unit = safe_str(v.get("unit"))
        original_text = safe_str(v.get("original_text") or v.get("raw_text"))
        conf = None
        try:
            if v.get("confidence") is not None:
                conf = float(v.get("confidence"))
        except Exception:
            conf = None
        out[str(k)] = {
            "min": min_v,
            "max": max_v,
            "currency": currency,
            "unit": unit,
            "original_text": original_text,
            "confidence": conf,
        }
    return out or None


def build_signals(parsed: Dict[str, Any], raw_text: str, normalized_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Build signals from parsed data (fallback if not computed upstream).
    """
    try:
        try:
            from signals_builder import build_signals as build_signals_impl
            from normalize import normalize_text
        except Exception:
            from TutorDexAggregator.signals_builder import build_signals as build_signals_impl
            from TutorDexAggregator.normalize import normalize_text
        
        sig, err = build_signals_impl(parsed=parsed, raw_text=raw_text, normalized_text=normalized_text)
        if not err and isinstance(sig, dict):
            return sig, None
        return None, err
    except Exception as e:
        return None, str(e)


def build_assignment_row(payload: Dict[str, Any], geocode_func=None) -> Dict[str, Any]:
    """
    Build assignment row from payload.
    
    Args:
        payload: Raw payload dict with parsed data, meta, etc.
        geocode_func: Optional geocoding function (lat, lon) = f(postal_code)
    
    Returns:
        Dict suitable for database insertion/update
    """
    parsed = payload.get("parsed") or {}
    agency_name, agency_link = derive_agency(payload)

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    signals_meta = meta.get("signals") if isinstance(meta.get("signals"), dict) else None
    signals_obj: Optional[Dict[str, Any]] = None
    if signals_meta and signals_meta.get("ok") is True and isinstance(signals_meta.get("signals"), dict):
        signals_obj = signals_meta.get("signals")

    # Fallback: if signals were not computed upstream, compute them here (best-effort).
    if signals_obj is None:
        raw_text = str(payload.get("raw_text") or "")
        try:
            from normalize import normalize_text
        except Exception:
            from TutorDexAggregator.normalize import normalize_text
        normalized_text = normalize_text(raw_text) if raw_text else ""
        sig, err = build_signals(parsed=parsed, raw_text=raw_text, normalized_text=normalized_text)
        if not err and isinstance(sig, dict):
            signals_obj = sig

    def _opt_list(value: Any) -> Optional[List[str]]:
        vals = coerce_text_list(value)
        return vals or None

    def _coerce_dict(value: Any) -> Optional[Dict[str, Any]]:
        return value if isinstance(value, dict) else None

    # v2 display fields
    assignment_code = safe_str(parsed.get("assignment_code")) if isinstance(parsed, dict) else None
    academic_display_text = safe_str(parsed.get("academic_display_text")) if isinstance(parsed, dict) else None

    lm_mode = None
    lm_raw = None
    lm = parsed.get("learning_mode") if isinstance(parsed, dict) else None
    if isinstance(lm, dict):
        lm_mode = safe_str(lm.get("mode"))
        lm_raw = safe_str(lm.get("raw_text"))
    else:
        lm_mode = safe_str(lm)

    address = _opt_list(parsed.get("address") if isinstance(parsed, dict) else None)
    postal_codes = coerce_text_list(parsed.get("postal_code") if isinstance(parsed, dict) else None)
    postal_code = postal_codes[0] if postal_codes else None
    postal_code_list = _opt_list(postal_codes)
    postal_code_estimated = _opt_list(parsed.get("postal_code_estimated") if isinstance(parsed, dict) else None)
    nearest_mrt = _opt_list(parsed.get("nearest_mrt") if isinstance(parsed, dict) else None)
    lesson_schedule = _opt_list(parsed.get("lesson_schedule") if isinstance(parsed, dict) else None)
    start_date = safe_str(parsed.get("start_date")) if isinstance(parsed, dict) else None

    ta = parsed.get("time_availability") if isinstance(parsed, dict) else None
    if not isinstance(ta, dict):
        ta = {}
    ta_note = safe_str(ta.get("note"))
    ta_explicit = _coerce_dict(ta.get("explicit"))
    ta_estimated = _coerce_dict(ta.get("estimated"))

    rate = parsed.get("rate") if isinstance(parsed, dict) else None
    if not isinstance(rate, dict):
        rate = {}
    rate_min = coerce_int_like(rate.get("min"))
    rate_max = coerce_int_like(rate.get("max"))
    rate_raw_text = safe_str(rate.get("raw_text"))
    
    # New: per-type tutor types and rate breakdown (optional)
    # Prefer deterministic signals (rule-based extractor) provided in `meta.signals` over LLM `parsed` outputs.
    tutor_types = parsed.get("tutor_types") if isinstance(parsed, dict) else None
    rate_breakdown = parsed.get("rate_breakdown") if isinstance(parsed, dict) else None
    
    # If signals_obj contains deterministic detections, prefer those.
    try:
        if isinstance(signals_obj, dict):
            sig_tt = signals_obj.get("tutor_types")
            sig_rb = signals_obj.get("rate_breakdown")
            if sig_tt:
                tutor_types = sig_tt
            if sig_rb:
                rate_breakdown = sig_rb
    except Exception:
        pass

    tutor_types = sanitize_tutor_types(tutor_types)
    rate_breakdown = sanitize_rate_breakdown(rate_breakdown)

    additional_remarks = safe_str(parsed.get("additional_remarks")) if isinstance(parsed, dict) else None

    # Deterministic signals rollups (optional, but default enabled).
    signals_subjects = coerce_text_list(signals_obj.get("subjects") if isinstance(signals_obj, dict) else None)
    signals_levels = coerce_text_list(signals_obj.get("levels") if isinstance(signals_obj, dict) else None)
    signals_specific = coerce_text_list(signals_obj.get("specific_student_levels") if isinstance(signals_obj, dict) else None)
    signals_streams = coerce_text_list(signals_obj.get("streams") if isinstance(signals_obj, dict) else None)
    signals_academic_requests = signals_obj.get("academic_requests") if isinstance(signals_obj, dict) else None
    signals_confidence_flags = signals_obj.get("confidence_flags") if isinstance(signals_obj, dict) else None

    # v2 subject taxonomy (stable codes) used for filtering/matching across the system.
    subjects_canonical = coerce_text_list(signals_obj.get("subjects_canonical") if isinstance(signals_obj, dict) else None)
    subjects_general = coerce_text_list(signals_obj.get("subjects_general") if isinstance(signals_obj, dict) else None)
    canonicalization_version = None
    canonicalization_debug = None
    if isinstance(signals_obj, dict):
        canonicalization_version = signals_obj.get("canonicalization_version")
        canonicalization_debug = signals_obj.get("canonicalization_debug")

    # TutorCity API: prefer the explicit API mappings (level label + subject labels).
    if str(payload.get("source_type") or "").strip().lower() == "tutorcity_api":
        try:
            src_mapped = meta.get("source_mapped") if isinstance(meta.get("source_mapped"), dict) else {}
            lvl = safe_str(src_mapped.get("level"))
            subs = src_mapped.get("subjects") if isinstance(src_mapped, dict) else None
            if subs is not None:
                try:
                    from taxonomy.canonicalize_subjects import canonicalize_subjects
                except Exception:
                    from TutorDexAggregator.taxonomy.canonicalize_subjects import canonicalize_subjects

                res = canonicalize_subjects(level=lvl, subjects=subs)
                subjects_canonical = coerce_text_list(res.get("subjects_canonical"))
                subjects_general = coerce_text_list(res.get("subjects_general"))
                canonicalization_version = res.get("canonicalization_version")
                canonicalization_debug = res.get("debug")
        except Exception:
            pass

    postal_lat = None
    postal_lon = None
    postal_coords_estimated = False

    # Geocoding: try explicit postal code first, then estimated
    if geocode_func:
        if postal_code:
            coords = geocode_func(postal_code)
            if coords:
                postal_lat, postal_lon = coords

        # If no explicit postal code or geocoding failed, try estimated postal code
        if postal_lat is None and postal_lon is None and postal_code_estimated:
            estimated_codes = coerce_text_list(postal_code_estimated)
            if estimated_codes:
                first_estimated = estimated_codes[0]
                coords = geocode_func(first_estimated)
                if coords:
                    postal_lat, postal_lon = coords
                    postal_coords_estimated = True

    region = None
    nearest_mrt_computed = None
    nearest_mrt_computed_line = None
    nearest_mrt_computed_distance_m = None
    geo_meta: Optional[Dict[str, Any]] = None
    if postal_lat is not None and postal_lon is not None:
        try:
            geo = enrich_from_coords(lat=postal_lat, lon=postal_lon)
            region = geo.region
            nearest_mrt_computed = geo.nearest_mrt
            nearest_mrt_computed_line = geo.nearest_mrt_line
            nearest_mrt_computed_distance_m = geo.nearest_mrt_distance_m
            geo_meta = geo.meta if isinstance(geo.meta, dict) else None
        except Exception:
            geo_meta = {"ok": False, "error": "geo_enrichment_failed"}

    # TutorCity API semantics: repeated assignment_code rows are updates, not separate assignments.
    # Record a stable upstream fingerprint so we can detect true upstream changes without letting
    # the poll loop continuously bump freshness.
    try:
        if str(payload.get("source_type") or "").strip().lower() == "tutorcity_api" and isinstance(meta, dict):
            src = meta.get("source_raw") if isinstance(meta.get("source_raw"), dict) else meta.get("source_mapped")
            if isinstance(src, dict):
                s = json.dumps(src, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                meta = dict(meta)
                meta["tutorcity_fingerprint"] = hashlib.sha256(s.encode("utf-8")).hexdigest()
    except Exception:
        pass

    # Telegram status detection (opt-in allowlist).
    try:
        from TutorDexAggregator.extractors.status_detector import detect_status, detection_meta
    except Exception:
        try:
            from extractors.status_detector import detect_status, detection_meta
        except Exception:
            detect_status = None
            detection_meta = None

    detected_status: Optional[str] = None
    if detect_status is not None:
        try:
            det = detect_status(raw_text=payload.get("raw_text"), channel_link=payload.get(
                "channel_link"), channel_username=payload.get("channel_username"))
        except Exception:
            det = None
        if det is not None:
            detected_status = str(getattr(det, "status", "") or "").strip().lower() or None
            if isinstance(meta, dict) and detection_meta is not None:
                meta = dict(meta)
                meta["status_detection"] = detection_meta(det)

    row: Dict[str, Any] = {
        "external_id": derive_external_id(payload),
        "agency_id": None,
        "agency_name": agency_name,
        "agency_link": agency_link,
        # Source publish time (Telegram message date, or first-seen for API sources).
        "published_at": coerce_iso_ts(payload.get("date")),
        # Last upstream bump/edit/repost time (Telegram edit_date or similar).
        "source_last_seen": coerce_iso_ts(payload.get("source_last_seen") or payload.get("date")),
        "channel_id": payload.get("channel_id"),
        "message_id": payload.get("message_id"),
        "message_link": safe_str(payload.get("message_link")),
        "raw_text": safe_str(payload.get("raw_text")),
        "assignment_code": assignment_code,
        "academic_display_text": academic_display_text,
        "learning_mode": lm_mode,
        "learning_mode_raw_text": lm_raw,
        "address": address,
        "postal_code": postal_code_list,
        "postal_code_estimated": postal_code_estimated,
        "postal_lat": postal_lat,
        "postal_lon": postal_lon,
        "postal_coords_estimated": postal_coords_estimated,
        "nearest_mrt": nearest_mrt,
        "region": region,
        "nearest_mrt_computed": nearest_mrt_computed,
        "nearest_mrt_computed_line": nearest_mrt_computed_line,
        "nearest_mrt_computed_distance_m": nearest_mrt_computed_distance_m,
        "lesson_schedule": lesson_schedule,
        "start_date": start_date,
        "time_availability_note": ta_note,
        "time_availability_explicit": ta_explicit,
        "time_availability_estimated": ta_estimated,
        "rate_min": rate_min,
        "rate_max": rate_max,
        "rate_raw_text": rate_raw_text,
        "tutor_types": tutor_types,
        "rate_breakdown": rate_breakdown,
        "additional_remarks": additional_remarks,
        "signals_subjects": signals_subjects,
        "signals_levels": signals_levels,
        "signals_specific_student_levels": signals_specific,
        "signals_streams": signals_streams,
        "signals_academic_requests": signals_academic_requests,
        "signals_confidence_flags": signals_confidence_flags,
        "subjects_canonical": subjects_canonical,
        "subjects_general": subjects_general,
        "canonicalization_version": int(canonicalization_version) if isinstance(canonicalization_version, (int, float)) else None,
        "canonicalization_debug": canonicalization_debug if bool(load_aggregator_config().subject_taxonomy_debug) and isinstance(canonicalization_debug, dict) else None,
        "canonical_json": parsed if isinstance(parsed, dict) else None,
        "meta": meta if isinstance(meta, dict) else None,
    }
    if detected_status in {"open", "closed"}:
        row["status"] = detected_status
    if geo_meta is not None and isinstance(row.get("meta"), dict):
        try:
            row["meta"] = dict(row["meta"])
            row["meta"]["geo_enrichment"] = geo_meta
        except Exception:
            pass

    row["parse_quality_score"] = compute_parse_quality(row)
    if _freshness_enabled():
        row["freshness_tier"] = "green"
    
    # Keep empty signal rollups as empty arrays (DB defaults also do this).
    row["signals_subjects"] = row.get("signals_subjects") or []
    row["signals_levels"] = row.get("signals_levels") or []
    row["signals_specific_student_levels"] = row.get("signals_specific_student_levels") or []
    row["signals_streams"] = row.get("signals_streams") or []
    row["subjects_canonical"] = row.get("subjects_canonical") or []
    row["subjects_general"] = row.get("subjects_general") or []
    return {k: v for k, v in row.items() if v is not None}
