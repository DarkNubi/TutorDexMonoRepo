import os
import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from logging_setup import bind_log_context, log_event, setup_logging, timed
from observability_metrics import dm_fail_reason_total, dm_fail_total, dm_rate_limited_total, dm_sent_total, versions as _obs_versions

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"
if load_dotenv and ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

setup_logging()
logger = logging.getLogger("dm_assignments")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


DM_BOT_TOKEN = (os.environ.get("DM_BOT_TOKEN") or "").strip()
DM_BOT_API_URL = (os.environ.get("DM_BOT_API_URL") or "").strip()
TUTOR_MATCH_URL = (os.environ.get("TUTOR_MATCH_URL") or "http://127.0.0.1:8000/match/payload").strip()
BACKEND_API_KEY = (os.environ.get("BACKEND_API_KEY") or "").strip()

DM_ENABLED = _truthy(os.environ.get("DM_ENABLED")) and bool(DM_BOT_TOKEN and TUTOR_MATCH_URL)
DM_MAX_RECIPIENTS = int(os.environ.get("DM_MAX_RECIPIENTS") or "50")
DM_FALLBACK_FILE = os.environ.get("DM_FALLBACK_FILE") or str(HERE / "outgoing_dm.jsonl")

# Adaptive threshold settings
DM_USE_ADAPTIVE_THRESHOLD = _truthy(os.environ.get("DM_USE_ADAPTIVE_THRESHOLD", "true"))
DM_RATING_LOOKBACK_DAYS = int(os.environ.get("DM_RATING_LOOKBACK_DAYS") or "7")
DM_RATING_AVG_RATE_LOOKBACK_DAYS = int(os.environ.get("DM_RATING_AVG_RATE_LOOKBACK_DAYS") or "30")


if not DM_BOT_API_URL and DM_BOT_TOKEN:
    DM_BOT_API_URL = f"https://api.telegram.org/bot{DM_BOT_TOKEN}/sendMessage"


