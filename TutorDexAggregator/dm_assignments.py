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


if not DM_BOT_API_URL and DM_BOT_TOKEN:
    DM_BOT_API_URL = f"https://api.telegram.org/bot{DM_BOT_TOKEN}/sendMessage"


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


def _get_or_geocode_assignment_coords(payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    parsed = payload.get("parsed") or {}
    if not isinstance(parsed, dict):
        return None, None

    lat = _safe_float(parsed.get("postal_lat"))
    lon = _safe_float(parsed.get("postal_lon"))
    if lat is not None and lon is not None:
        return lat, lon

    if _learning_mode_is_online_only(payload):
        return None, None

    try:
        from supabase_persist import _geocode_sg_postal  # best-effort + cached
    except Exception:
        _geocode_sg_postal = None

    if not _geocode_sg_postal:
        return None, None

    postal_code = parsed.get("postal_code")
    if isinstance(postal_code, list) and postal_code:
        postal_code = postal_code[0]
    if not postal_code:
        return None, None

    coords = _geocode_sg_postal(str(postal_code))
    if not coords:
        return None, None

    lat, lon = coords
    parsed["postal_lat"] = float(lat)
    parsed["postal_lon"] = float(lon)
    payload["parsed"] = parsed
    return float(lat), float(lon)


def fetch_matching_results(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            out.append({"chat_id": chat_id, "distance_km": m.get("distance_km")})
        log_event(logger, logging.DEBUG, "dm_match_ok", matched=len(out), match_ms=match_ms)
        return out

    chat_ids = _coerce_chat_ids(data.get("chat_ids"))
    out = [{"chat_id": cid, "distance_km": None} for cid in chat_ids]
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


def send_dms(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not DM_ENABLED:
        log_event(logger, logging.DEBUG, "dm_skipped", reason="dm_disabled")
        return {"ok": False, "skipped": True, "reason": "dm_disabled"}

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

        matches = matches[:DM_MAX_RECIPIENTS]
        if not matches:
            log_event(logger, logging.INFO, "dm_no_matches")
            return {"ok": True, "sent": 0, "matched": 0}

        reply_markup = None
        try:
            reply_markup = build_inline_keyboard(payload)
        except Exception:
            logger.exception("dm_inline_keyboard_error")

        sent = 0
        failures = 0
        for match in matches:
            chat_id = str(match.get("chat_id") or "").strip()
            if not chat_id:
                continue

            distance_km = match.get("distance_km")
            text = build_message_text(payload, include_clicks=False, clicks=0, distance_km=_safe_float(distance_km))
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
            matched=len(matches),
            sent=sent,
            failures=failures,
            fallback_written=fallback_written,
        )
        return {"ok": failures == 0, "matched": len(matches), "sent": sent, "failures": failures}
