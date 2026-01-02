"""
Reprocess recent raw Telegram messages into canonical assignment rows.

Use case:
- LLM outage caused extraction failures.
- You want to re-run extraction + enrichment + Supabase persistence for a recent time window.

Source of truth:
- Reads from Supabase `telegram_messages_raw` (lossless raw history).

Safety:
- Does NOT broadcast and does NOT DM. It only extracts + persists to Supabase.
"""

from pathlib import Path
import sys

AGG_DIR = Path(__file__).resolve().parents[1]  # noqa: E402
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from compilation_detection import is_compilation
from extract_key_info import extract_assignment_with_model, process_parsed_payload
from extractors.time_availability import extract_time_availability
from hard_validator import hard_validate
from normalize import normalize_text
from signals_builder import build_signals
from supabase_persist import persist_assignment_to_supabase
from supabase_raw_persist import SupabaseRawStore
from logging_setup import bind_log_context, log_event, setup_logging
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

# --------------------------------------------------------------------------------------
# Edit these two values when you need to reprocess a window (no CLI args on purpose).
# --------------------------------------------------------------------------------------
DAYS_BACK = 0
HOURS_BACK = 24


setup_logging()
logger = logging.getLogger("reprocess_recent")


@dataclass(frozen=True)
class Counters:
    scanned: int = 0
    ok: int = 0
    failed: int = 0
    skipped: int = 0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_env() -> None:
    agg_dir = Path(__file__).resolve().parents[1]
    env_path = agg_dir / ".env"

    if load_dotenv and env_path.exists():
        load_dotenv(dotenv_path=env_path)
        return

    if not env_path.exists():
        return

    # Simple parser: supports KEY=VALUE or KEY: VALUE and quoted values.
    try:
        raw = env_path.read_text(encoding="utf8")
        for ln in raw.splitlines():
            line = ln.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
            elif ":" in line:
                k, v = line.split(":", 1)
            else:
                continue
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception:
        logger.debug("env_parse_failed", exc_info=True)


def _parse_channels_from_env() -> List[str]:
    raw = (os.environ.get("CHANNEL_LIST") or os.environ.get("CHANNELS") or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip().strip('"').strip("'") for x in items if str(x).strip()]
        except Exception:
            inner = raw[1:-1]
            return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _normalize_channel_link(value: str) -> str:
    s = str(value or "").strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://"):
        return s.replace("https://", "").replace("http://", "").strip("/")
    s = s.lstrip("@")
    if not s.startswith("t.me/"):
        s = f"t.me/{s}"
    return s


def _looks_like_assignment(parsed: Dict[str, Any]) -> bool:
    if not isinstance(parsed, dict) or not parsed:
        return False

    if str(parsed.get("assignment_code") or "").strip():
        return True

    signals = 0

    # V2 schema signals
    if str(parsed.get("academic_display_text") or "").strip() or str(parsed.get("academic_tags_raw") or "").strip():
        signals += 1

    rate_text = str(parsed.get("hourly_rate") or "").strip()
    if not rate_text and isinstance(parsed.get("rate"), dict):
        rate_text = str((parsed.get("rate") or {}).get("raw_text") or "").strip()
    if rate_text:
        signals += 1

    ta = parsed.get("time_availability")
    if isinstance(ta, dict):
        note = str(ta.get("note") or "").strip()
        if note:
            signals += 1
        else:
            for section in ("explicit", "estimated"):
                day_map = ta.get(section)
                if isinstance(day_map, dict) and any(isinstance(v, list) and any(str(x).strip() for x in v) for v in day_map.values()):
                    signals += 1
                    break

    lesson = parsed.get("lesson_schedule")
    if isinstance(lesson, dict):
        if str(lesson.get("raw_text") or "").strip():
            signals += 1
        elif any(lesson.get(k) is not None for k in ("lessons_per_week", "hours_per_lesson", "total_hours_per_week")):
            signals += 1
    elif isinstance(lesson, list) and any(isinstance(x, str) and x.strip() for x in lesson):
        signals += 1

    # Legacy schema signals (kept for older pipeline versions)
    if parsed.get("subjects"):
        signals += 1
    if str(parsed.get("level") or "").strip():
        signals += 1
    if str(parsed.get("hourly_rate") or "").strip():
        signals += 1
    if parsed.get("postal_code") or parsed.get("postal_code_estimated"):
        signals += 1
    if parsed.get("address") or parsed.get("nearest_mrt"):
        signals += 1
    if parsed.get("time_slots") or parsed.get("estimated_time_slots") or str(parsed.get("time_slots_note") or "").strip():
        signals += 1

    return signals >= 2


