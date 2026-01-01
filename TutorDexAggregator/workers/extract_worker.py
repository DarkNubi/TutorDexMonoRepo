"""
Extraction worker for the "raw collector + queue" pipeline.

Flow:
1) Claims pending rows from `public.telegram_extractions` via RPC (SKIP LOCKED).
2) Loads raw message from `public.telegram_messages_raw` by raw_id.
3) Applies filters (deleted, forwarded, compilation).
4) Runs LLM extraction + enrichment + persistence.
5) Optionally broadcasts + DMs (best-effort) like the legacy pipeline.

This is designed to be run continuously.
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from compilation_detection import is_compilation  # noqa: E402
from extract_key_info import extract_assignment_with_model, get_examples_meta, get_system_prompt_meta, process_parsed_payload  # noqa: E402
from logging_setup import bind_log_context, log_event, setup_logging  # noqa: E402
from supabase_persist import mark_assignment_closed, persist_assignment_to_supabase  # noqa: E402
from schema_validation import validate_parsed_assignment  # noqa: E402

try:
    import broadcast_assignments  # noqa: E402
except Exception:
    broadcast_assignments = None  # type: ignore

try:
    from dm_assignments import send_dms  # noqa: E402
except Exception:
    send_dms = None  # type: ignore

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

# --------------------------------------------------------------------------------------
# Easy knobs (no required CLI args; runnable via VS Code “Run”)
# --------------------------------------------------------------------------------------
DEFAULT_PIPELINE_VERSION = "singlecall_v1"
DEFAULT_CLAIM_BATCH_SIZE = 10
DEFAULT_IDLE_SLEEP_SECONDS = 2.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_S = 1.5
DEFAULT_BACKOFF_MAX_S = 60.0
DEFAULT_QUEUE_HEARTBEAT_FILE = "monitoring/heartbeat_queue_worker.json"
DEFAULT_QUEUE_HEARTBEAT_SECONDS = 30
DEFAULT_STALE_PROCESSING_SECONDS = 900  # 15 minutes

# Best-effort side-effects (same behavior as legacy pipeline when enabled/configured).
DEFAULT_ENABLE_BROADCAST = True
DEFAULT_ENABLE_DMS = True

# Runtime toggles (overridden in main() after loading .env)
ENABLE_BROADCAST = DEFAULT_ENABLE_BROADCAST
ENABLE_DMS = DEFAULT_ENABLE_DMS
MAX_ATTEMPTS = DEFAULT_MAX_ATTEMPTS
BACKOFF_BASE_S = DEFAULT_BACKOFF_BASE_S
BACKOFF_MAX_S = DEFAULT_BACKOFF_MAX_S
QUEUE_HEARTBEAT_FILE = DEFAULT_QUEUE_HEARTBEAT_FILE
QUEUE_HEARTBEAT_SECONDS = DEFAULT_QUEUE_HEARTBEAT_SECONDS
STALE_PROCESSING_SECONDS = DEFAULT_STALE_PROCESSING_SECONDS


setup_logging()
logger = logging.getLogger("extract_worker")

_CHANNEL_CACHE: Dict[str, Dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _load_env() -> None:
    env_path = AGG_DIR / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(dotenv_path=env_path)
        return
    if not env_path.exists():
        return
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


def _supabase_cfg() -> Tuple[str, str]:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    enabled = _truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key)
    if not enabled:
        raise SystemExit("Supabase not enabled. Set SUPABASE_ENABLED=1, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.")
    return url, key


def _headers(key: str) -> Dict[str, str]:
    return {"apikey": key, "authorization": f"Bearer {key}", "content-type": "application/json"}


def _rpc(url: str, key: str, fn: str, body: Dict[str, Any], *, timeout: int = 30) -> Any:
    resp = requests.post(f"{url}/rest/v1/rpc/{fn}", headers=_headers(key), json=body, timeout=timeout)
    if resp.status_code >= 400:
        raise RuntimeError(f"rpc {fn} failed status={resp.status_code} body={resp.text[:300]}")
    try:
        return resp.json()
    except Exception:
        return None


def _get_one(url: str, key: str, table: str, query: str, *, timeout: int = 30) -> Optional[Dict[str, Any]]:
    resp = requests.get(f"{url}/rest/v1/{table}?{query}", headers=_headers(key), timeout=timeout)
    if resp.status_code >= 400:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if isinstance(data, list) and data:
        row = data[0]
        return row if isinstance(row, dict) else None
    return None


def _count_from_range(rng: Optional[str]) -> Optional[int]:
    if not rng or "/" not in rng:
        return None
    try:
        return int(rng.split("/")[-1])
    except Exception:
        return None


def _queue_counts(url: str, key: str, statuses: List[str]) -> Dict[str, Optional[int]]:
    counts: Dict[str, Optional[int]] = {}
    h = dict(_headers(key))
    h["prefer"] = "count=exact"
    for st in statuses:
        resp = requests.get(f"{url}/rest/v1/telegram_extractions?status=eq.{requests.utils.quote(st, safe='')}&select=id&limit=0", headers=h, timeout=15)
        counts[st] = _count_from_range(resp.headers.get("content-range"))
    return counts


def _oldest_created_age_s(url: str, key: str, status: str) -> Optional[float]:
    row = _get_one(
        url,
        key,
        "telegram_extractions",
        f"select=created_at&status=eq.{requests.utils.quote(status, safe='')}&order=created_at.asc&limit=1",
        timeout=15,
    )
    if not row or "created_at" not in row:
        return None
    try:
        created = row["created_at"]
        if isinstance(created, str):
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            return None
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def _write_queue_heartbeat(path: Path, payload: Dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(path))
    except Exception:
        logger.debug("queue_heartbeat_write_failed", exc_info=True)


def _patch(url: str, key: str, table: str, where: str, body: Dict[str, Any], *, timeout: int = 30) -> bool:
    h = dict(_headers(key))
    h["prefer"] = "return=minimal"
    resp = requests.patch(f"{url}/rest/v1/{table}?{where}", headers=h, json=body, timeout=timeout)
    return resp.status_code < 400


def _merge_meta(existing: Any, patch: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if patch is None:
        if isinstance(existing, dict):
            return existing
        return None
    base: Dict[str, Any] = existing if isinstance(existing, dict) else {}
    merged = dict(base)
    merged.update(patch)
    return merged


def _requeue_stale_processing(url: str, key: str, *, older_than_s: int) -> Optional[int]:
    if older_than_s <= 0:
        return None
    try:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=older_than_s)
    except Exception:
        cutoff_dt = datetime.now(timezone.utc)
    cutoff = cutoff_dt.isoformat()
    h = dict(_headers(key))
    h["prefer"] = "count=exact"
    where = f"status=eq.processing&updated_at=lt.{requests.utils.quote(cutoff, safe='')}"
    # increment attempt in meta and return to pending
    body = {
        "status": "pending",
        "updated_at": _utc_now_iso(),
        "meta": requests.utils.requote_uri("jsonb_set(coalesce(meta,'{}'::jsonb), '{attempt}', to_jsonb(coalesce((meta->>'attempt')::int,0)+1))"),  # type: ignore
    }
    # PostgREST cannot accept jsonb_set via JSON body; use RPC-less patch is tricky. Use RPC endpoint via prefer=return=representation with raw SQL via /rest/v1/ (not supported).
    # Simpler approach: fetch stale ids then patch individually.
    resp = requests.get(
        f"{url}/rest/v1/telegram_extractions?{where}&select=id,meta&limit=200",
        headers=h,
        timeout=20,
    )
    if resp.status_code >= 400:
        return None
    try:
        rows = resp.json()
    except Exception:
        rows = []
    if not isinstance(rows, list) or not rows:
        return 0

    requeued = 0
    for row in rows:
        eid = row.get("id")
        meta = row.get("meta") if isinstance(row, dict) else None
        att = 0
        if isinstance(meta, dict):
            try:
                att = int(meta.get("attempt") or 0)
            except Exception:
                att = 0
        new_meta = _merge_meta(meta, {"attempt": att + 1, "requeued_at": _utc_now_iso()})
        if _patch(
            url,
            key,
            "telegram_extractions",
            f"id=eq.{requests.utils.quote(str(eid), safe='')}",
            {"status": "pending", "updated_at": _utc_now_iso(), "meta": new_meta},
            timeout=20,
        ):
            requeued += 1
    return requeued


def _mark_extraction(
    url: str,
    key: str,
    extraction_id: Any,
    *,
    status: str,
    canonical_json: Any = None,
    error: Any = None,
    meta_patch: Optional[Dict[str, Any]] = None,
    existing_meta: Any = None,
    llm_model: Optional[str] = None,
) -> None:
    body: Dict[str, Any] = {"status": status}
    body["updated_at"] = _utc_now_iso()
    if canonical_json is not None:
        body["canonical_json"] = canonical_json
    if error is not None:
        # New schema uses error_json (old schema had stage_b_errors).
        body["error_json"] = error
    merged = _merge_meta(existing_meta, meta_patch)
    if merged is not None:
        body["meta"] = merged
    if llm_model:
        body["llm_model"] = llm_model

    where = f"id=eq.{requests.utils.quote(str(extraction_id), safe='')}"
    ok = _patch(url, key, "telegram_extractions", where, body)

    # Backward-compatible retry for older schemas (stage_b_errors/model_a).
    if not ok and ("error_json" in body or "llm_model" in body):
        body2 = dict(body)
        body2.pop("updated_at", None)
        if "error_json" in body2:
            body2["stage_b_errors"] = body2.pop("error_json")
        if "llm_model" in body2:
            body2["model_a"] = body2.pop("llm_model")
        _patch(url, key, "telegram_extractions", where, body2)


def _job_attempt(job: Dict[str, Any]) -> int:
    meta = job.get("meta")
    if isinstance(meta, dict):
        try:
            return int(meta.get("attempt") or 0)
        except Exception:
            return 0
    return 0


def _fetch_raw(url: str, key: str, raw_id: Any) -> Optional[Dict[str, Any]]:
    rid = requests.utils.quote(str(raw_id), safe="")
    select = "id,channel_link,channel_id,message_id,message_date,raw_text,is_forward,deleted_at"
    return _get_one(url, key, "telegram_messages_raw", f"select={select}&id=eq.{rid}&limit=1")


def _fetch_channel(url: str, key: str, channel_link: str) -> Optional[Dict[str, Any]]:
    if channel_link in _CHANNEL_CACHE:
        return _CHANNEL_CACHE[channel_link]
    cl = requests.utils.quote(str(channel_link), safe="")
    row = _get_one(url, key, "telegram_channels", f"select=channel_link,channel_id,title&channel_link=eq.{cl}&limit=1")
    if isinstance(row, dict):
        _CHANNEL_CACHE[channel_link] = row
        return row
    _CHANNEL_CACHE[channel_link] = {}
    return None


def _build_message_link(channel_link: str, message_id: str) -> Optional[str]:
    cl = str(channel_link or "").strip()
    mid = str(message_id or "").strip()
    if not cl or not mid:
        return None
    if cl.startswith("t.me/"):
        return f"https://{cl}/{mid}"
    if cl.startswith("https://t.me/") or cl.startswith("http://t.me/"):
        cl2 = cl.replace("https://", "").replace("http://", "")
        return f"https://{cl2}/{mid}"
    return None


def _work_one(url: str, key: str, job: Dict[str, Any]) -> None:
    extraction_id = job.get("id")
    raw_id = job.get("raw_id")
    channel_link = str(job.get("channel_link") or "").strip() or "t.me/unknown"
    message_id = str(job.get("message_id") or "").strip()
    cid = f"worker:{channel_link}:{message_id}:{extraction_id}"
    existing_meta = job.get("meta")
    llm_model = (os.environ.get("LLM_MODEL_NAME") or "").strip() or None
    try:
        prompt_meta = get_system_prompt_meta()
        if not isinstance(prompt_meta, dict) or not prompt_meta:
            prompt_meta = None
    except Exception:
        prompt_meta = None

    try:
        examples_meta = get_examples_meta(channel_link)
        if not isinstance(examples_meta, dict) or not examples_meta:
            examples_meta = None
    except Exception:
        examples_meta = None

    def _with_prompt(meta_patch: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(meta_patch)
        if prompt_meta is not None:
            out["prompt"] = prompt_meta
        if examples_meta is not None:
            out["examples"] = examples_meta
        return out
    attempt = _job_attempt(job)
    if attempt >= MAX_ATTEMPTS:
        _mark_extraction(
            url,
            key,
            extraction_id,
            status="failed",
            error={"error": "max_attempts", "attempt": attempt},
            meta_patch=_with_prompt({"reason": "max_attempts", "ts": _utc_now_iso()}),
            existing_meta=existing_meta,
            llm_model=llm_model,
        )
        return

    if attempt > 1 and BACKOFF_BASE_S > 0:
        delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2 ** max(0, attempt - 1)))
        time.sleep(delay)

    with bind_log_context(cid=cid, channel=channel_link, message_id=message_id, step="worker.process"):
        ch_info = _fetch_channel(url, key, channel_link) or {}
        raw = _fetch_raw(url, key, raw_id)
        if not raw:
            _mark_extraction(url, key, extraction_id, status="failed", error={"error": "raw_missing"}, meta_patch=_with_prompt({"ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            return

        if raw.get("deleted_at"):
            try:
                close_payload = {
                    "cid": cid,
                    "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
                    "channel_link": channel_link,
                    "channel_username": channel_link.replace("https://", "").replace("http://", "").replace("t.me/", ""),
                    "message_id": raw.get("message_id"),
                    "message_link": _build_message_link(channel_link, str(raw.get("message_id") or "")),
                    "raw_text": raw.get("raw_text"),
                    "parsed": {},
                }
                close_res = mark_assignment_closed(close_payload)
            except Exception:
                close_res = None
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="skipped",
                meta_patch=_with_prompt({"reason": "deleted", "ts": _utc_now_iso(), "close_res": close_res}),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            return

        if bool(raw.get("is_forward")):
            _mark_extraction(url, key, extraction_id, status="skipped", meta_patch=_with_prompt({"reason": "forward", "ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            return

        raw_text = str(raw.get("raw_text") or "").strip()
        if not raw_text:
            _mark_extraction(url, key, extraction_id, status="skipped", meta_patch=_with_prompt({"reason": "empty_text", "ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            return

        is_comp, comp_details = is_compilation(raw_text)
        if is_comp:
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="skipped",
                meta_patch=_with_prompt({"reason": "compilation", "details": comp_details, "ts": _utc_now_iso()}),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            return

        # 1) Extract
        try:
            parsed = extract_assignment_with_model(raw_text, chat=channel_link, cid=cid)
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception as e:
            _mark_extraction(url, key, extraction_id, status="failed", error={"error": str(e)}, meta_patch=_with_prompt({"stage": "llm", "ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            return

        payload: Dict[str, Any] = {
            "cid": cid,
            "channel_link": channel_link,
            "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
            "channel_title": ch_info.get("title"),
            "channel_username": channel_link.replace("t.me/", "") if channel_link.startswith("t.me/") else None,
            "message_id": raw.get("message_id"),
            "message_link": _build_message_link(channel_link, str(raw.get("message_id") or "")),
            "date": raw.get("message_date"),
            "raw_text": raw_text,
            "parsed": parsed,
        }

        # 2) Enrich (postal estimation etc.)
        try:
            payload = process_parsed_payload(payload, False)
        except Exception as e:
            log_event(logger, logging.WARNING, "enrich_failed", error=str(e))
            payload = payload

        # 2b) Contract validation before persistence/broadcast
        ok_schema, schema_errors = validate_parsed_assignment(payload.get("parsed") or {})
        if not ok_schema:
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="failed",
                error={"error": "validation_failed", "errors": schema_errors},
                meta_patch=_with_prompt({"stage": "validation", "errors": schema_errors, "ts": _utc_now_iso()}),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            return

        # 3) Persist assignment row
        persist_res: Dict[str, Any] = {}
        try:
            r = persist_assignment_to_supabase(payload)
            persist_res = r if isinstance(r, dict) else {}
        except Exception as e:
            persist_res = {"ok": False, "error": str(e)}

        # Retry path for transient Supabase failures: requeue if attempts remain.
        if not bool(persist_res.get("ok")) and attempt + 1 < MAX_ATTEMPTS:
            new_attempt = attempt + 1
            meta_patch = _merge_meta(existing_meta, {"attempt": new_attempt, "persist_error": persist_res})
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="pending",
                error={"error": "persist_failed", "details": persist_res},
                meta_patch=_with_prompt(meta_patch),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            return

        # 4) Broadcast/DM (best-effort)
        broadcast_res: Any = None
        if ENABLE_BROADCAST and broadcast_assignments is not None:
            try:
                broadcast_assignments.send_broadcast(payload)
                broadcast_res = {"ok": True}
            except Exception as e:
                broadcast_res = {"ok": False, "error": str(e)}

        dm_res: Any = None
        if ENABLE_DMS and send_dms is not None:
            try:
                dm_res = send_dms(payload)
            except Exception as e:
                dm_res = {"ok": False, "error": str(e)}

        meta = {
            "ts": _utc_now_iso(),
            "persist": persist_res,
            "broadcast": broadcast_res,
            "dm": dm_res,
        }

        ok = bool(persist_res.get("ok"))
        _mark_extraction(url, key, extraction_id, status="ok" if ok else "failed", canonical_json=payload.get("parsed"), meta_patch=_with_prompt(meta), existing_meta=existing_meta, llm_model=llm_model)


def main() -> None:
    _load_env()
    url, key = _supabase_cfg()

    pipeline_version = (os.environ.get("EXTRACTION_PIPELINE_VERSION") or DEFAULT_PIPELINE_VERSION).strip() or DEFAULT_PIPELINE_VERSION
    claim_batch_size = int(os.environ.get("EXTRACTION_WORKER_BATCH", str(DEFAULT_CLAIM_BATCH_SIZE)) or DEFAULT_CLAIM_BATCH_SIZE)
    idle_sleep_s = float(os.environ.get("EXTRACTION_WORKER_IDLE_S", str(DEFAULT_IDLE_SLEEP_SECONDS)) or DEFAULT_IDLE_SLEEP_SECONDS)
    max_attempts = int(os.environ.get("EXTRACTION_MAX_ATTEMPTS", str(DEFAULT_MAX_ATTEMPTS)) or DEFAULT_MAX_ATTEMPTS)
    backoff_base_s = float(os.environ.get("EXTRACTION_BACKOFF_BASE_S", str(DEFAULT_BACKOFF_BASE_S)) or DEFAULT_BACKOFF_BASE_S)
    backoff_max_s = float(os.environ.get("EXTRACTION_BACKOFF_MAX_S", str(DEFAULT_BACKOFF_MAX_S)) or DEFAULT_BACKOFF_MAX_S)
    hb_file = (os.environ.get("EXTRACTION_QUEUE_HEARTBEAT_FILE") or DEFAULT_QUEUE_HEARTBEAT_FILE).strip()
    hb_seconds = int(os.environ.get("EXTRACTION_QUEUE_HEARTBEAT_SECONDS", str(DEFAULT_QUEUE_HEARTBEAT_SECONDS)) or DEFAULT_QUEUE_HEARTBEAT_SECONDS)
    stale_processing_s = int(os.environ.get("EXTRACTION_STALE_PROCESSING_SECONDS", str(DEFAULT_STALE_PROCESSING_SECONDS)) or DEFAULT_STALE_PROCESSING_SECONDS)

    enable_broadcast = str(os.environ.get("EXTRACTION_WORKER_BROADCAST", "1" if DEFAULT_ENABLE_BROADCAST else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}
    enable_dms = str(os.environ.get("EXTRACTION_WORKER_DMS", "1" if DEFAULT_ENABLE_DMS else "0")).strip().lower() in {"1", "true", "yes", "y", "on"}

    oneshot = str(os.environ.get("EXTRACTION_WORKER_ONESHOT", "")).strip().lower() in {"1", "true", "yes", "y", "on"}
    max_jobs = int(os.environ.get("EXTRACTION_WORKER_MAX_JOBS") or "0")
    if max_jobs < 0:
        max_jobs = 0

    log_event(
        logger,
        logging.INFO,
        "worker_start",
        pipeline_version=pipeline_version,
        batch_size=claim_batch_size,
        broadcast=enable_broadcast and broadcast_assignments is not None,
        dms=enable_dms and send_dms is not None,
        max_attempts=max_attempts,
        backoff_base_s=backoff_base_s,
        backoff_max_s=backoff_max_s,
        heartbeat_file=hb_file,
        heartbeat_seconds=hb_seconds,
        stale_processing_s=stale_processing_s,
        oneshot=oneshot,
        max_jobs=max_jobs or None,
    )

    global ENABLE_BROADCAST, ENABLE_DMS, MAX_ATTEMPTS, BACKOFF_BASE_S, BACKOFF_MAX_S, QUEUE_HEARTBEAT_FILE, QUEUE_HEARTBEAT_SECONDS, STALE_PROCESSING_SECONDS
    ENABLE_BROADCAST = enable_broadcast
    ENABLE_DMS = enable_dms
    MAX_ATTEMPTS = max(1, int(max_attempts))
    BACKOFF_BASE_S = max(0.0, float(backoff_base_s))
    BACKOFF_MAX_S = max(BACKOFF_BASE_S, float(backoff_max_s)) if backoff_max_s > 0 else DEFAULT_BACKOFF_MAX_S
    QUEUE_HEARTBEAT_FILE = hb_file or DEFAULT_QUEUE_HEARTBEAT_FILE
    QUEUE_HEARTBEAT_SECONDS = max(5, int(hb_seconds))
    STALE_PROCESSING_SECONDS = max(60, int(stale_processing_s))

    hb_path = AGG_DIR / QUEUE_HEARTBEAT_FILE
    last_hb = 0.0
    last_requeue = 0.0
    processed = 0

    while True:
        try:
            now = time.time()
            if now - last_requeue >= max(30, STALE_PROCESSING_SECONDS // 3):
                requeued = _requeue_stale_processing(url, key, older_than_s=STALE_PROCESSING_SECONDS)
                if requeued:
                    log_event(logger, logging.INFO, "requeued_stale_jobs", count=requeued, older_than_s=STALE_PROCESSING_SECONDS)
                last_requeue = now

            jobs = _rpc(
                url,
                key,
                "claim_telegram_extractions",
                {"p_pipeline_version": pipeline_version, "p_limit": int(max(1, claim_batch_size))},
                timeout=30,
            )
            if not isinstance(jobs, list) or not jobs:
                now = time.time()
                if now - last_hb >= QUEUE_HEARTBEAT_SECONDS:
                    counts = _queue_counts(url, key, ["pending", "processing", "ok", "failed"])
                    oldest = _oldest_created_age_s(url, key, "pending")
                    hb_payload = {
                        "ts": int(now),
                        "iso": _utc_now_iso(),
                        "counts": counts,
                        "oldest_pending_age_s": oldest,
                        "pid": os.getpid(),
                        "pipeline_version": pipeline_version,
                    }
                    _write_queue_heartbeat(hb_path, hb_payload)
                    last_hb = now

                if oneshot:
                    log_event(logger, logging.INFO, "worker_oneshot_done", processed=processed, pipeline_version=pipeline_version)
                    return

                time.sleep(max(0.25, float(idle_sleep_s)))
                continue

            for job in jobs:
                if isinstance(job, dict):
                    _work_one(url, key, job)
                    processed += 1
                    if max_jobs and processed >= max_jobs:
                        log_event(logger, logging.INFO, "worker_max_jobs_reached", processed=processed, max_jobs=max_jobs, pipeline_version=pipeline_version)
                        return
        except KeyboardInterrupt:
            log_event(logger, logging.INFO, "worker_interrupted")
            return
        except Exception as e:
            log_event(logger, logging.WARNING, "worker_loop_error", error=str(e))
            time.sleep(2.0)


if __name__ == "__main__":
    main()
