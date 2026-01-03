"""
Fetch TutorCity assignments API (no LLM) and persist/broadcast/DM via existing pipeline.

Usage:
  python utilities/tutorcity_fetch.py --limit 50

Environment variables:
  TUTORCITY_API_URL (default: https://tutorcity.sg/api/tuition-assignments/)
  TUTORCITY_LIMIT (default: 50)
  TUTORCITY_TIMEOUT_SECONDS (default: 30)
  (No source label env var; source is always "TutorCity")

This script:
  - calls the API once
  - maps rows into the hardened v2 `canonical_json` display schema
  - computes deterministic time availability + signals (meta)
  - persists via `supabase_persist` (which materializes `signals_*` columns for the website/backend)
"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Optional

import requests

from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from logging_setup import bind_log_context, log_event, setup_logging
from supabase_persist import SupabaseConfig, load_config_from_env, persist_assignment_to_supabase
from normalize import normalize_text
from extractors.time_availability import extract_time_availability
from signals_builder import build_signals

try:
    from dm_assignments import send_dms
except Exception:
    send_dms = None  # type: ignore

try:
    import broadcast_assignments
except Exception:
    broadcast_assignments = None  # type: ignore


setup_logging()
logger = logging.getLogger("tutorcity_fetch")

DEFAULT_URL = "https://tutorcity.sg/api/tuition-assignments/"


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _first(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for x in value:
            s = _first(x)
            if s:
                return s
        return None
    s = str(value).strip()
    return s or None


def _join_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        parts: List[str] = []
        for x in value:
            t = _join_text(x)
            if t:
                parts.append(t)
        seen = set()
        uniq: List[str] = []
        for p in parts:
            if p in seen:
                continue
            seen.add(p)
            uniq.append(p)
        return ", ".join(uniq)
    return str(value).strip()


def _parse_rate(rate: Optional[str]) -> Dict[str, Any]:
    # Keep the original string; best-effort min/max parsing for simple ranges like "50-80 p/h" or "$30/h".
    out: Dict[str, Any] = {"min": None, "max": None, "raw_text": rate}
    if not rate:
        return out
    cleaned = rate.replace("$", "").replace("/h", "").replace("p/h", "").replace("p.h", "").replace("per hour", "")
    cleaned = cleaned.replace("to", "-").replace("–", "-").replace("—", "-")
    parts = cleaned.split("-")
    nums: List[float] = []
    for p in parts:
        try:
            n = float(str(p).strip().split()[0])
            nums.append(n)
        except Exception:
            continue

    if len(nums) == 1:
        out["min"] = out["max"] = nums[0]
    elif len(nums) >= 2:
        out["min"] = float(min(nums))
        out["max"] = float(max(nums))
    return out


def _map_row(row: Dict[str, Any], source_label: str) -> Dict[str, Any]:
    assignment_code = _first(row.get("assignment_code"))
    subjects_raw = row.get("subjects") or []
    subjects_list = subjects_raw if isinstance(subjects_raw, list) else [subjects_raw] if subjects_raw else []
    level = row.get("level")
    year = row.get("year")
    address = _first(row.get("address"))
    postal_code = _first(row.get("postal_code"))
    availability = _first(row.get("availability"))
    hourly_rate = row.get("hourly_rate")
    additional_remarks = _first(row.get("additional_remarks"))
    assignment_url = _first(row.get("assignment_url"))

    # Build an academic display string (best-effort, API-provided fields only).
    subj_bits = [str(s).strip() for s in subjects_list if str(s).strip()]
    headline_parts = [str(x).strip() for x in (year, level) if str(x).strip()]
    headline = " ".join(headline_parts).strip()
    if subj_bits:
        headline = f"{headline} {' / '.join(subj_bits)}".strip()
    academic_display_text = headline or None

    # Deterministic time availability from the API availability string (if present).
    det_time = None
    if availability:
        try:
            det_time, _meta = extract_time_availability(raw_text=availability, normalized_text=normalize_text(availability))
        except Exception:
            det_time = None

    parsed: Dict[str, Any] = {
        "assignment_code": assignment_code,
        "academic_display_text": academic_display_text,
        "learning_mode": {"mode": None, "raw_text": None},
        "address": [address] if address else None,
        "postal_code": [postal_code] if postal_code else None,
        "nearest_mrt": None,
        "lesson_schedule": None,
        "start_date": None,
        "time_availability": det_time
        or {
            "explicit": {d: [] for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")},
            "estimated": {d: [] for d in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")},
            "note": availability or None,
        },
        "rate": _parse_rate(_first(hourly_rate)),
        "additional_remarks": additional_remarks,
    }

    signals, err = build_signals(parsed=parsed, raw_text="", normalized_text=academic_display_text)
    signals_meta = {"ok": False, "error": err} if err else {"ok": True, "signals": signals}

    payload: Dict[str, Any] = {
        "cid": f"tutorcity:{assignment_code or ''}",
        "channel_title": source_label,
        "channel_link": "https://tutorcity.sg",
        "channel_username": "tutorcity_sg",
        "message_id": assignment_code,
        "message_link": assignment_url,
        "parsed": parsed,
        "raw_text": availability or None,
        "meta": {"signals": signals_meta},
        "source_type": "tutorcity_api",
    }
    return payload


def fetch_api(url: str, limit: int, timeout_s: int) -> List[Dict[str, Any]]:
    params = {"limit": limit}
    ua = os.environ.get("TUTORCITY_USER_AGENT") or "TutorDexTutorCityFetcher/1.0"
    headers = {
        "accept": "application/json",
        "user-agent": ua,
    }
    resp = requests.get(url, params=params, headers=headers, timeout=timeout_s)
    if resp.status_code >= 400:
        raise RuntimeError(f"API error status={resp.status_code} body={resp.text[:300]}")
    data = resp.json()
    rows = data.get("all_assignments_data")
    return rows if isinstance(rows, list) else []


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch TutorCity API and persist/broadcast without LLM")
    p.add_argument("--limit", type=int, default=None, help="Number of rows to fetch (default from env or 50)")
    args = p.parse_args()

    url = (os.environ.get("TUTORCITY_API_URL") or DEFAULT_URL).strip()
    limit = args.limit if args.limit is not None else _env_int("TUTORCITY_LIMIT", 50)
    timeout_s = _env_int("TUTORCITY_TIMEOUT_SECONDS", 30)
    source_label = "TutorCity"
    # Disable bumping for API rows: set bump_min_seconds extremely high.
    base_cfg = load_config_from_env()
    supa_cfg = SupabaseConfig(
        url=base_cfg.url,
        key=base_cfg.key,
        assignments_table=base_cfg.assignments_table,
        enabled=base_cfg.enabled,
        bump_min_seconds=10**9,
    )

    rows = fetch_api(url, limit, timeout_s)
    if not rows:
        print("No rows returned from API.")
        return

    for row in rows:
        payload = _map_row(row, source_label)
        cid = payload.get("cid")
        with bind_log_context(cid=str(cid), channel=payload.get("channel_link"), message_id=payload.get("message_id"), step="tutorcity"):
            log_event(logger, logging.INFO, "tutorcity_row", assignment_code=payload["parsed"].get("assignment_code"), address=payload["parsed"].get("address"))
            res = persist_assignment_to_supabase(payload, cfg=supa_cfg)
            log_event(logger, logging.INFO, "tutorcity_persist_result", res=res)

            is_insert = bool(res.get("ok")) and str(res.get("action")).lower() == "inserted"
            if broadcast_assignments is not None and is_insert:
                try:
                    broadcast_assignments.send_broadcast(payload)
                except Exception:
                    logger.exception("tutorcity_broadcast_failed")
            if send_dms is not None and is_insert:
                try:
                    send_dms(payload)
                except Exception:
                    logger.exception("tutorcity_dm_failed")


if __name__ == "__main__":
    main()
