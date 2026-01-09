import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, List
import re
import math
import json
import hashlib

import requests
from urllib.parse import urlparse

try:
    # Running from `TutorDexAggregator/` with that folder on sys.path.
    from logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
    from supabase_env import resolve_supabase_url  # type: ignore
    from geo_enrichment import enrich_from_coords  # type: ignore
except Exception:
    # Imported as `TutorDexAggregator.*` from repo root (e.g., unit tests).
    from TutorDexAggregator.logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
    from TutorDexAggregator.supabase_env import resolve_supabase_url  # type: ignore
    from TutorDexAggregator.geo_enrichment import enrich_from_coords  # type: ignore

setup_logging()
logger = logging.getLogger("supabase_persist")
_SG_POSTAL_RE = re.compile(r"\b(\d{6})\b")

try:
    from observability_metrics import worker_supabase_fail_total, versions as _obs_versions  # type: ignore
except Exception:
    worker_supabase_fail_total = None  # type: ignore
    _obs_versions = None  # type: ignore


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _freshness_enabled() -> bool:
    return _truthy(os.environ.get("FRESHNESS_TIER_ENABLED"))


def _nominatim_disabled() -> bool:
    return str(os.environ.get("DISABLE_NOMINATIM", "")).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_sg_postal_code(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    digits = re.sub(r"\D+", "", s)
    m = _SG_POSTAL_RE.search(digits)
    return m.group(1) if m else None


@lru_cache(maxsize=2048)
def _geocode_sg_postal(postal_code: str, *, timeout: int = 10) -> Optional[Tuple[float, float]]:
    if _nominatim_disabled():
        return None
    pc = _normalize_sg_postal_code(postal_code)
    if not pc:
        return None

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"Singapore {pc}", "format": "jsonv2", "limit": 1, "countrycodes": "sg"}
    headers = {"User-Agent": os.environ.get("NOMINATIM_USER_AGENT") or "TutorDexAggregator/1.0"}

    max_attempts = int(os.environ.get("NOMINATIM_RETRIES") or "3")
    backoff_s = float(os.environ.get("NOMINATIM_BACKOFF_SECONDS") or "1.0")

    resp = None
    for attempt in range(max(1, min(max_attempts, 6))):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        except Exception:
            logger.debug("postal_geocode_failed", exc_info=True)
            resp = None

        if resp is None:
            # transient network issue
            if attempt < max_attempts - 1:
                try:
                    import time
                    time.sleep(min(10.0, backoff_s * (2**attempt)))
                except Exception:
                    pass
            continue

        if resp.status_code in {429, 503} and attempt < max_attempts - 1:
            try:
                import time
                time.sleep(min(10.0, backoff_s * (2**attempt)))
            except Exception:
                pass
            continue

        if resp.status_code >= 400:
            return None
        break

    if resp is None:
        return None

    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None

    try:
        lat = float(data[0].get("lat"))
        lon = float(data[0].get("lon"))
        return (lat, lon)
    except Exception:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _coerce_iso_ts(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    s = str(value).strip()
    return s or None


def _max_iso_ts(a: Optional[str], b: Optional[str]) -> Optional[str]:
    """
    Return the later of two ISO-ish timestamps.
    If parsing fails, prefer a non-empty value deterministically.
    """
    if not a and not b:
        return None
    if not a:
        return b
    if not b:
        return a
    da = _parse_iso_dt(a)
    db = _parse_iso_dt(b)
    if da and db:
        return a if da >= db else b
    if da and not db:
        return a
    if db and not da:
        return b
    # Both unparseable: fall back to stable choice.
    return b


def _coerce_int_like(value: Any) -> Optional[int]:
    """
    Convert values like 45, 45.0, "45", "45.0" into an int.

    Returns None if the value is not safely representable as an integer (e.g. 45.5).
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


def _first_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            s = _first_text(item)
            if s:
                return s
        return None
    return _safe_str(value)


def _coerce_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(_coerce_text_list(x))
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


def _truthy_text(value: Any) -> bool:
    return any(_coerce_text_list(value))


def _compute_parse_quality(row_like: Dict[str, Any]) -> int:
    # Simple heuristic score used to prevent low-quality reposts from overwriting richer data.
    score = 0
    if _truthy_text(row_like.get("academic_display_text")):
        score += 3
    if _truthy_text(row_like.get("assignment_code")):
        score += 1
    if _truthy_text(row_like.get("signals_subjects")):
        score += 2
    if _truthy_text(row_like.get("signals_levels")) or _truthy_text(row_like.get("signals_specific_student_levels")):
        score += 1
    if _truthy_text(row_like.get("address")) or _truthy_text(row_like.get("postal_code")) or _truthy_text(row_like.get("postal_code_estimated")) or _truthy_text(row_like.get("nearest_mrt")):
        score += 2
    if row_like.get("rate_min") is not None or row_like.get("rate_max") is not None or _truthy_text(row_like.get("rate_raw_text")):
        score += 1
    if _truthy_text(row_like.get("lesson_schedule")):
        score += 1
    if row_like.get("time_availability_explicit") is not None or row_like.get("time_availability_estimated") is not None or _truthy_text(row_like.get("time_availability_note")):
        score += 1
    if _truthy_text(row_like.get("region")):
        score += 1
    if _truthy_text(row_like.get("nearest_mrt_computed")):
        score += 1
    return int(score)


def _merge_patch_body(*, existing: Dict[str, Any], incoming_row: Dict[str, Any], force_upgrade: bool = False) -> Dict[str, Any]:
    """
    Conservative merge:
    - Always update latest message pointers (message_id/message_link).
    - Allow filling missing fields.
    - Overwrite more broadly only when parse_quality_score improves.
    """
    old_score = existing.get("parse_quality_score")
    old_score_i = int(old_score) if isinstance(old_score, (int, float)) else _compute_parse_quality(existing)
    new_score_i = int(incoming_row.get("parse_quality_score") or 0)
    upgrade = force_upgrade or (new_score_i > old_score_i)

    patch: Dict[str, Any] = {}

    # Status should always be updated when explicitly detected (even if overall parse quality didn't improve).
    incoming_status = incoming_row.get("status")
    if incoming_status is not None:
        s = str(incoming_status).strip().lower()
        if s in {"open", "closed"} and str(existing.get("status") or "").strip().lower() != s:
            patch["status"] = s

    # Update "latest seen" identifiers for UI linking/debugging only when
    # the incoming record is at least as new as the existing seen timestamp,
    # or when the existing pointer is missing. This prevents an older original
    # post (processed after a bump/repost) from clobbering the pointer to the
    # more recent repost/bump message.
    try:
        existing_source = None
        if isinstance(existing.get("source_last_seen"), str) and existing.get("source_last_seen"):
            existing_source = _parse_iso_dt(existing.get("source_last_seen"))
        elif isinstance(existing.get("published_at"), str) and existing.get("published_at"):
            existing_source = _parse_iso_dt(existing.get("published_at"))
        elif isinstance(existing.get("last_seen"), str) and existing.get("last_seen"):
            existing_source = _parse_iso_dt(existing.get("last_seen"))

        incoming_source = None
        if isinstance(incoming_row.get("source_last_seen"), str) and incoming_row.get("source_last_seen"):
            incoming_source = _parse_iso_dt(incoming_row.get("source_last_seen"))
        elif isinstance(incoming_row.get("published_at"), str) and incoming_row.get("published_at"):
            incoming_source = _parse_iso_dt(incoming_row.get("published_at"))

        for k in ("message_id", "message_link"):
            # If existing pointer is missing, allow update.
            existing_ptr = existing.get(k)
            incoming_ptr = incoming_row.get(k)
            if incoming_ptr is None:
                continue
            allow = False
            if not existing_ptr:
                allow = True
            elif incoming_source is None and existing_source is None:
                # Unknown timestamps, be conservative and do not overwrite.
                allow = False
            elif incoming_source is not None and existing_source is not None:
                try:
                    allow = incoming_source >= existing_source
                except Exception:
                    allow = False
            elif incoming_source is not None and existing_source is None:
                allow = True

            if allow:
                patch[k] = incoming_ptr
    except Exception:
        # Fallback to the previous conservative behavior on any unexpected error.
        for k in ("message_id", "message_link"):
            if k in incoming_row and incoming_row.get(k) is not None:
                patch[k] = incoming_row[k]

    # Only update heavy/raw blobs when we're upgrading quality.
    if upgrade:
        for k in ("raw_text", "canonical_json", "meta"):
            if k in incoming_row and incoming_row.get(k) is not None:
                patch[k] = incoming_row[k]

    for k, v in incoming_row.items():
        if k in {"external_id", "agency_name", "agency_id", "parse_quality_score"}:
            continue
        if v is None:
            continue

        if upgrade:
            patch[k] = v
            continue

        cur = existing.get(k)
        if cur is None:
            patch[k] = v
            continue
        if isinstance(cur, str) and not cur.strip():
            patch[k] = v
            continue
        if isinstance(cur, list) and len(cur) == 0:
            patch[k] = v
            continue

    # Union signal rollups when not upgrading (preserve + add).
    if not upgrade:
        for key in ("signals_subjects", "signals_levels", "signals_specific_student_levels", "signals_streams"):
            existing_vals = _coerce_text_list(existing.get(key) or [])
            incoming_vals = _coerce_text_list(incoming_row.get(key) or [])
            if incoming_vals:
                combined = _coerce_text_list(existing_vals + incoming_vals)
                if combined != existing_vals:
                    patch[key] = combined

    # Update score to reflect the merged record.
    merged_preview = dict(existing)
    merged_preview.update(patch)
    patch["parse_quality_score"] = _compute_parse_quality(merged_preview)

    # Freshness tier is optional; enable only after applying the DB migration.
    if _freshness_enabled():
        patch["freshness_tier"] = "green"

    return patch


def _derive_agency(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    link = _safe_str(payload.get("channel_link")) or _safe_str(payload.get("channel_username"))
    title = _safe_str(payload.get("channel_title"))
    if link and not link.startswith("t.me/") and not link.startswith("http"):
        link = link.lstrip("@")
        link = f"t.me/{link}"
    return title, link


def _derive_external_id(payload: Dict[str, Any]) -> str:
    parsed = payload.get("parsed") or {}
    assignment_code = _safe_str(parsed.get("assignment_code"))
    if assignment_code:
        return assignment_code

    channel_id = payload.get("channel_id")
    message_id = payload.get("message_id")
    if channel_id is not None and message_id is not None:
        return f"tg:{channel_id}:{message_id}"

    message_link = _safe_str(payload.get("message_link"))
    if message_link:
        return message_link

    cid = _safe_str(payload.get("cid"))
    if cid:
        return cid

    return f"unknown:{int(datetime.now(timezone.utc).timestamp())}"


def _build_assignment_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    parsed = payload.get("parsed") or {}
    agency_name, agency_link = _derive_agency(payload)

    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    signals_meta = meta.get("signals") if isinstance(meta.get("signals"), dict) else None
    signals_obj: Optional[Dict[str, Any]] = None
    if signals_meta and signals_meta.get("ok") is True and isinstance(signals_meta.get("signals"), dict):
        signals_obj = signals_meta.get("signals")

    # Fallback: if signals were not computed upstream, compute them here (best-effort).
    if signals_obj is None:
        try:
            try:
                from signals_builder import build_signals  # type: ignore
                from normalize import normalize_text  # type: ignore
            except Exception:
                from TutorDexAggregator.signals_builder import build_signals  # type: ignore
                from TutorDexAggregator.normalize import normalize_text  # type: ignore

            raw_text = str(payload.get("raw_text") or "")
            normalized_text = normalize_text(raw_text) if raw_text else ""
            sig, err = build_signals(parsed=parsed, raw_text=raw_text, normalized_text=normalized_text)
            if not err and isinstance(sig, dict):
                signals_obj = sig
        except Exception:
            signals_obj = None

    def _opt_list(value: Any) -> Optional[List[str]]:
        vals = _coerce_text_list(value)
        return vals or None

    def _coerce_dict(value: Any) -> Optional[Dict[str, Any]]:
        return value if isinstance(value, dict) else None

    # v2 display fields
    assignment_code = _safe_str(parsed.get("assignment_code")) if isinstance(parsed, dict) else None
    academic_display_text = _safe_str(parsed.get("academic_display_text")) if isinstance(parsed, dict) else None

    lm_mode = None
    lm_raw = None
    lm = parsed.get("learning_mode") if isinstance(parsed, dict) else None
    if isinstance(lm, dict):
        lm_mode = _safe_str(lm.get("mode"))
        lm_raw = _safe_str(lm.get("raw_text"))
    else:
        lm_mode = _safe_str(lm)

    address = _opt_list(parsed.get("address") if isinstance(parsed, dict) else None)
    postal_codes = _coerce_text_list(parsed.get("postal_code") if isinstance(parsed, dict) else None)
    postal_code = postal_codes[0] if postal_codes else None
    postal_code_list = _opt_list(postal_codes)
    postal_code_estimated = _opt_list(parsed.get("postal_code_estimated") if isinstance(parsed, dict) else None)
    nearest_mrt = _opt_list(parsed.get("nearest_mrt") if isinstance(parsed, dict) else None)
    lesson_schedule = _opt_list(parsed.get("lesson_schedule") if isinstance(parsed, dict) else None)
    start_date = _safe_str(parsed.get("start_date")) if isinstance(parsed, dict) else None

    ta = parsed.get("time_availability") if isinstance(parsed, dict) else None
    if not isinstance(ta, dict):
        ta = {}
    ta_note = _safe_str(ta.get("note"))
    ta_explicit = _coerce_dict(ta.get("explicit"))
    ta_estimated = _coerce_dict(ta.get("estimated"))

    rate = parsed.get("rate") if isinstance(parsed, dict) else None
    if not isinstance(rate, dict):
        rate = {}
    rate_min = _coerce_int_like(rate.get("min"))
    rate_max = _coerce_int_like(rate.get("max"))
    rate_raw_text = _safe_str(rate.get("raw_text"))
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

    # Sanitize tutor_types: ensure list of dicts with canonical, original, agency, confidence(float)
    def _sanitize_tutor_types(tt: Any):
        if not tt:
            return None
        if not isinstance(tt, (list, tuple)):
            return None
        out = []
        for item in tt:
            if not isinstance(item, dict):
                continue
            canonical = _safe_str(item.get("canonical") or item.get("canonical_name") or item.get("canonical"))
            original = _safe_str(item.get("original") or item.get("label") or item.get("raw"))
            agency = _safe_str(item.get("agency"))
            conf = None
            try:
                if item.get("confidence") is not None:
                    conf = float(item.get("confidence"))
            except Exception:
                conf = None
            out.append({
                "canonical": canonical or (None if canonical == "" else None),
                "original": original,
                "agency": agency,
                "confidence": conf,
            })
        return out or None

    def _sanitize_rate_breakdown(rb: Any):
        if not rb:
            return None
        if not isinstance(rb, dict):
            return None
        out = {}
        for k, v in rb.items():
            if not isinstance(v, dict):
                continue
            try:
                min_v = _coerce_int_like(v.get("min"))
            except Exception:
                min_v = None
            try:
                max_v = _coerce_int_like(v.get("max"))
            except Exception:
                max_v = None
            currency = _safe_str(v.get("currency"))
            unit = _safe_str(v.get("unit"))
            original_text = _safe_str(v.get("original_text") or v.get("raw_text"))
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

    tutor_types = _sanitize_tutor_types(tutor_types)
    rate_breakdown = _sanitize_rate_breakdown(rate_breakdown)

    additional_remarks = _safe_str(parsed.get("additional_remarks")) if isinstance(parsed, dict) else None

    # Deterministic signals rollups (optional, but default enabled).
    signals_subjects = _coerce_text_list(signals_obj.get("subjects") if isinstance(signals_obj, dict) else None)
    signals_levels = _coerce_text_list(signals_obj.get("levels") if isinstance(signals_obj, dict) else None)
    signals_specific = _coerce_text_list(signals_obj.get("specific_student_levels") if isinstance(signals_obj, dict) else None)
    signals_streams = _coerce_text_list(signals_obj.get("streams") if isinstance(signals_obj, dict) else None)
    signals_academic_requests = signals_obj.get("academic_requests") if isinstance(signals_obj, dict) else None
    signals_confidence_flags = signals_obj.get("confidence_flags") if isinstance(signals_obj, dict) else None

    # v2 subject taxonomy (stable codes) used for filtering/matching across the system.
    subjects_canonical = _coerce_text_list(signals_obj.get("subjects_canonical") if isinstance(signals_obj, dict) else None)
    subjects_general = _coerce_text_list(signals_obj.get("subjects_general") if isinstance(signals_obj, dict) else None)
    canonicalization_version = None
    canonicalization_debug = None
    if isinstance(signals_obj, dict):
        canonicalization_version = signals_obj.get("canonicalization_version")
        canonicalization_debug = signals_obj.get("canonicalization_debug")

    # TutorCity API: prefer the explicit API mappings (level label + subject labels).
    if str(payload.get("source_type") or "").strip().lower() == "tutorcity_api":
        try:
            src_mapped = meta.get("source_mapped") if isinstance(meta.get("source_mapped"), dict) else {}
            lvl = _safe_str(src_mapped.get("level"))
            subs = src_mapped.get("subjects") if isinstance(src_mapped, dict) else None
            if subs is not None:
                try:
                    from taxonomy.canonicalize_subjects import canonicalize_subjects  # type: ignore
                except Exception:
                    from TutorDexAggregator.taxonomy.canonicalize_subjects import canonicalize_subjects  # type: ignore

                res = canonicalize_subjects(level=lvl, subjects=subs)
                subjects_canonical = _coerce_text_list(res.get("subjects_canonical"))
                subjects_general = _coerce_text_list(res.get("subjects_general"))
                canonicalization_version = res.get("canonicalization_version")
                canonicalization_debug = res.get("debug")
        except Exception:
            pass

    postal_lat = None
    postal_lon = None
    postal_coords_estimated = False

    # First, try explicit postal code
    if postal_code:
        coords = _geocode_sg_postal(postal_code)
        if coords:
            postal_lat, postal_lon = coords

    # If no explicit postal code or geocoding failed, try estimated postal code
    if postal_lat is None and postal_lon is None and postal_code_estimated:
        # Try the first estimated postal code
        estimated_codes = _coerce_text_list(postal_code_estimated)
        if estimated_codes:
            first_estimated = estimated_codes[0]
            coords = _geocode_sg_postal(first_estimated)
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
        from TutorDexAggregator.extractors.status_detector import detect_status, detection_meta  # type: ignore
    except Exception:
        try:
            from extractors.status_detector import detect_status, detection_meta  # type: ignore
        except Exception:
            detect_status = None  # type: ignore
            detection_meta = None  # type: ignore

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
                meta["status_detection"] = detection_meta(det)  # type: ignore[arg-type]

    row: Dict[str, Any] = {
        "external_id": _derive_external_id(payload),
        "agency_id": None,
        "agency_name": agency_name,
        "agency_link": agency_link,
        # Source publish time (Telegram message date, or first-seen for API sources).
        "published_at": _coerce_iso_ts(payload.get("date")),
        # Last upstream bump/edit/repost time (Telegram edit_date or similar).
        "source_last_seen": _coerce_iso_ts(payload.get("source_last_seen") or payload.get("date")),
        "channel_id": payload.get("channel_id"),
        "message_id": payload.get("message_id"),
        "message_link": _safe_str(payload.get("message_link")),
        "raw_text": _safe_str(payload.get("raw_text")),
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
        "canonicalization_debug": canonicalization_debug if _truthy(os.environ.get("SUBJECT_TAXONOMY_DEBUG")) and isinstance(canonicalization_debug, dict) else None,
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

    row["parse_quality_score"] = _compute_parse_quality(row)
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


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str
    assignments_table: str = "assignments"
    enabled: bool = False
    bump_min_seconds: int = 6 * 60 * 60  # 6 hours


def load_config_from_env() -> SupabaseConfig:
    url = resolve_supabase_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    assignments_table = (os.environ.get("SUPABASE_ASSIGNMENTS_TABLE") or "assignments").strip()
    enabled = _truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key and assignments_table)
    bump_min_seconds = int(os.environ.get("SUPABASE_BUMP_MIN_SECONDS") or str(6 * 60 * 60))
    return SupabaseConfig(
        url=url,
        key=key,
        assignments_table=assignments_table,
        enabled=enabled,
        bump_min_seconds=bump_min_seconds,
    )


class SupabaseRestClient:
    def __init__(self, cfg: SupabaseConfig):
        self.cfg = cfg
        self.base = f"{cfg.url}/rest/v1"
        self.session = requests.Session()
        try:
            host = (urlparse(cfg.url).hostname or "").lower()
            if host in {"127.0.0.1", "localhost", "::1"}:
                self.session.trust_env = False
        except Exception:
            pass
        self.session.headers.update(
            {
                "apikey": cfg.key,
                "authorization": f"Bearer {cfg.key}",
                "content-type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def get(self, path: str, *, timeout: int = 15) -> requests.Response:
        return self.session.get(self._url(path), timeout=timeout)

    def post(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.post(self._url(path), json=json_body, headers=headers, timeout=timeout)

    def patch(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.patch(self._url(path), json=json_body, headers=headers, timeout=timeout)


def _upsert_agency(client: SupabaseRestClient, *, name: str, channel_link: Optional[str]) -> Optional[int]:
    if not name:
        return None

    # Try lookup by channel_link first (if present), else by name.
    if channel_link:
        q = f"agencies?select=id&channel_link=eq.{requests.utils.quote(channel_link, safe='')}&limit=1"
        try:
            r = client.get(q, timeout=15)
            if r.status_code < 400:
                rows = _coerce_rows(r)
                if rows:
                    return rows[0].get("id")
        except Exception:
            logger.debug("Agency lookup by channel_link failed", exc_info=True)

    q2 = f"agencies?select=id&name=eq.{requests.utils.quote(name, safe='')}&limit=1"
    try:
        r2 = client.get(q2, timeout=15)
        if r2.status_code < 400:
            rows = _coerce_rows(r2)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency lookup by name failed", exc_info=True)

    try:
        ins = client.post(
            "agencies",
            [{"name": name, "channel_link": channel_link}],
            timeout=20,
            prefer="return=representation",
        )
        if ins.status_code < 400:
            rows = _coerce_rows(ins)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency insert failed", exc_info=True)
        return None
    return None


def _coerce_rows(resp: requests.Response) -> List[Dict[str, Any]]:
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []


def persist_assignment_to_supabase(payload: Dict[str, Any], *, cfg: Optional[SupabaseConfig] = None) -> Dict[str, Any]:
    cfg = cfg or load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel = payload.get("channel_link") or payload.get("channel_username")

    pv = str(payload.get("pipeline_version") or "").strip()
    sv = str(payload.get("schema_version") or "").strip()
    if _obs_versions and not pv:
        pv = _obs_versions().pipeline_version
    if _obs_versions and not sv:
        sv = _obs_versions().schema_version
    pv = pv or "-"
    sv = sv or "-"

    row = _build_assignment_row(payload)
    external_id = row.get("external_id")
    agency_name = row.get("agency_name")
    agency_link = row.get("agency_link")

    with bind_log_context(
        cid=str(cid),
        message_id=msg_id,
        channel=str(channel) if channel else None,
        assignment_id=str(external_id) if external_id else None,
        step="supabase",
        component="supabase",
        pipeline_version=pv,
        schema_version=sv,
    ):
        t_all = timed()

        client = SupabaseRestClient(cfg)
        if not external_id or not agency_name:
            res = {
                "ok": False,
                "skipped": True,
                "reason": "missing_external_id_or_agency_name",
                "external_id": external_id,
                "agency_name": agency_name,
            }
            log_event(logger, logging.WARNING, "supabase_skipped", **res)
            return res

        # If the normalized schema exists, try to create/resolve agency_id.
        try:
            t0 = timed()
            agency_id = _upsert_agency(client, name=str(agency_name), channel_link=str(agency_link) if agency_link else None)
            agency_ms = round((timed() - t0) * 1000.0, 2)
            if agency_id:
                row["agency_id"] = agency_id
                log_event(logger, logging.DEBUG, "supabase_agency_resolved", agency_id=agency_id, agency_ms=agency_ms)
            else:
                log_event(logger, logging.DEBUG, "supabase_agency_unresolved", agency_ms=agency_ms)
        except Exception:
            logger.debug("Agency upsert failed (continuing without agency_id)", exc_info=True)

        now_iso = _utc_now_iso()

        select = ",".join(
            [
                "id",
                "agency_id",
                "external_id",
                "published_at",
                "source_last_seen",
                "last_seen",
                "bump_count",
                "parse_quality_score",
                "message_id",
                "message_link",
                "address",
                "postal_code",
                "nearest_mrt",
                "learning_mode",
                "learning_mode_raw_text",
                "assignment_code",
                "academic_display_text",
                "lesson_schedule",
                "start_date",
                "time_availability_note",
                "time_availability_explicit",
                "time_availability_estimated",
                "rate_min",
                "rate_max",
                "rate_raw_text",
                "tutor_types",
                "rate_breakdown",
                "additional_remarks",
                "signals_subjects",
                "signals_levels",
                "signals_specific_student_levels",
                "signals_streams",
                "signals_academic_requests",
                "signals_confidence_flags",
                "canonical_json",
                "meta",
                "status",
            ]
        )
        query = f"{cfg.assignments_table}?select={select}&external_id=eq.{requests.utils.quote(str(external_id), safe='')}"
        if row.get("agency_id") is not None:
            query += f"&agency_id=eq.{int(row['agency_id'])}"
        else:
            query += f"&agency_name=eq.{requests.utils.quote(str(agency_name), safe='')}"
        query += "&limit=1"

        try:
            t0 = timed()
            existing_resp = client.get(query, timeout=15)
            get_ms = round((timed() - t0) * 1000.0, 2)
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "supabase_get_failed",
                external_id=str(external_id),
                agency_name=str(agency_name),
                error=str(e),
            )
            if worker_supabase_fail_total:
                try:
                    worker_supabase_fail_total.labels(operation="get", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
            return {"ok": False, "error": str(e)}

        existing_rows = _coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
        if existing_rows:
            existing = existing_rows[0]
            last_seen = _parse_iso_dt(existing.get("last_seen"))
            bump_count = int(existing.get("bump_count") or 0)
            existing_source_last_seen = _safe_str(existing.get("source_last_seen"))
            source_type = str(payload.get("source_type") or "").strip().lower()
            tutorcity_changed = False
            if source_type == "tutorcity_api":
                try:
                    prev_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else None
                    prev_fp = _safe_str(prev_meta.get("tutorcity_fingerprint")) if isinstance(prev_meta, dict) else None
                    incoming_meta = row.get("meta") if isinstance(row.get("meta"), dict) else None
                    incoming_fp = _safe_str(incoming_meta.get("tutorcity_fingerprint")) if isinstance(incoming_meta, dict) else None
                    tutorcity_changed = bool(incoming_fp and incoming_fp != prev_fp)
                except Exception:
                    tutorcity_changed = False

            should_bump = True
            if last_seen:
                elapsed = (datetime.now(timezone.utc) - last_seen.astimezone(timezone.utc)).total_seconds()
                should_bump = elapsed >= cfg.bump_min_seconds
                if not should_bump:
                    log_event(
                        logger,
                        logging.DEBUG,
                        "supabase_bump_suppressed",
                        external_id=str(external_id),
                        agency=str(agency_name),
                        last_seen=existing.get("last_seen"),
                        elapsed_s=round(elapsed, 2),
                        min_seconds=cfg.bump_min_seconds,
                    )

            patch_body: Dict[str, Any] = {"last_seen": now_iso}
            if should_bump:
                patch_body["bump_count"] = bump_count + 1

            patch_body.update(_merge_patch_body(existing=existing, incoming_row=row, force_upgrade=bool(tutorcity_changed)))

            # `source_last_seen` = last upstream bump/edit/repost.
            # - For Telegram: keep monotonic based on upstream timestamp (edit_date).
            # - For TutorCity API: only update when the upstream payload fingerprint changed (true update),
            #   so polling doesn't continuously bump freshness.
            incoming_source_last_seen = _safe_str(row.get("source_last_seen"))
            if source_type == "tutorcity_api":
                if tutorcity_changed:
                    patch_body["source_last_seen"] = now_iso
                else:
                    patch_body["source_last_seen"] = existing_source_last_seen
            else:
                patch_body["source_last_seen"] = _max_iso_ts(existing_source_last_seen, incoming_source_last_seen) or existing_source_last_seen
            if patch_body.get("source_last_seen") is None:
                patch_body.pop("source_last_seen", None)

            try:
                t0 = timed()
                patch_resp = client.patch(
                    f"{cfg.assignments_table}?id=eq.{existing.get('id')}",
                    patch_body,
                    timeout=20,
                    prefer="return=representation",
                )
                patch_ms = round((timed() - t0) * 1000.0, 2)
            except Exception as e:
                log_event(logger, logging.ERROR, "supabase_patch_failed", row_id=existing.get("id"), error=str(e))
                if worker_supabase_fail_total:
                    try:
                        worker_supabase_fail_total.labels(operation="patch", pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                return {"ok": False, "error": str(e)}

            ok = patch_resp.status_code < 400
            if not ok and patch_resp.status_code == 400 and ("PGRST204" in patch_resp.text or "schema cache" in patch_resp.text):
                patch_body.pop("postal_lat", None)
                patch_body.pop("postal_lon", None)
                patch_body.pop("subjects_canonical", None)
                patch_body.pop("subjects_general", None)
                patch_body.pop("canonicalization_version", None)
                patch_body.pop("canonicalization_debug", None)
                patch_body.pop("published_at", None)
                patch_body.pop("source_last_seen", None)
                try:
                    t0 = timed()
                    patch_resp = client.patch(
                        f"{cfg.assignments_table}?id=eq.{existing.get('id')}",
                        patch_body,
                        timeout=20,
                        prefer="return=representation",
                    )
                    patch_ms = round((timed() - t0) * 1000.0, 2)
                    ok = patch_resp.status_code < 400
                except Exception as e:
                    log_event(logger, logging.ERROR, "supabase_patch_failed", row_id=existing.get("id"), error=str(e))
                    if worker_supabase_fail_total:
                        try:
                            worker_supabase_fail_total.labels(operation="patch", pipeline_version=pv, schema_version=sv).inc()
                        except Exception:
                            pass
                    return {"ok": False, "error": str(e)}
            if not ok:
                log_event(logger, logging.WARNING, "supabase_patch_status", status_code=patch_resp.status_code, body=patch_resp.text[:500])
            res = {"ok": ok, "action": "updated", "status_code": patch_resp.status_code, "get_ms": get_ms, "patch_ms": patch_ms}
            res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
            log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)
            return res

        row_to_insert = dict(row)
        row_to_insert["last_seen"] = now_iso
        row_to_insert.setdefault("published_at", now_iso)
        row_to_insert.setdefault("source_last_seen", row_to_insert.get("published_at") or now_iso)
        row_to_insert.setdefault("bump_count", 0)
        row_to_insert.setdefault("status", "open")

        try:
            t0 = timed()
            insert_resp = client.post(
                cfg.assignments_table,
                [row_to_insert],
                timeout=20,
                prefer="return=representation",
            )
            insert_ms = round((timed() - t0) * 1000.0, 2)
        except Exception as e:
            log_event(logger, logging.ERROR, "supabase_insert_failed", external_id=str(external_id), agency_name=str(agency_name), error=str(e))
            if worker_supabase_fail_total:
                try:
                    worker_supabase_fail_total.labels(operation="insert", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
            return {"ok": False, "error": str(e)}

        ok = insert_resp.status_code < 400
        if not ok and insert_resp.status_code == 400 and ("PGRST204" in insert_resp.text or "schema cache" in insert_resp.text):
            row_to_insert.pop("postal_lat", None)
            row_to_insert.pop("postal_lon", None)
            row_to_insert.pop("subjects_canonical", None)
            row_to_insert.pop("subjects_general", None)
            row_to_insert.pop("canonicalization_version", None)
            row_to_insert.pop("canonicalization_debug", None)
            row_to_insert.pop("published_at", None)
            row_to_insert.pop("source_last_seen", None)
            try:
                t0 = timed()
                insert_resp = client.post(
                    cfg.assignments_table,
                    [row_to_insert],
                    timeout=20,
                    prefer="return=representation",
                )
                insert_ms = round((timed() - t0) * 1000.0, 2)
                ok = insert_resp.status_code < 400
            except Exception as e:
                log_event(logger, logging.ERROR, "supabase_insert_failed", external_id=str(external_id), agency_name=str(agency_name), error=str(e))
                if worker_supabase_fail_total:
                    try:
                        worker_supabase_fail_total.labels(operation="insert", pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                return {"ok": False, "error": str(e)}
        if not ok:
            log_event(logger, logging.WARNING, "supabase_insert_status", status_code=insert_resp.status_code, body=insert_resp.text[:500])
        res = {"ok": ok, "action": "inserted", "status_code": insert_resp.status_code, "get_ms": get_ms, "insert_ms": insert_ms}
        res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)
        return res


def mark_assignment_closed(payload: Dict[str, Any], *, cfg: Optional[SupabaseConfig] = None) -> Dict[str, Any]:
    """
    Best-effort close of an assignment when we observe a Telegram delete.
    Uses the same external_id derivation as normal persistence to avoid schema drift.
    """
    cfg = cfg or load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel = payload.get("channel_link") or payload.get("channel_username")

    with bind_log_context(cid=str(cid), message_id=msg_id, channel=str(channel) if channel else None, step="supabase.close"):
        client = SupabaseRestClient(cfg)
        row = _build_assignment_row(payload)
        external_id = row.get("external_id")
        agency_name = row.get("agency_name")
        agency_link = row.get("agency_link")
        if not external_id or not agency_name:
            res = {
                "ok": False,
                "skipped": True,
                "reason": "missing_external_id_or_agency_name",
                "external_id": external_id,
                "agency_name": agency_name,
            }
            log_event(logger, logging.DEBUG, "supabase_close_skipped", **res)
            return res

        query = f"{cfg.assignments_table}?select=id,status,last_seen&external_id=eq.{requests.utils.quote(str(external_id), safe='')}"
        if row.get("agency_id") is not None:
            query += f"&agency_id=eq.{int(row['agency_id'])}"
        else:
            query += f"&agency_name=eq.{requests.utils.quote(str(agency_name), safe='')}"
        query += "&limit=1"

        try:
            existing_resp = client.get(query, timeout=10)
            existing_rows = _coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
        except Exception as e:
            log_event(logger, logging.WARNING, "supabase_close_lookup_failed", error=str(e))
            return {"ok": False, "error": str(e), "action": "lookup_failed"}

        if not existing_rows:
            log_event(logger, logging.INFO, "supabase_close_not_found", external_id=external_id, agency_name=agency_name)
            return {"ok": False, "skipped": True, "reason": "not_found"}

        row_id = existing_rows[0].get("id")
        patch_body = {"status": "closed", "last_seen": _utc_now_iso()}

        try:
            patch_resp = client.patch(f"{cfg.assignments_table}?id=eq.{row_id}", patch_body, timeout=10, prefer="return=representation")
            ok = patch_resp.status_code < 400
        except Exception as e:
            log_event(logger, logging.WARNING, "supabase_close_failed", row_id=row_id, error=str(e))
            return {"ok": False, "error": str(e), "action": "close_failed"}

        res = {"ok": ok, "action": "closed" if ok else "close_failed", "status_code": patch_resp.status_code if 'patch_resp' in locals() else None}
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_close_result", **res)
        return res
