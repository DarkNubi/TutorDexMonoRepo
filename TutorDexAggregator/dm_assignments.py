import os
import json
import time
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from logging_setup import bind_log_context, log_event, setup_logging, timed

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


def fetch_matching_chat_ids(payload: Dict[str, Any]) -> List[str]:
    headers = {"x-api-key": BACKEND_API_KEY} if BACKEND_API_KEY else None
    t0 = timed()
    resp = requests.post(TUTOR_MATCH_URL, json={"payload": payload}, headers=headers, timeout=10)
    match_ms = round((timed() - t0) * 1000.0, 2)
    if resp.status_code >= 400:
        raise RuntimeError(f"match_api_error status={resp.status_code} body={resp.text[:300]}")
    data = resp.json()
    chat_ids = _coerce_chat_ids(data.get("chat_ids"))
    log_event(logger, logging.DEBUG, "dm_match_ok", matched=len(chat_ids), match_ms=match_ms)
    return chat_ids


def _telegram_send_message(chat_id: str, text: str) -> Dict[str, Any]:
    body = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": False,
    }
    resp = requests.post(DM_BOT_API_URL, json=body, timeout=15)
    try:
        data = resp.json()
    except Exception:
        data = {"status_code": resp.status_code, "text": resp.text}
    return {"status_code": resp.status_code, "data": data}


def send_dms(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not DM_ENABLED:
        log_event(logger, logging.DEBUG, "dm_skipped", reason="dm_disabled")
        return {"ok": False, "skipped": True, "reason": "dm_disabled"}

    try:
        from broadcast_assignments import build_message_text
    except Exception as e:
        return {"ok": False, "error": f"missing_broadcast_assignments_build_message_text: {e}"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel_link = payload.get("channel_link") or payload.get("channel_username")

    with bind_log_context(cid=cid, message_id=msg_id, channel=str(channel_link) if channel_link else None, step="dm"):
        text = build_message_text(payload, include_clicks=False, clicks=0)

        try:
            chat_ids = fetch_matching_chat_ids(payload)
        except Exception as e:
            logger.warning("DM match failed error=%s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

        chat_ids = chat_ids[:DM_MAX_RECIPIENTS]
        if not chat_ids:
            log_event(logger, logging.INFO, "dm_no_matches")
            return {"ok": True, "sent": 0, "matched": 0}

        sent = 0
        failures = 0
        for chat_id in chat_ids:
            log_event(logger, logging.DEBUG, "dm_send_attempt", chat_id=chat_id)
            res = _telegram_send_message(chat_id, text)
            status = res.get("status_code") or 0

            if status == 429:
                retry_after = None
                try:
                    retry_after = int(res["data"].get("parameters", {}).get("retry_after") or 0)
                except Exception:
                    retry_after = None
                sleep_s = max(1, min(30, retry_after or 2))
                log_event(logger, logging.WARNING, "dm_rate_limited", chat_id=chat_id, sleep_s=sleep_s)
                time.sleep(sleep_s)
                res = _telegram_send_message(chat_id, text)
                status = res.get("status_code") or 0

            if status >= 400:
                failures += 1
                log_event(logger, logging.WARNING, "dm_send_failed", chat_id=chat_id, status_code=status)
                continue

            sent += 1
            time.sleep(0.05)

        fallback_written = False
        if failures:
            try:
                with open(DM_FALLBACK_FILE, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"payload": payload, "text": text, "matched_chat_ids": chat_ids}, ensure_ascii=False) + "\n")
                fallback_written = True
                log_event(logger, logging.INFO, "dm_fallback_written", path=str(DM_FALLBACK_FILE))
            except Exception:
                logger.exception("Failed to write DM fallback file path=%s", DM_FALLBACK_FILE)

        log_event(logger, logging.INFO, "dm_summary", matched=len(chat_ids), sent=sent, failures=failures, fallback_written=fallback_written)
        return {"ok": failures == 0, "matched": len(chat_ids), "sent": sent, "failures": failures}