def _report_path() -> Path:
    out_dir = Path(__file__).resolve().parent / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    return out_dir / f"reprocess_recent_{ts}.jsonl"


def _fetch_raw_batch(
    *,
    store: SupabaseRawStore,
    channel_link: str,
    since_iso: str,
    until_iso: str,
    offset: int,
    limit: int,
) -> List[Dict[str, Any]]:
    if not store.client:
        return []

    table = store.cfg.messages_table
    ch = requests.utils.quote(channel_link, safe="")
    since_q = requests.utils.quote(since_iso, safe="")
    until_q = requests.utils.quote(until_iso, safe="")

    select = "id,channel_link,channel_id,message_id,message_date,raw_text,is_forward,deleted_at"
    q = (
        f"{table}"
        f"?select={select}"
        f"&channel_link=eq.{ch}"
        f"&message_date=gte.{since_q}"
        f"&message_date=lt.{until_q}"
        f"&deleted_at=is.null"
        f"&order=message_date.asc,message_id.asc"
        f"&limit={int(limit)}"
        f"&offset={int(offset)}"
    )

    resp = store.client.get(q, timeout=30)
    if resp.status_code >= 400:
        log_event(logger, logging.WARNING, "raw_query_status", status_code=resp.status_code, body=resp.text[:300], channel=channel_link)
        return []
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []


def main() -> None:
    _load_env()

    if DAYS_BACK < 0 or HOURS_BACK < 0:
        raise SystemExit("DAYS_BACK and HOURS_BACK must be >= 0")

    since = _utc_now() - timedelta(days=int(DAYS_BACK), hours=int(HOURS_BACK))
    until = _utc_now()

    store = SupabaseRawStore()
    if not store.enabled() or not store.client:
        raise SystemExit(
            "Supabase raw store not enabled. Check SUPABASE_URL_HOST/SUPABASE_URL_DOCKER/SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY + SUPABASE_RAW_ENABLED."
        )

    channels = [_normalize_channel_link(c) for c in _parse_channels_from_env() if str(c).strip()]
    if not channels:
        raise SystemExit("No channels configured. Set CHANNEL_LIST (or CHANNELS) in TutorDexAggregator/.env.")

    report_path = _report_path()
    log_event(
        logger,
        logging.INFO,
        "reprocess_start",
        channels=len(channels),
        since=since.isoformat(),
        until=until.isoformat(),
        report=str(report_path),
    )

    total = {"scanned": 0, "ok": 0, "failed": 0, "skipped": 0}
    per_channel: Dict[str, Dict[str, int]] = {}

    with report_path.open("a", encoding="utf-8") as fh:
        for ch in channels:
            per_channel.setdefault(ch, {"scanned": 0, "ok": 0, "failed": 0, "skipped": 0})
            offset = 0
            limit = 500

            while True:
                batch = _fetch_raw_batch(
                    store=store,
                    channel_link=ch,
                    since_iso=since.isoformat(),
                    until_iso=until.isoformat(),
                    offset=offset,
                    limit=limit,
                )
                if not batch:
                    break

                for row in batch:
                    msg_id = str(row.get("message_id") or "").strip()
                    raw_text = str(row.get("raw_text") or "").strip()
                    is_forward = bool(row.get("is_forward"))

                    cid = f"reprocess:{ch}:{msg_id}"
                    per_channel[ch]["scanned"] += 1
                    total["scanned"] += 1

                    if not msg_id or not raw_text:
                        per_channel[ch]["skipped"] += 1
                        total["skipped"] += 1
                        fh.write(json.dumps({"channel": ch, "message_id": msg_id, "ok": False, "skipped": "empty"}, ensure_ascii=False) + "\n")
                        continue

                    if is_forward:
                        per_channel[ch]["skipped"] += 1
                        total["skipped"] += 1
                        fh.write(json.dumps({"channel": ch, "message_id": msg_id, "ok": False, "skipped": "forward"}, ensure_ascii=False) + "\n")
                        continue

                    is_comp, comp_reasons = is_compilation(raw_text)
                    if is_comp:
                        per_channel[ch]["skipped"] += 1
                        total["skipped"] += 1
                        fh.write(
                            json.dumps(
                                {"channel": ch, "message_id": msg_id, "ok": False, "skipped": "compilation", "details": comp_reasons},
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
                        continue

                    with bind_log_context(cid=cid, channel=ch, message_id=msg_id, step="reprocess"):
                        try:
                            normalized_text = normalize_text(raw_text)
                            use_norm = _truthy(os.environ.get("USE_NORMALIZED_TEXT_FOR_LLM"))
                            llm_input = normalized_text if use_norm else raw_text

                            parsed = extract_assignment_with_model(llm_input, chat=ch, cid=cid)
                            if not isinstance(parsed, dict):
                                parsed = {}

                            if not _looks_like_assignment(parsed):
                                per_channel[ch]["skipped"] += 1
                                total["skipped"] += 1
                                fh.write(
                                    json.dumps({"channel": ch, "message_id": msg_id, "ok": False, "skipped": "non_assignment"}, ensure_ascii=False)
                                    + "\n"
                                )
                                continue

                            payload: Dict[str, Any] = {
                                "cid": cid,
                                "channel_link": ch,
                                "channel_id": row.get("channel_id"),
                                "message_id": msg_id,
                                "message_link": None,
                                "date": row.get("message_date"),
                                "raw_text": raw_text,
                                "parsed": parsed,
                            }

                            payload = process_parsed_payload(payload, False)

                            # Deterministic time overwrite (recommended).
                            if _truthy(os.environ.get("USE_DETERMINISTIC_TIME")):
                                try:
                                    det_ta, det_meta = extract_time_availability(raw_text=raw_text, normalized_text=normalized_text)
                                    if isinstance(payload.get("parsed"), dict):
                                        payload["parsed"]["time_availability"] = det_ta
                                except Exception:
                                    det_meta = {"ok": False, "error": "time_extract_failed"}
                            else:
                                det_meta = None

                            # Hard validation (default enforce for reprocessing).
                            hard_mode = (os.environ.get("HARD_VALIDATE_MODE") or "enforce").strip().lower()
                            hard_meta = None
                            if hard_mode in {"report", "enforce"}:
                                try:
                                    cleaned, violations = hard_validate(payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
                                    hard_meta = {"mode": hard_mode, "violations_count": len(violations), "violations": violations[:50]}
                                    if hard_mode == "enforce":
                                        payload["parsed"] = cleaned
                                except Exception as e:
                                    hard_meta = {"mode": hard_mode, "error": str(e)}

                            # Deterministic signals (recommended).
                            sig_meta = None
                            if _truthy(os.environ.get("ENABLE_DETERMINISTIC_SIGNALS")):
                                try:
                                    sig, err = build_signals(parsed=payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
                                    sig_meta = {"ok": False, "error": err} if err else {"ok": True, "signals": sig}
                                except Exception as e:
                                    sig_meta = {"ok": False, "error": str(e)}

                            payload["meta"] = {
                                "normalization": {"chars": len(normalized_text), "preview": normalized_text[:200]},
                                "time_deterministic": det_meta,
                                "hard_validation": hard_meta,
                                "signals": sig_meta,
                            }
                            persist_res = persist_assignment_to_supabase(payload)

                            ok = bool(persist_res and persist_res.get("ok"))
                            if ok:
                                per_channel[ch]["ok"] += 1
                                total["ok"] += 1
                            else:
                                per_channel[ch]["failed"] += 1
                                total["failed"] += 1

                            fh.write(
                                json.dumps(
                                    {
                                        "channel": ch,
                                        "message_id": msg_id,
                                        "ok": ok,
                                        "action": persist_res.get("action") if isinstance(persist_res, dict) else None,
                                        "status_code": persist_res.get("status_code") if isinstance(persist_res, dict) else None,
                                    },
                                    ensure_ascii=False,
                                )
                                + "\n"
                            )
                        except Exception as e:
                            per_channel[ch]["failed"] += 1
                            total["failed"] += 1
                            fh.write(json.dumps({"channel": ch, "message_id": msg_id, "ok": False, "error": str(e)}, ensure_ascii=False) + "\n")

                offset += len(batch)
                time.sleep(0.05)

    log_event(logger, logging.INFO, "reprocess_done", totals=total, per_channel=per_channel, report=str(report_path))
    print(json.dumps({"ok": True, "totals": total, "per_channel": per_channel, "report": str(report_path)}, indent=2))


if __name__ == "__main__":
    main()