def _calculate_match_ratings(
    matches: List[Dict[str, Any]],
    payload: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Calculate assignment rating for each match.
    
    Returns matches enriched with 'rating' field based on:
    - Base matching score
    - Distance to assignment  
    - Assignment rate vs tutor's historical average
    
    Requires backend with rating calculation support.
    """
    try:
        from TutorDexBackend.assignment_rating import calculate_assignment_rating
        from TutorDexBackend.supabase_store import SupabaseStore
    except Exception:
        # If imports fail, return matches unchanged (backward compatibility)
        logger.debug("Rating calculation not available, using base scores only")
        return matches
    
    # Get assignment rates from payload
    parsed = payload.get("parsed") or {}
    assignment_rate_min = _safe_int(parsed.get("rate_min"))
    assignment_rate_max = _safe_int(parsed.get("rate_max"))
    
    # Get supabase connection for historical rate lookups
    sb = None
    try:
        sb = SupabaseStore()
        if not sb.enabled():
            sb = None
    except Exception:
        sb = None
    
    enriched_matches = []
    for match in matches:
        # Get tutor's average rate from history if available
        tutor_avg_rate = None
        tutor_id = match.get("tutor_id")
        if sb and tutor_id:
            try:
                from TutorDexBackend.supabase_store import SupabaseStore
                # Get user_id from firebase_uid
                user_id = sb.upsert_user(firebase_uid=str(tutor_id), email=None, name=None)
                if user_id:
                    tutor_avg_rate = sb.get_tutor_avg_rate(
                        user_id=user_id,
                        lookback_days=DM_RATING_AVG_RATE_LOOKBACK_DAYS
                    )
            except Exception as e:
                logger.debug(f"Could not get tutor avg rate for {tutor_id}: {e}")
        
        # Calculate rating
        rating = calculate_assignment_rating(
            base_score=match.get("score", 0),
            distance_km=match.get("distance_km"),
            assignment_rate_min=assignment_rate_min,
            assignment_rate_max=assignment_rate_max,
            tutor_avg_rate=tutor_avg_rate,
        )
        
        # Add rating to match
        match_with_rating = dict(match)
        match_with_rating["rating"] = rating
        match_with_rating["tutor_avg_rate"] = tutor_avg_rate
        enriched_matches.append(match_with_rating)
    
    return enriched_matches


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except Exception:
        return None


def _filter_by_adaptive_threshold(
    matches: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Filter matches by adaptive threshold per tutor.
    
    For each tutor, looks up their:
    - desired_assignments_per_day preference
    - historical assignment rating threshold
    
    Only sends assignments above the tutor's personal threshold.
    """
    if not DM_USE_ADAPTIVE_THRESHOLD:
        # Disabled - return all matches
        return matches
    
    try:
        from TutorDexBackend.supabase_store import SupabaseStore
        from TutorDexBackend.redis_store import TutorStore
    except Exception:
        logger.debug("Adaptive threshold not available, using all matches")
        return matches
    
    sb = None
    redis_store = None
    try:
        sb = SupabaseStore()
        if not sb.enabled():
            sb = None
        redis_store = TutorStore()
    except Exception:
        logger.debug("Could not initialize stores for adaptive threshold")
        return matches
    
    filtered = []
    for match in matches:
        tutor_id = match.get("tutor_id")
        rating = match.get("rating")
        
        if not tutor_id or rating is None:
            # No tutor ID or rating - include match (backward compat)
            filtered.append(match)
            continue
        
        # Get tutor's desired assignments per day
        desired_per_day = 10  # default
        try:
            if redis_store:
                tutor = redis_store.get_tutor(str(tutor_id))
                if tutor:
                    desired_per_day = tutor.get("desired_assignments_per_day", 10)
        except Exception as e:
            logger.debug(f"Could not get tutor preferences for {tutor_id}: {e}")
        
        # Get adaptive threshold from database
        threshold = None
        if sb:
            try:
                user_id = sb.upsert_user(firebase_uid=str(tutor_id), email=None, name=None)
                if user_id:
                    threshold = sb.get_tutor_rating_threshold(
                        user_id=user_id,
                        desired_per_day=desired_per_day,
                        lookback_days=DM_RATING_LOOKBACK_DAYS,
                    )
            except Exception as e:
                logger.debug(f"Could not get threshold for {tutor_id}: {e}")
        
        # If no threshold available (new tutor or no history), include the match
        if threshold is None:
            filtered.append(match)
            logger.debug(f"Including {tutor_id} - no threshold available (new tutor)")
            continue
        
        # Filter by threshold
        if rating >= threshold:
            filtered.append(match)
            logger.debug(f"Including {tutor_id} - rating {rating:.2f} >= threshold {threshold:.2f}")
        else:
            logger.debug(f"Filtering out {tutor_id} - rating {rating:.2f} < threshold {threshold:.2f}")
    
    return filtered


def _coerce_chat_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(_coerce_chat_ids(x))
        return out
    s = str(value).strip()
    return [s] if s else []


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _learning_mode_is_online_only(payload: Dict[str, Any]) -> bool:
    parsed = payload.get("parsed") or {}
    lm_val = parsed.get("learning_mode")
    if isinstance(lm_val, dict):
        lm = str(lm_val.get("mode") or lm_val.get("raw_text") or "").strip().lower()
    else:
        lm = str(lm_val or "").strip().lower()
    return lm == "online"


def _get_or_geocode_assignment_coords(payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Get or geocode assignment coordinates.
    Returns (lat, lon, is_estimated) tuple.
    is_estimated is True when coordinates came from postal_code_estimated.
    """
    parsed = payload.get("parsed") or {}
    if not isinstance(parsed, dict):
        return None, None, False

    lat = _safe_float(parsed.get("postal_lat"))
    lon = _safe_float(parsed.get("postal_lon"))
    coords_estimated = parsed.get("postal_coords_estimated", False)
    if lat is not None and lon is not None:
        return lat, lon, bool(coords_estimated)

    if _learning_mode_is_online_only(payload):
        return None, None, False

    try:
        from supabase_persist import _geocode_sg_postal  # best-effort + cached
    except Exception:
        _geocode_sg_postal = None

    if not _geocode_sg_postal:
        return None, None, False

    # Try explicit postal code first
    postal_code = parsed.get("postal_code")
    if isinstance(postal_code, list) and postal_code:
        postal_code = postal_code[0]
    
    if postal_code:
        coords = _geocode_sg_postal(str(postal_code))
        if coords:
            lat, lon = coords
            parsed["postal_lat"] = float(lat)
            parsed["postal_lon"] = float(lon)
            parsed["postal_coords_estimated"] = False
            payload["parsed"] = parsed
            return float(lat), float(lon), False
    
    # If explicit failed, try estimated postal code
    postal_code_estimated = parsed.get("postal_code_estimated")
    if isinstance(postal_code_estimated, list) and postal_code_estimated:
        postal_code_estimated = postal_code_estimated[0]
    
    if postal_code_estimated:
        coords = _geocode_sg_postal(str(postal_code_estimated))
        if coords:
            lat, lon = coords
            parsed["postal_lat"] = float(lat)
            parsed["postal_lon"] = float(lon)
            parsed["postal_coords_estimated"] = True
            payload["parsed"] = parsed
            return float(lat), float(lon), True

    return None, None, False


def fetch_matching_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fetch matching tutors from the backend.
    
    Returns list of matches with:
    - chat_id: Telegram chat ID
    - tutor_id: User ID for database operations
    - distance_km: Distance to assignment
    - score: Base matching score
    - rating: Overall assignment rating (optional, may be None)
    - rate_min, rate_max: Assignment rates
    """
    headers = {"x-api-key": BACKEND_API_KEY} if BACKEND_API_KEY else None
    t0 = timed()
    resp = requests.post(TUTOR_MATCH_URL, json={"payload": payload}, headers=headers, timeout=10)
    match_ms = round((timed() - t0) * 1000.0, 2)
    if resp.status_code >= 400:
        raise RuntimeError(f"match_api_error status={resp.status_code} body={resp.text[:300]}")
    data = resp.json()
    matches = data.get("matches")
    if isinstance(matches, list) and matches:
        out: List[Dict[str, Any]] = []
        for m in matches:
            if not isinstance(m, dict):
                continue
            chat_id = str(m.get("chat_id") or "").strip()
            if not chat_id:
                continue
            out.append({
                "chat_id": chat_id,
                "tutor_id": m.get("tutor_id"),
                "distance_km": m.get("distance_km"),
                "score": m.get("score"),
                "rating": m.get("rating"),
                "rate_min": m.get("rate_min"),
                "rate_max": m.get("rate_max"),
            })
        log_event(logger, logging.DEBUG, "dm_match_ok", matched=len(out), match_ms=match_ms)
        return out

    # Backward compatibility: old format with just chat_ids
    chat_ids = _coerce_chat_ids(data.get("chat_ids"))
    out = [{"chat_id": cid, "distance_km": None, "tutor_id": None, "score": 0, "rating": None, "rate_min": None, "rate_max": None} for cid in chat_ids]
    log_event(logger, logging.DEBUG, "dm_match_ok", matched=len(out), match_ms=match_ms)
    return out


def _telegram_send_message(chat_id: str, text: str, reply_markup: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": False,
    }
    if reply_markup:
        body["reply_markup"] = reply_markup
    resp = requests.post(DM_BOT_API_URL, json=body, timeout=15)
    try:
        data = resp.json()
    except Exception:
        data = {"status_code": resp.status_code, "text": resp.text}
    return {"status_code": resp.status_code, "data": data}


def _classify_dm_error(*, status_code: Optional[int], error: Optional[str]) -> str:
    msg = str(error or "").lower()
    if status_code == 429 or "too many requests" in msg or "retry_after" in msg:
        return "rate_limited"
    if status_code is not None and status_code >= 500:
        return "telegram_5xx"
    if status_code is not None and status_code >= 400:
        return "telegram_4xx"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "connection" in msg or "connection refused" in msg:
        return "connection"
    if "match_api_error" in msg:
        return "match_api_error"
    return "error"


def _should_send_dm_for_assignment(payload: Dict[str, Any]) -> bool:
    """
    Check if DM should be sent for this assignment.
    Returns False if assignment is non-primary duplicate.
    
    Environment variable DM_FILTER_DUPLICATES (default: true) controls this behavior.
    """
    # Check if DM duplicate filtering is enabled
    filter_enabled = _truthy(os.environ.get("DM_FILTER_DUPLICATES", "true"))
    if not filter_enabled:
        return True
    
    # Get duplicate metadata from parsed data
    parsed = payload.get("parsed") or {}
    is_primary = parsed.get("is_primary_in_group", True)
    
    # If assignment is non-primary, skip DM
    if not is_primary:
        duplicate_group_id = parsed.get("duplicate_group_id")
        logger.info(
            f"Skipping DM for non-primary duplicate assignment",
            extra={
                "assignment_id": parsed.get("id"),
                "duplicate_group_id": duplicate_group_id,
                "reason": "non_primary_duplicate"
            }
        )
        try:
            from observability_metrics import dm_skipped_duplicate_total
            dm_skipped_duplicate_total.inc()
        except Exception:
            pass
        return False
    
    return True


def send_dms(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not DM_ENABLED:
        log_event(logger, logging.DEBUG, "dm_skipped", reason="dm_disabled")
        return {"ok": False, "skipped": True, "reason": "dm_disabled"}
    
    # Check if we should skip this assignment due to duplicate filtering
    if not _should_send_dm_for_assignment(payload):
        log_event(logger, logging.INFO, "dm_skipped", reason="non_primary_duplicate")
        return {"ok": True, "skipped": True, "reason": "non_primary_duplicate", "matched": 0, "sent": 0}

    try:
        from broadcast_assignments import build_inline_keyboard, build_message_text
    except Exception as e:
        return {"ok": False, "error": f"missing_broadcast_assignments_build_message_text: {e}"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel_link = payload.get("channel_link") or payload.get("channel_username")

    v = _obs_versions()
    pv = str(payload.get("pipeline_version") or "").strip() or v.pipeline_version
    sv = str(payload.get("schema_version") or "").strip() or v.schema_version
    parsed = payload.get("parsed") or {}
    assignment_id = "-"
    try:
        assignment_code = parsed.get("assignment_code")
        if isinstance(assignment_code, list) and assignment_code:
            assignment_id = str(assignment_code[0]).strip() or "-"
        elif isinstance(assignment_code, str) and assignment_code.strip():
            assignment_id = assignment_code.strip()
    except Exception:
        assignment_id = "-"

    with bind_log_context(
        cid=cid,
        message_id=msg_id,
        channel=str(channel_link) if channel_link else None,
        assignment_id=assignment_id,
        step="dm",
        component="dm",
        pipeline_version=pv,
        schema_version=sv,
    ):
        _get_or_geocode_assignment_coords(payload)

        try:
            matches = fetch_matching_results(payload)
        except Exception as e:
            logger.warning("DM match failed error=%s", e, exc_info=True)
            try:
                dm_fail_reason_total.labels(reason=_classify_dm_error(status_code=None, error=str(e)), pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass
            return {"ok": False, "error": str(e)}
        
        initial_match_count = len(matches)
        
        # Calculate assignment ratings for each match
        matches = _calculate_match_ratings(matches, payload)
        
        # Apply adaptive threshold filtering
        matches = _filter_by_adaptive_threshold(matches)
        
        # Apply hard cap on recipients
        matches = matches[:DM_MAX_RECIPIENTS]
        
        filtered_count = initial_match_count - len(matches)
        if filtered_count > 0:
            log_event(logger, logging.INFO, "dm_adaptive_filter", 
                     initial_matches=initial_match_count, 
                     filtered_out=filtered_count, 
                     remaining=len(matches))
        
        if not matches:
            log_event(logger, logging.INFO, "dm_no_matches", 
                     initial_matches=initial_match_count,
                     after_filtering=len(matches))
            return {"ok": True, "sent": 0, "matched": 0, "initial_matched": initial_match_count}

        reply_markup = None
        try:
            reply_markup = build_inline_keyboard(payload)
        except Exception:
            logger.exception("dm_inline_keyboard_error")

        sent = 0
        failures = 0
        # Get the postal_coords_estimated flag from payload
        parsed = payload.get("parsed") or {}
        postal_coords_estimated = parsed.get("postal_coords_estimated", False)
        
        for match in matches:
            chat_id = str(match.get("chat_id") or "").strip()
            if not chat_id:
                continue

            distance_km = match.get("distance_km")
            text = build_message_text(
                payload, 
                include_clicks=False, 
                clicks=0, 
                distance_km=_safe_float(distance_km),
                postal_coords_estimated=bool(postal_coords_estimated)
            )
            log_event(logger, logging.DEBUG, "dm_send_attempt", chat_id=chat_id)
            res = _telegram_send_message(chat_id, text, reply_markup=reply_markup)
            status = res.get("status_code") or 0

            if status == 429:
                try:
                    dm_rate_limited_total.labels(pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
                retry_after = None
                try:
                    retry_after = int(res["data"].get("parameters", {}).get("retry_after") or 0)
                except Exception:
                    retry_after = None
                sleep_s = max(1, min(30, retry_after or 2))
                log_event(logger, logging.WARNING, "dm_rate_limited", chat_id=chat_id, sleep_s=sleep_s)
                time.sleep(sleep_s)
                res = _telegram_send_message(chat_id, text, reply_markup=reply_markup)
                status = res.get("status_code") or 0

            if status >= 400:
                failures += 1
                log_event(logger, logging.WARNING, "dm_send_failed", chat_id=chat_id, status_code=status)
                try:
                    dm_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
                try:
                    err_text = None
                    if isinstance(res.get("data"), dict):
                        err_text = res["data"].get("description") or res["data"].get("text")
                    dm_fail_reason_total.labels(
                        reason=_classify_dm_error(status_code=int(status), error=str(err_text or "")),
                        pipeline_version=pv,
                        schema_version=sv,
                    ).inc()
                except Exception:
                    pass
                continue

            sent += 1
            try:
                dm_sent_total.labels(pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass
            
            # Record assignment rating for this tutor (for adaptive threshold calculation)
            try:
                from TutorDexBackend.supabase_store import SupabaseStore
                sb_record = SupabaseStore()
                if sb_record.enabled():
                    tutor_id = match.get("tutor_id")
                    rating = match.get("rating")
                    if tutor_id and rating is not None:
                        # Get assignment internal ID from parsed data
                        assignment_db_id = parsed.get("id")  # Internal DB ID
                        if assignment_db_id:
                            user_id = sb_record.upsert_user(firebase_uid=str(tutor_id), email=None, name=None)
                            if user_id:
                                sb_record.record_assignment_rating(
                                    user_id=user_id,
                                    assignment_id=int(assignment_db_id),
                                    rating_score=float(rating),
                                    distance_km=match.get("distance_km"),
                                    rate_min=match.get("rate_min"),
                                    rate_max=match.get("rate_max"),
                                    match_score=match.get("score", 0),
                                )
            except Exception as e:
                # Don't fail DM if rating recording fails
                logger.debug(f"Could not record assignment rating: {e}")
            
            time.sleep(0.05)

        fallback_written = False
        if failures:
            try:
                with open(DM_FALLBACK_FILE, "a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps(
                            {"payload": payload, "matched": matches},
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
                fallback_written = True
                log_event(logger, logging.INFO, "dm_fallback_written", path=str(DM_FALLBACK_FILE))
                try:
                    dm_fail_reason_total.labels(reason="fallback_written", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
            except Exception:
                logger.exception("Failed to write DM fallback file path=%s", DM_FALLBACK_FILE)
                try:
                    dm_fail_reason_total.labels(reason="fallback_write_failed", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass

        log_event(
            logger,
            logging.INFO,
            "dm_summary",
            initial_matched=initial_match_count,
            matched=len(matches),
            sent=sent,
            failures=failures,
            fallback_written=fallback_written,
        )
        return {
            "ok": failures == 0, 
            "initial_matched": initial_match_count,
            "matched": len(matches), 
            "sent": sent, 
            "failures": failures,
        }
