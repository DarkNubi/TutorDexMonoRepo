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

AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from compilation_detection import is_compilation  # noqa: E402
from extract_key_info import extract_assignment_with_model  # noqa: E402
from extractors.time_availability import extract_time_availability  # noqa: E402
from hard_validator import hard_validate  # noqa: E402
from normalize import normalize_text  # noqa: E402
from signals_builder import build_signals  # noqa: E402
from schema_validation import validate_parsed_assignment  # noqa: E402
from supabase_persist import persist_assignment_to_supabase  # noqa: E402
from supabase_raw_persist import SupabaseRawStore  # noqa: E402
from logging_setup import bind_log_context, log_event, setup_logging  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import re  # noqa: E402
import time  # noqa: E402
from dataclasses import dataclass  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402
from typing import Any, Dict, List, Optional  # noqa: E402

import requests  # noqa: E402

from shared.config import load_aggregator_config  # noqa: E402

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


def _parse_channels(raw: str) -> List[str]:
    raw = str(raw or "").strip()
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


def _extract_sg_postal_codes(text: str) -> Optional[List[str]]:
    try:
        codes = re.findall(r"\b(\d{6})\b", str(text or ""))
    except Exception:
        codes = []
    seen = set()
    out: List[str] = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out or None


def _coerce_list_of_str(value: Any) -> Optional[List[str]]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else None
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(_coerce_list_of_str(x) or [])
        seen = set()
        uniq: List[str] = []
        for s in out:
            ss = str(s).strip()
            if not ss or ss in seen:
                continue
            seen.add(ss)
            uniq.append(ss)
        return uniq or None
    s2 = str(value).strip()
    return [s2] if s2 else None


def _fill_postal_code_from_text(parsed: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    existing = _coerce_list_of_str(parsed.get("postal_code"))
    if existing:
        parsed["postal_code"] = existing
        return parsed
    codes = _extract_sg_postal_codes(raw_text)
    parsed["postal_code"] = codes
    return parsed


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
    cfg = load_aggregator_config()

    if DAYS_BACK < 0 or HOURS_BACK < 0:
        raise SystemExit("DAYS_BACK and HOURS_BACK must be >= 0")

    since = _utc_now() - timedelta(days=int(DAYS_BACK), hours=int(HOURS_BACK))
    until = _utc_now()

    store = SupabaseRawStore()
    if not store.enabled() or not store.client:
        raise SystemExit(
            "Supabase raw store not enabled. Check SUPABASE_URL_HOST/SUPABASE_URL_DOCKER/SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY + SUPABASE_RAW_ENABLED."
        )

    channels = [_normalize_channel_link(c) for c in _parse_channels(cfg.channel_list) if str(c).strip()]
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
                            llm_input = normalized_text if bool(cfg.use_normalized_text_for_llm) else raw_text

                            parsed = extract_assignment_with_model(llm_input, chat=ch, cid=cid)
                            if not isinstance(parsed, dict):
                                parsed = {}

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

                            # Deterministic postal-code fill (strict: only explicit 6-digit tokens).
                            if isinstance(payload.get("parsed"), dict):
                                payload["parsed"] = _fill_postal_code_from_text(payload["parsed"], raw_text)

                            # Deterministic time overwrite (recommended).
                            if bool(cfg.use_deterministic_time):
                                try:
                                    det_ta, det_meta = extract_time_availability(raw_text=raw_text, normalized_text=normalized_text)
                                    if isinstance(payload.get("parsed"), dict):
                                        payload["parsed"]["time_availability"] = det_ta
                                except Exception:
                                    det_meta = {"ok": False, "error": "time_extract_failed"}
                            else:
                                det_meta = None

                            # Hard validation (default enforce for reprocessing).
                            hard_mode = str(cfg.hard_validate_mode or "enforce").strip().lower()
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
                            if bool(cfg.enable_deterministic_signals):
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

                            ok_schema, schema_errors = validate_parsed_assignment(payload.get("parsed") or {})
                            if not ok_schema:
                                per_channel[ch]["skipped"] += 1
                                total["skipped"] += 1
                                fh.write(
                                    json.dumps(
                                        {"channel": ch, "message_id": msg_id, "ok": False, "skipped": "validation_failed", "errors": schema_errors},
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                )
                                continue
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
