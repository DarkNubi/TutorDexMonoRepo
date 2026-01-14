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
import hashlib
import logging
import re
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
from compilation_message_handler import (  # noqa: E402
    confirm_compilation_identifiers,
    order_verified_identifiers,
    split_compilation_message,
)
from extractors.non_assignment_detector import is_non_assignment, detection_meta  # noqa: E402
from extract_key_info import extract_assignment_with_model, get_examples_meta, get_system_prompt_meta  # noqa: E402
from logging_setup import bind_log_context, log_event, setup_logging  # noqa: E402
from shared.config import load_aggregator_config  # noqa: E402
from supabase_persist import mark_assignment_closed, persist_assignment_to_supabase  # noqa: E402
from schema_validation import validate_parsed_assignment  # noqa: E402
from normalize import normalize_text  # noqa: E402
from hard_validator import hard_validate  # noqa: E402
from signals_builder import build_signals  # noqa: E402
from extractors.time_availability import extract_time_availability  # noqa: E402
from extractors.postal_code_estimated import estimate_postal_codes  # noqa: E402
from observability_http import start_observability_http_server  # noqa: E402
from otel import setup_otel  # noqa: E402
from observability_metrics import (  # noqa: E402
    assignment_quality_inconsistency_total,
    assignment_quality_missing_field_total,
    queue_failed,
    queue_ok,
    queue_oldest_pending_age_seconds,
    queue_oldest_processing_age_seconds,
    queue_pending,
    queue_processing,
    set_version_metrics,
    worker_job_latency_seconds,
    worker_job_stage_latency_seconds,
    worker_jobs_processed_total,
    worker_llm_call_latency_seconds,
    worker_llm_requests_total,
    worker_llm_fail_total,
    worker_requeued_stale_jobs_total,
    worker_supabase_fail_total,
    worker_supabase_latency_seconds,
    worker_supabase_requests_total,
    worker_parse_failure_total,
    worker_parse_success_total,
)

try:
    import broadcast_assignments  # noqa: E402
except Exception:
    broadcast_assignments = None  # type: ignore

try:
    from dm_assignments import send_dms  # noqa: E402
except Exception:
    send_dms = None  # type: ignore

_CFG = None

# --------------------------------------------------------------------------------------
# Easy knobs (no required CLI args; runnable via VS Code “Run”)
# --------------------------------------------------------------------------------------
DEFAULT_PIPELINE_VERSION = "2026-01-02_det_time_v1"
DEFAULT_CLAIM_BATCH_SIZE = 10
DEFAULT_IDLE_SLEEP_SECONDS = 2.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE_S = 1.5
DEFAULT_BACKOFF_MAX_S = 60.0
DEFAULT_STALE_PROCESSING_SECONDS = 900  # 15 minutes
DEFAULT_USE_NORMALIZED_TEXT_FOR_LLM = False
DEFAULT_HARD_VALIDATE_MODE = "report"  # off|report|enforce
DEFAULT_ENABLE_DETERMINISTIC_SIGNALS = True
DEFAULT_USE_DETERMINISTIC_TIME = True
DEFAULT_ENABLE_POSTAL_CODE_ESTIMATED = True

# Best-effort side-effects (same behavior as legacy pipeline when enabled/configured).
DEFAULT_ENABLE_BROADCAST = True
DEFAULT_ENABLE_DMS = True

# Runtime toggles (overridden in main() after loading .env)
ENABLE_BROADCAST = DEFAULT_ENABLE_BROADCAST
ENABLE_DMS = DEFAULT_ENABLE_DMS
MAX_ATTEMPTS = DEFAULT_MAX_ATTEMPTS
BACKOFF_BASE_S = DEFAULT_BACKOFF_BASE_S
BACKOFF_MAX_S = DEFAULT_BACKOFF_MAX_S
STALE_PROCESSING_SECONDS = DEFAULT_STALE_PROCESSING_SECONDS
USE_NORMALIZED_TEXT_FOR_LLM = DEFAULT_USE_NORMALIZED_TEXT_FOR_LLM
HARD_VALIDATE_MODE = DEFAULT_HARD_VALIDATE_MODE
ENABLE_DETERMINISTIC_SIGNALS = DEFAULT_ENABLE_DETERMINISTIC_SIGNALS
USE_DETERMINISTIC_TIME = DEFAULT_USE_DETERMINISTIC_TIME
ENABLE_POSTAL_CODE_ESTIMATED = DEFAULT_ENABLE_POSTAL_CODE_ESTIMATED


def _cfg():
    global _CFG
    if _CFG is None:
        _CFG = load_aggregator_config()
    return _CFG


# Initialize circuit breaker for LLM calls
from circuit_breaker import CircuitBreaker, CircuitBreakerOpenError  # noqa: E402

# Circuit breaker prevents queue burn when LLM API is down
llm_circuit_breaker = CircuitBreaker(
    failure_threshold=int(_cfg().llm_circuit_breaker_threshold),
    timeout_seconds=int(_cfg().llm_circuit_breaker_timeout_seconds),
)


setup_logging()
logger = logging.getLogger("extract_worker")
_V = set_version_metrics(component="worker")
from sentry_init import setup_sentry  # noqa: E402
setup_sentry(service_name=_cfg().sentry_service_name or "tutordex-aggregator-worker")
setup_otel(service_name=_cfg().otel_service_name or "tutordex-aggregator-worker")
_DEFAULT_LOG_CTX = bind_log_context(component="worker", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version)


def _skipped_messages_chat_id() -> Optional[str]:
    v = str(_cfg().skipped_messages_chat_id or "").strip()
    return v or None


def _default_skipped_messages_thread_id() -> Optional[int]:
    # Legacy single-thread fallback for all triage messages.
    return _cfg().skipped_messages_thread_id


def _triage_thread_id(kind: str) -> Optional[int]:
    """
    Route triage messages to different Telegram topics (threads).

    Back-compat: falls back to SKIPPED_MESSAGES_THREAD_ID when a kind-specific topic is not configured.
    """
    k = str(kind or "").strip().lower()
    if k in {"extraction_error", "extraction_errors", "extraction"}:
        return _cfg().skipped_messages_thread_id_extraction_errors or _default_skipped_messages_thread_id()
    if k in {"non_assignment", "non-assignments", "nonassignment"}:
        return _cfg().skipped_messages_thread_id_non_assignment or _default_skipped_messages_thread_id()
    if k in {"compilation", "compilations"}:
        return _cfg().skipped_messages_thread_id_compilations or _default_skipped_messages_thread_id()
    return _default_skipped_messages_thread_id()


def _skipped_messages_bot_token() -> Optional[str]:
    # Prefer the broadcast/group bot for channel forwarding; fallback to DM bot.
    v = str(_cfg().group_bot_token or "").strip() or str(_cfg().dm_bot_token or "").strip()
    return v or None


def _telegram_bot_api_base() -> Optional[str]:
    # Allow override, but default to standard Telegram Bot API.
    return str(_cfg().bot_api_url or "").strip() or None


def _telegram_send_message(*, to_chat_id: str, text: str, thread_id: Optional[int] = None) -> Dict[str, Any]:
    token = _skipped_messages_bot_token()
    base = _telegram_bot_api_base()
    if not token and not base:
        return {"ok": False, "error": "no_bot_token_or_api_url"}

    url = base
    if not url and token:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
    elif url and not url.endswith("/sendMessage"):
        url = url.rstrip("/") + "/sendMessage"

    try:
        body: Dict[str, Any] = {
            "chat_id": to_chat_id,
            "text": text,
            "disable_web_page_preview": True,
            "disable_notification": True,
        }
        if thread_id is not None:
            body["message_thread_id"] = int(thread_id)
        resp = requests.post(
            url,
            json=body,
            timeout=10,
        )
        return {"ok": resp.status_code < 400, "status_code": resp.status_code, "body": (resp.text or "")[:500]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _chunk_text(text: str, *, max_len: int) -> List[str]:
    t = str(text or "")
    if not t:
        return [""]
    if max_len <= 0:
        return [t]
    return [t[i: i + max_len] for i in range(0, len(t), max_len)]


def _try_report_triage_message(
    *,
    kind: str,
    raw: Dict[str, Any],
    channel_link: str,
    summary: str,
    stage: str,
    extracted_codes: Optional[List[str]] = None,
) -> None:
    to_chat_id = _skipped_messages_chat_id()
    if not to_chat_id:
        return

    thread_id = _triage_thread_id(kind)

    msg_id = raw.get("message_id")
    link = _build_message_link(channel_link, str(msg_id or "")) or ""
    raw_text = str(raw.get("raw_text") or "").strip()

    kind_norm = str(kind or "").strip().lower()
    title = "TutorDex: triage"
    if kind_norm in {"extraction_error", "extraction_errors", "extraction"}:
        title = "TutorDex: extraction error"
    elif kind_norm in {"non_assignment", "non-assignments", "nonassignment"}:
        title = "TutorDex: non-assignment (skipped)"
    elif kind_norm in {"compilation", "compilations"}:
        title = "TutorDex: compilation (skipped)"

    # Telegram sendMessage hard limit is 4096 chars. Keep a conservative ceiling.
    max_msg_len = 3600
    codes_clean: Optional[List[str]] = None
    codes_line = ""
    codes_preview_limit = 40
    if extracted_codes is not None:
        codes_clean = [str(c).strip() for c in (extracted_codes or []) if str(c).strip()]
        if not codes_clean:
            codes_line = "codes=[]\n"
        else:
            preview = codes_clean[:codes_preview_limit]
            rest = len(codes_clean) - len(preview)
            preview_joined = ", ".join(preview)
            codes_line = f"codes=[{preview_joined}{f' (+{rest} more)' if rest > 0 else ''}]\n"
    header = (
        f"{title}\n"
        f"stage={stage}\n"
        f"channel={channel_link}\n"
        + (f"message_id={msg_id}\n" if msg_id is not None else "")
        + (f"link={link}\n" if link else "")
        + (codes_line if codes_line else "")
        + f"summary={str(summary or '')[:800]}\n"
        "\n"
        "raw_text:\n"
    )

    # First message includes header + the first chunk of raw text.
    try:
        first_budget = max(200, max_msg_len - len(header))
        raw_chunks = _chunk_text(raw_text, max_len=first_budget)
        first = header + (raw_chunks[0] if raw_chunks else "")
        res0 = _telegram_send_message(to_chat_id=to_chat_id, text=first, thread_id=thread_id)
        log_event(
            logger,
            logging.INFO,
            "failed_message_triage_sent",
            ok=bool(res0.get("ok")),
            kind=kind_norm,
            stage=stage,
            channel=channel_link,
            message_id=str(msg_id),
            part=1,
            parts=max(1, len(raw_chunks)),
            thread_id=thread_id,
            res=res0,
        )
    except Exception:
        return

    # If we have a large codes list, send it in follow-up messages (so we include *all* extracted codes).
    if codes_clean is not None and len(codes_clean) > codes_preview_limit:
        try:
            codes_full = ", ".join(codes_clean)
            prefix = f"{title}: codes (full)\n"
            budget = max(200, max_msg_len - len(prefix))
            parts = _chunk_text(codes_full, max_len=budget)
            for idx, chunk in enumerate(parts, start=1):
                resi = _telegram_send_message(
                    to_chat_id=to_chat_id,
                    text=f"{prefix}(part {idx}/{len(parts)})\n{chunk}",
                    thread_id=thread_id,
                )
                log_event(
                    logger,
                    logging.INFO,
                    "failed_message_triage_sent",
                    ok=bool(resi.get("ok")),
                    kind=kind_norm,
                    stage=stage,
                    channel=channel_link,
                    message_id=str(msg_id),
                    part=f"codes:{idx}",
                    parts=f"codes:{len(parts)}",
                    thread_id=thread_id,
                    res=resi,
                )
        except Exception:
            pass

    # Remaining raw text chunks (if any): send as additional messages.
    if raw_chunks and len(raw_chunks) > 1:
        for idx, chunk in enumerate(raw_chunks[1:], start=2):
            try:
                part_prefix = f"{title}: raw_text (part {idx}/{len(raw_chunks)})\n"
                budget = max(50, max_msg_len - len(part_prefix))
                for sub in _chunk_text(chunk, max_len=budget):
                    resi = _telegram_send_message(to_chat_id=to_chat_id, text=part_prefix + sub, thread_id=thread_id)
                    log_event(
                        logger,
                        logging.INFO,
                        "failed_message_triage_sent",
                        ok=bool(resi.get("ok")),
                        kind=kind_norm,
                        stage=stage,
                        channel=channel_link,
                        message_id=str(msg_id),
                        part=idx,
                        parts=len(raw_chunks),
                        thread_id=thread_id,
                        res=resi,
                    )
            except Exception:
                # best-effort; do not fail the worker
                pass


_DEFAULT_LOG_CTX.__enter__()

_CHANNEL_CACHE: Dict[str, Dict[str, Any]] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_env() -> None:
    # Legacy hook (removed): config is loaded via `shared.config` and `_env_file` now.
    return


def _supabase_cfg() -> Tuple[str, str]:
    cfg = _cfg()
    url = cfg.supabase_rest_url
    key = cfg.supabase_auth_key
    if not (cfg.supabase_enabled and url and key):
        raise SystemExit("Supabase not enabled/misconfigured. Check SUPABASE_* settings in .env.")
    return url, key


def _headers(key: str) -> Dict[str, str]:
    return {"apikey": key, "authorization": f"Bearer {key}", "content-type": "application/json"}


def _rpc(url: str, key: str, fn: str, body: Dict[str, Any], *, timeout: int = 30) -> Any:
    t0 = time.perf_counter()
    op = f"rpc:{fn}"
    try:
        worker_supabase_requests_total.labels(operation=op, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
    except Exception:
        pass
    try:
        resp = requests.post(f"{url}/rest/v1/rpc/{fn}", headers=_headers(key), json=body, timeout=timeout)
        # Check for ambiguous overloads (HTTP 300) and other errors
        from supabase_env import check_rpc_response  # noqa: E402
        check_rpc_response(resp, fn)
        try:
            return resp.json()
        except Exception:
            return None
    finally:
        try:
            worker_supabase_latency_seconds.labels(operation=op, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                max(0.0, time.perf_counter() - t0)
            )
        except Exception:
            pass


def _get_one(url: str, key: str, table: str, query: str, *, timeout: int = 30) -> Optional[Dict[str, Any]]:
    t0 = time.perf_counter()
    op = f"get:{table}"
    try:
        worker_supabase_requests_total.labels(operation=op, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
    except Exception:
        pass
    try:
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
    finally:
        try:
            worker_supabase_latency_seconds.labels(operation=op, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                max(0.0, time.perf_counter() - t0)
            )
        except Exception:
            pass


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


def _patch(url: str, key: str, table: str, where: str, body: Dict[str, Any], *, timeout: int = 30) -> bool:
    t0 = time.perf_counter()
    op = f"patch:{table}"
    try:
        worker_supabase_requests_total.labels(operation=op, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
    except Exception:
        pass
    h = dict(_headers(key))
    h["prefer"] = "return=minimal"
    resp = requests.patch(f"{url}/rest/v1/{table}?{where}", headers=h, json=body, timeout=timeout)
    try:
        worker_supabase_latency_seconds.labels(operation=op, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
            max(0.0, time.perf_counter() - t0)
        )
    except Exception:
        pass
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


def _sha256(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _extract_sg_postal_codes(text: str) -> List[str]:
    try:
        codes = re.findall(r"\b(\d{6})\b", str(text or ""))
    except Exception:
        codes = []
    # de-dup while preserving order
    seen = set()
    out: List[str] = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _llm_model_name() -> str:
    return str(_cfg().llm_model_name or "").strip() or "unknown"


def _classify_llm_error(err: Exception) -> str:
    s = str(err or "").lower()
    if "timeout" in s or "timed out" in s:
        return "llm_timeout"
    if "connection" in s or "connection refused" in s or "failed to establish a new connection" in s:
        return "llm_connection"
    if "failed to parse json" in s or "json parsing" in s or "json parse" in s:
        return "llm_invalid_json"
    if "failed to parse llm response" in s or "no valid text found" in s:
        return "llm_bad_response"
    return "llm_error"


def _inc_quality_missing(field: str, channel: str) -> None:
    try:
        assignment_quality_missing_field_total.labels(
            field=field,
            channel=channel,
            pipeline_version=_V.pipeline_version,
            schema_version=_V.schema_version,
        ).inc()
    except Exception:
        pass


def _inc_quality_inconsistency(kind: str, channel: str) -> None:
    try:
        assignment_quality_inconsistency_total.labels(
            kind=kind,
            channel=channel,
            pipeline_version=_V.pipeline_version,
            schema_version=_V.schema_version,
        ).inc()
    except Exception:
        pass


def _quality_checks(*, parsed: Dict[str, Any], signals: Optional[Dict[str, Any]], channel: str) -> None:
    p = parsed if isinstance(parsed, dict) else {}
    s = signals if isinstance(signals, dict) else {}

    subjects = s.get("subjects") or []
    levels = s.get("levels") or []
    if not isinstance(subjects, list) or len(subjects) == 0:
        _inc_quality_missing("signals_subjects", channel)
    if not isinstance(levels, list) or len(levels) == 0:
        _inc_quality_missing("signals_levels", channel)

    postal = p.get("postal_code")
    if not (isinstance(postal, list) and any(str(x).strip() for x in postal)):
        _inc_quality_missing("postal_code", channel)

    academic = str(p.get("academic_display_text") or "")
    if not academic.strip():
        _inc_quality_missing("academic_display_text", channel)

    headline = academic.lower()
    sig_levels = {str(x).strip() for x in levels} if isinstance(levels, list) else set()
    if "ib" in headline and "IB" not in sig_levels:
        _inc_quality_inconsistency("headline_ib_no_signal", channel)
    if "igcse" in headline and "IGCSE" not in sig_levels:
        _inc_quality_inconsistency("headline_igcse_no_signal", channel)


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
        # de-dup while preserving order
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
    """
    Best-effort, deterministic enrichment:
    - Ensures `parsed["postal_code"]` is a list[str] when explicit 6-digit SG codes exist in the post.
    - Never guesses a postal code from an address (no external geocoding here).
    """
    if not isinstance(parsed, dict):
        return {}
    existing = _coerce_list_of_str(parsed.get("postal_code"))
    if existing:
        parsed["postal_code"] = existing
        return parsed
    codes = _extract_sg_postal_codes(raw_text)
    if codes:
        parsed["postal_code"] = codes
    else:
        parsed["postal_code"] = None
    return parsed


def _hard_mode() -> str:
    m = str(HARD_VALIDATE_MODE or "").strip().lower()
    if m in {"off", "report", "enforce"}:
        return m
    return "report"


def _signals_enabled() -> bool:
    return bool(_cfg().enable_deterministic_signals)


def _deterministic_time_enabled() -> bool:
    return bool(_cfg().use_deterministic_time)


def _postal_code_estimated_enabled() -> bool:
    return bool(_cfg().enable_postal_code_estimated)


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
        # type: ignore
        "meta": requests.utils.requote_uri("jsonb_set(coalesce(meta,'{}'::jsonb), '{attempt}', to_jsonb(coalesce((meta->>'attempt')::int,0)+1))"),
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
    select = "id,channel_link,channel_id,message_id,message_date,edit_date,raw_text,is_forward,deleted_at"
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


def _work_one(url: str, key: str, job: Dict[str, Any]) -> str:
    extraction_id = job.get("id")
    raw_id = job.get("raw_id")
    channel_link = str(job.get("channel_link") or "").strip() or "t.me/unknown"
    message_id = str(job.get("message_id") or "").strip()
    cid = f"worker:{channel_link}:{message_id}:{extraction_id}"
    existing_meta = job.get("meta")
    llm_model = str(_cfg().llm_model_name or "").strip() or None
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
        try:
            worker_parse_failure_total.labels(
                channel=channel_link, reason="max_attempts", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version
            ).inc()
        except Exception:
            pass
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
        return "failed"

    if attempt > 1 and BACKOFF_BASE_S > 0:
        delay = min(BACKOFF_MAX_S, BACKOFF_BASE_S * (2 ** max(0, attempt - 1)))
        time.sleep(delay)

    with bind_log_context(
        cid=cid,
        channel=channel_link,
        message_id=message_id,
        assignment_id=str(extraction_id) if extraction_id is not None else None,
        step="worker.process",
        component="worker",
        pipeline_version=_V.pipeline_version,
        schema_version=_V.schema_version,
    ):
        t_load0 = time.perf_counter()
        ch_info = _fetch_channel(url, key, channel_link) or {}
        raw = _fetch_raw(url, key, raw_id)
        try:
            worker_job_stage_latency_seconds.labels(stage="load_raw", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                max(0.0, time.perf_counter() - t_load0)
            )
        except Exception:
            pass
        if not raw:
            _mark_extraction(url, key, extraction_id, status="failed", error={"error": "raw_missing"}, meta_patch=_with_prompt(
                {"ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link, reason="raw_missing", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version
                ).inc()
            except Exception:
                pass
            return "failed"

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
            return "skipped"

        if bool(raw.get("is_forward")):
            _mark_extraction(url, key, extraction_id, status="skipped", meta_patch=_with_prompt(
                {"reason": "forward", "ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            return "skipped"

        raw_text = str(raw.get("raw_text") or "").strip()
        if not raw_text:
            _mark_extraction(url, key, extraction_id, status="skipped", meta_patch=_with_prompt(
                {"reason": "empty_text", "ts": _utc_now_iso()}), existing_meta=existing_meta, llm_model=llm_model)
            return "skipped"

        normalized_text = normalize_text(raw_text)
        norm_meta = {
            "sha256": _sha256(normalized_text),
            "chars": len(normalized_text),
            "preview": normalized_text[:200] if normalized_text else "",
        }

        is_comp_suspected, comp_details = is_compilation(raw_text)
        compilation_audit: Optional[Dict[str, Any]] = None
        if is_comp_suspected:
            compilation_audit = confirm_compilation_identifiers(raw_message=raw_text, cid=cid, channel=channel_link)

            triggers = [str(t).strip() for t in (comp_details or []) if str(t).strip()]
            triggers_preview = "; ".join(triggers[:3])
            if len(triggers) > 3:
                triggers_preview += f"; (+{len(triggers) - 3} more)"

            log_event(
                logger,
                logging.INFO,
                "compilation_suspected",
                channel=channel_link,
                message_id=message_id,
                raw_id=raw_id,
                triggers=triggers,
                llm_model=compilation_audit.get("llm_model"),
                llm_parse_ok=bool(compilation_audit.get("ok")),
                llm_parse_error=compilation_audit.get("parse_error"),
                llm_raw_sha256=compilation_audit.get("llm_raw_sha256"),
                llm_raw_output=(str(compilation_audit.get("llm_raw_output") or "")[:4000]),
                llm_raw_truncated=bool(compilation_audit.get("llm_raw_truncated"))
                or len(str(compilation_audit.get("llm_raw_output") or "")) > 4000,
                candidates=compilation_audit.get("candidates") or [],
                verified=compilation_audit.get("verified") or [],
                dropped=compilation_audit.get("dropped") or [],
                confirmed=bool(compilation_audit.get("confirmed")),
            )

            _try_report_triage_message(
                kind="compilation",
                raw=raw,
                channel_link=channel_link,
                summary=(
                    f"compilation_suspected: triggers=[{triggers_preview or 'unknown'}]; "
                    f"verified_ids={len(compilation_audit.get('verified') or [])}; "
                    f"candidates={len(compilation_audit.get('candidates') or [])}"
                ),
                stage="compilation_identifiers",
                extracted_codes=[str(c) for c in (compilation_audit.get("verified") or []) if isinstance(c, str) and c],
            )

            # Fail CLOSED: do not proceed with compilation splitting unless >=2 identifiers are verified verbatim.
            if bool(compilation_audit.get("confirmed")):
                ordered = order_verified_identifiers(raw_message=raw_text, verified=list(compilation_audit.get("verified") or []))
                segments = split_compilation_message(raw_message=raw_text, identifiers=ordered)

                results: List[Dict[str, Any]] = []
                any_failed = False
                any_requeueable_persist_fail = False

                for seg in segments:
                    seg_text = str(seg.get("text") or "")
                    seg_code_verbatim = str(seg.get("identifier_verbatim") or "")
                    seg_code_norm = str(seg.get("identifier_normalized") or "") or seg_code_verbatim

                    seg_cid = f"{cid}:comp:{int(seg.get('index') or 0)}"
                    normalized_seg_text = normalize_text(seg_text)

                    # 1) Extract (LLM)
                    try:
                        llm_input = normalized_seg_text if bool(USE_NORMALIZED_TEXT_FOR_LLM) else seg_text
                        model = _llm_model_name()
                        try:
                            worker_llm_requests_total.labels(model=model, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                        except Exception:
                            pass
                        t_llm0 = time.perf_counter()
                        parsed = extract_assignment_with_model(llm_input, chat=channel_link, cid=seg_cid)
                        try:
                            worker_llm_call_latency_seconds.labels(pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(time.perf_counter() - t_llm0)
                            worker_job_stage_latency_seconds.labels(stage="llm", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                                max(0.0, time.perf_counter() - t_llm0)
                            )
                        except Exception:
                            pass
                        if not isinstance(parsed, dict):
                            parsed = {}
                    except Exception as e:
                        any_failed = True
                        try:
                            worker_llm_fail_total.labels(pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                        except Exception:
                            pass
                        results.append({"ok": False, "stage": "llm", "error": str(e), "identifier_verbatim": seg_code_verbatim, "identifier_normalized": seg_code_norm})
                        _try_report_triage_message(
                            kind="extraction_error",
                            raw=raw,
                            channel_link=channel_link,
                            summary=f"compilation_segment_llm_failed: {str(e)[:500]}",
                            stage="llm",
                            extracted_codes=[seg_code_norm],
                        )
                        continue

                    # Force verified identifier downstream (no hallucinated IDs).
                    parsed["assignment_code"] = seg_code_norm

                    payload: Dict[str, Any] = {
                        "cid": seg_cid,
                        "pipeline_version": _V.pipeline_version,
                        "schema_version": _V.schema_version,
                        "channel_link": channel_link,
                        "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
                        "channel_title": ch_info.get("title"),
                        "channel_username": channel_link.replace("t.me/", "") if channel_link.startswith("t.me/") else None,
                        "message_id": raw.get("message_id"),
                        "message_link": _build_message_link(channel_link, str(raw.get("message_id") or "")),
                        "date": raw.get("message_date"),
                        "source_last_seen": raw.get("edit_date") or raw.get("message_date"),
                        "raw_text": seg_text,
                        "parsed": parsed,
                        "meta": {
                            "compilation": {
                                "identifier_verbatim": seg_code_verbatim,
                                "identifier_normalized": seg_code_norm,
                            }
                        },
                    }

                    # 2) Deterministic enrichment (safe, no guessing)
                    postal_estimated_meta: Optional[Dict[str, Any]] = None
                    try:
                        parsed_obj = payload.get("parsed") or {}
                        if isinstance(parsed_obj, dict):
                            parsed_obj = _fill_postal_code_from_text(parsed_obj, seg_text)
                            payload["parsed"] = parsed_obj
                    except Exception:
                        pass

                    if _postal_code_estimated_enabled():
                        try:
                            parsed_obj = payload.get("parsed") or {}
                            if isinstance(parsed_obj, dict):
                                res = estimate_postal_codes(parsed=parsed_obj, raw_text=seg_text)
                                parsed_obj["postal_code_estimated"] = res.estimated
                                payload["parsed"] = parsed_obj
                                postal_estimated_meta = dict(res.meta or {})
                                postal_estimated_meta["estimated"] = res.estimated
                        except Exception as e:
                            postal_estimated_meta = {"ok": False, "error": str(e)}

                    time_meta: Optional[Dict[str, Any]] = None
                    if _deterministic_time_enabled():
                        try:
                            parsed_obj = payload.get("parsed") or {}
                            det_ta, det_meta = extract_time_availability(raw_text=seg_text, normalized_text=normalized_seg_text)
                            if isinstance(parsed_obj, dict):
                                parsed_obj["time_availability"] = det_ta
                                payload["parsed"] = parsed_obj
                            time_meta = {"ok": True}
                            if isinstance(det_meta, dict):
                                time_meta.update(det_meta)
                        except Exception as e:
                            time_meta = {"ok": False, "error": str(e)}

                    hard_meta: Optional[Dict[str, Any]] = None
                    mode = _hard_mode()
                    if mode != "off":
                        try:
                            cleaned, violations = hard_validate(payload.get("parsed") or {}, raw_text=seg_text, normalized_text=normalized_seg_text)
                            hard_meta = {
                                "mode": mode,
                                "violations_count": int(len(violations)),
                                "violations": violations[:50],
                            }
                            if mode == "enforce":
                                payload["parsed"] = cleaned
                        except Exception as e:
                            hard_meta = {"mode": mode, "error": str(e)}

                    signals_meta: Optional[Dict[str, Any]] = None
                    if _signals_enabled():
                        try:
                            signals, err = build_signals(parsed=payload.get("parsed") or {}, raw_text=seg_text, normalized_text=normalized_seg_text)
                            if err:
                                signals_meta = {"ok": False, "error": err}
                            else:
                                signals_meta = {"ok": True, "signals": signals}
                        except Exception as e:
                            signals_meta = {"ok": False, "error": str(e)}

                    ok_schema, schema_errors = validate_parsed_assignment(payload.get("parsed") or {})
                    if not ok_schema:
                        any_failed = True
                        results.append({"ok": False, "stage": "validation", "errors": schema_errors, "identifier_verbatim": seg_code_verbatim, "identifier_normalized": seg_code_norm})
                        _try_report_triage_message(
                            kind="extraction_error",
                            raw=raw,
                            channel_link=channel_link,
                            summary=f"compilation_segment_validation_failed: {str(schema_errors)[:500]}",
                            stage="validation",
                            extracted_codes=[seg_code_norm],
                        )
                        continue

                    persist_res: Dict[str, Any] = {}
                    try:
                        try:
                            worker_supabase_requests_total.labels(operation="persist", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                        except Exception:
                            pass
                        r = persist_assignment_to_supabase(payload)
                        persist_res = r if isinstance(r, dict) else {}
                    except Exception as e:
                        persist_res = {"ok": False, "error": str(e)}

                    if not bool(persist_res.get("ok")):
                        any_failed = True
                        if attempt + 1 < MAX_ATTEMPTS:
                            any_requeueable_persist_fail = True

                    is_insert = bool(persist_res.get("ok")) and str(persist_res.get("action") or "").lower() == "inserted"
                    broadcast_res: Any = None
                    if is_insert and ENABLE_BROADCAST and broadcast_assignments is not None:
                        try:
                            broadcast_assignments.send_broadcast(payload)
                            broadcast_res = {"ok": True}
                        except Exception as e:
                            broadcast_res = {"ok": False, "error": str(e)}

                    dm_res: Any = None
                    if is_insert and ENABLE_DMS and send_dms is not None:
                        try:
                            dm_res = send_dms(payload)
                        except Exception as e:
                            dm_res = {"ok": False, "error": str(e)}

                    results.append(
                        {
                            "ok": bool(persist_res.get("ok")),
                            "identifier_verbatim": seg_code_verbatim,
                            "identifier_normalized": seg_code_norm,
                            "segment_chars": len(seg_text),
                            "persist": persist_res,
                            "broadcast": broadcast_res,
                            "dm": dm_res,
                            "llm_input": "normalized" if bool(USE_NORMALIZED_TEXT_FOR_LLM) else "raw",
                            "postal_code_estimated": postal_estimated_meta,
                            "time_deterministic": time_meta,
                            "hard_validation": hard_meta,
                            "signals": signals_meta,
                        }
                    )

                if any_requeueable_persist_fail:
                    new_attempt = attempt + 1
                    meta_patch = _merge_meta(
                        existing_meta,
                        {
                            "attempt": new_attempt,
                            "reason": "compilation_persist_failed",
                            "compilation": {"triggers": comp_details, "identifiers": compilation_audit, "segments": results},
                        },
                    )
                    _mark_extraction(
                        url,
                        key,
                        extraction_id,
                        status="pending",
                        error={"error": "persist_failed", "details": {"compilation_segments": results}},
                        meta_patch=_with_prompt(meta_patch),
                        existing_meta=existing_meta,
                        llm_model=llm_model,
                    )
                    return "requeued"

                status = "ok" if (segments and not any_failed) else "failed"
                meta = {
                    "ts": _utc_now_iso(),
                    "reason": "compilation_processed",
                    "compilation_details": comp_details,
                    "compilation": {"identifiers": compilation_audit, "segments": results},
                    "normalization": norm_meta,
                }
                _mark_extraction(url, key, extraction_id, status=status, meta_patch=_with_prompt(meta), existing_meta=existing_meta, llm_model=llm_model)
                return status

            log_event(
                logger,
                logging.INFO,
                "compilation_downgraded",
                channel=channel_link,
                message_id=message_id,
                raw_id=raw_id,
                triggers=triggers,
                verified=len(compilation_audit.get("verified") or []),
                decision="non_compilation_path",
            )

        # Check for non-assignment messages (status updates, redirects, administrative posts)
        # before expensive LLM extraction
        is_non, non_type, non_details = is_non_assignment(raw_text)
        if is_non:
            non_meta = detection_meta(is_non, non_type, non_details)
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="skipped",
                meta_patch=_with_prompt({
                    "reason": "non_assignment",
                    "non_assignment_detection": non_meta,
                    "ts": _utc_now_iso(),
                    "normalization": norm_meta,
                }),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            # Report to triage channel if configured
            _try_report_triage_message(
                kind="non_assignment",
                raw=raw,
                channel_link=channel_link,
                summary=f"non_assignment: {non_type} - {non_details}",
                stage="pre_extraction_filter",
            )
            return "skipped"

        # 1) Extract
        try:
            llm_input = normalized_text if bool(USE_NORMALIZED_TEXT_FOR_LLM) else raw_text
            model = _llm_model_name()
            try:
                worker_llm_requests_total.labels(model=model, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
            except Exception:
                pass
            t_llm0 = time.perf_counter()
            
            # Use circuit breaker to prevent queue burn when LLM API is down
            try:
                parsed = llm_circuit_breaker.call(
                    extract_assignment_with_model,
                    llm_input,
                    chat=channel_link,
                    cid=cid
                )
            except CircuitBreakerOpenError as e:
                # Circuit breaker open - fail fast without retrying
                logger.warning(
                    "llm_circuit_breaker_blocked_call",
                    extra={
                        "extraction_id": extraction_id,
                        "channel": channel_link,
                        "circuit_stats": llm_circuit_breaker.get_stats(),
                    }
                )
                raise RuntimeError(f"LLM circuit breaker open: {e}") from e
            
            try:
                worker_llm_call_latency_seconds.labels(pipeline_version=_V.pipeline_version,
                                                       schema_version=_V.schema_version).observe(time.perf_counter() - t_llm0)
                worker_job_stage_latency_seconds.labels(stage="llm", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                    max(0.0, time.perf_counter() - t_llm0)
                )
            except Exception:
                pass
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception as e:
            try:
                worker_llm_fail_total.labels(pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
            except Exception:
                pass
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link,
                    reason=_classify_llm_error(e),
                    pipeline_version=_V.pipeline_version,
                    schema_version=_V.schema_version,
                ).inc()
            except Exception:
                pass
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="failed",
                error={"error": str(e)},
                meta_patch=_with_prompt({"stage": "llm", "ts": _utc_now_iso(), "normalization": norm_meta,
                                        "llm_input": "normalized" if bool(USE_NORMALIZED_TEXT_FOR_LLM) else "raw"}),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            _try_report_triage_message(kind="extraction_error", raw=raw, channel_link=channel_link, summary=str(e), stage="llm")
            return "failed"

        payload: Dict[str, Any] = {
            "cid": cid,
            "pipeline_version": _V.pipeline_version,
            "schema_version": _V.schema_version,
            "channel_link": channel_link,
            "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
            "channel_title": ch_info.get("title"),
            "channel_username": channel_link.replace("t.me/", "") if channel_link.startswith("t.me/") else None,
            "message_id": raw.get("message_id"),
            "message_link": _build_message_link(channel_link, str(raw.get("message_id") or "")),
            # Source publish time (original Telegram message time).
            "date": raw.get("message_date"),
            # Source bump/edit time (when Telegram reports an edit), used for `assignments.source_last_seen`.
            "source_last_seen": raw.get("edit_date") or raw.get("message_date"),
            "raw_text": raw_text,
            "parsed": parsed,
        }

        # 2) Deterministic enrichment (safe, no guessing)
        postal_meta: Optional[Dict[str, Any]] = None
        try:
            parsed_obj = payload.get("parsed") or {}
            if isinstance(parsed_obj, dict):
                before = parsed_obj.get("postal_code")
                parsed_obj = _fill_postal_code_from_text(parsed_obj, raw_text)
                payload["parsed"] = parsed_obj
                after = parsed_obj.get("postal_code")
                postal_meta = {
                    "ok": True,
                    "changed": before != after,
                    "postal_code_count": len(after) if isinstance(after, list) else (1 if isinstance(after, str) and after.strip() else 0),
                }
        except Exception as e:
            postal_meta = {"ok": False, "error": str(e)}

        # 2a) Estimated postal code (best-effort; external Nominatim fallback).
        postal_estimated_meta: Optional[Dict[str, Any]] = None
        if _postal_code_estimated_enabled():
            try:
                parsed_obj = payload.get("parsed") or {}
                if isinstance(parsed_obj, dict):
                    res = estimate_postal_codes(parsed=parsed_obj, raw_text=raw_text)
                    parsed_obj["postal_code_estimated"] = res.estimated
                    payload["parsed"] = parsed_obj
                    postal_estimated_meta = dict(res.meta or {})
                    postal_estimated_meta["estimated"] = res.estimated
            except Exception as e:
                postal_estimated_meta = {"ok": False, "error": str(e)}

        # 2a) Deterministic time_availability (overwrites LLM output when enabled).
        time_meta: Optional[Dict[str, Any]] = None
        if _deterministic_time_enabled():
            try:
                parsed_obj = payload.get("parsed") or {}
                det_ta, det_meta = extract_time_availability(raw_text=raw_text, normalized_text=normalized_text)
                if isinstance(parsed_obj, dict):
                    parsed_obj["time_availability"] = det_ta
                    payload["parsed"] = parsed_obj
                time_meta = {"ok": True}
                if isinstance(det_meta, dict):
                    time_meta.update(det_meta)
            except Exception as e:
                time_meta = {"ok": False, "error": str(e)}

        # 2a) Hard validation (report/enforce; default report; never guesses/fixes)
        hard_meta: Optional[Dict[str, Any]] = None
        mode = _hard_mode()
        if mode != "off":
            try:
                cleaned, violations = hard_validate(payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
                hard_meta = {
                    "mode": mode,
                    "violations_count": int(len(violations)),
                    "violations": violations[:50],
                }
                if mode == "enforce":
                    payload["parsed"] = cleaned
            except Exception as e:
                hard_meta = {"mode": mode, "error": str(e)}

        # 2a.1) Deterministic signals (never breaks the job; stored in meta only)
        signals_meta: Optional[Dict[str, Any]] = None
        if _signals_enabled():
            try:
                signals, err = build_signals(parsed=payload.get("parsed") or {}, raw_text=raw_text, normalized_text=normalized_text)
                if err:
                    signals_meta = {"ok": False, "error": err}
                else:
                    signals_meta = {
                        "ok": True,
                        "signals": signals,
                        "summary": {
                            "subjects": len((signals or {}).get("subjects") or []) if isinstance(signals, dict) else 0,
                            "levels": len((signals or {}).get("levels") or []) if isinstance(signals, dict) else 0,
                            "academic_requests": len((signals or {}).get("academic_requests") or []) if isinstance((signals or {}).get("academic_requests"), list) else 0,
                            "ambiguous": bool(((signals or {}).get("confidence_flags") or {}).get("ambiguous_academic_mapping")) if isinstance(signals, dict) else False,
                        },
                    }
            except Exception as e:
                signals_meta = {"ok": False, "error": str(e)}

        # Make deterministic diagnostics available to downstream side-effects (persist/broadcast/DM),
        # without mutating the stored canonical_json schema.
        payload["meta"] = {
            "normalization": norm_meta,
            "postal_code_fill": postal_meta,
            "postal_code_estimated": postal_estimated_meta,
            "time_deterministic": time_meta,
            "hard_validation": hard_meta,
            "signals": signals_meta,
        }

        # 2b) Contract validation before persistence/broadcast
        t_val0 = time.perf_counter()
        ok_schema, schema_errors = validate_parsed_assignment(payload.get("parsed") or {})
        try:
            worker_job_stage_latency_seconds.labels(stage="validate", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                max(0.0, time.perf_counter() - t_val0)
            )
        except Exception:
            pass
        if not ok_schema:
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link, reason="schema_validation_failed", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version
                ).inc()
            except Exception:
                pass
            _mark_extraction(
                url,
                key,
                extraction_id,
                status="failed",
                error={"error": "validation_failed", "errors": schema_errors},
                meta_patch=_with_prompt(
                    {
                        "stage": "validation",
                        "errors": schema_errors,
                        "ts": _utc_now_iso(),
                        "normalization": norm_meta,
                        "llm_input": "normalized" if bool(USE_NORMALIZED_TEXT_FOR_LLM) else "raw",
                        "postal_code_estimated": postal_estimated_meta,
                        "time_deterministic": time_meta,
                        "hard_validation": hard_meta,
                        "signals": signals_meta,
                    }
                ),
                existing_meta=existing_meta,
                llm_model=llm_model,
            )
            extracted_code = None
            try:
                extracted_code = str((payload.get("parsed") or {}).get("assignment_code") or "").strip()  # type: ignore[union-attr]
            except Exception:
                extracted_code = None
            _try_report_triage_message(
                kind="extraction_error",
                raw=raw,
                channel_link=channel_link,
                summary=f"validation_failed: {str(schema_errors)[:500]}",
                stage="validation",
                extracted_codes=[extracted_code] if extracted_code else None,
            )
            return "failed"

        # 3) Persist assignment row
        persist_res: Dict[str, Any] = {}
        t_persist0 = time.perf_counter()
        try:
            try:
                worker_supabase_requests_total.labels(operation="persist", pipeline_version=_V.pipeline_version,
                                                      schema_version=_V.schema_version).inc()
            except Exception:
                pass
            r = persist_assignment_to_supabase(payload)
            persist_res = r if isinstance(r, dict) else {}
        except Exception as e:
            persist_res = {"ok": False, "error": str(e)}
        try:
            worker_supabase_latency_seconds.labels(operation="persist", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                max(0.0, time.perf_counter() - t_persist0)
            )
            worker_job_stage_latency_seconds.labels(stage="persist", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(
                max(0.0, time.perf_counter() - t_persist0)
            )
        except Exception:
            pass

        # Retry path for transient Supabase failures: requeue if attempts remain.
        if not bool(persist_res.get("ok")) and attempt + 1 < MAX_ATTEMPTS:
            try:
                worker_supabase_fail_total.labels(operation="persist", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
            except Exception:
                pass
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link, reason="supabase_persist_failed", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version
                ).inc()
            except Exception:
                pass
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
            return "requeued"

        # 4) Broadcast/DM (best-effort)
        #
        # Only do side-effects for newly inserted assignments to avoid duplicate posts on
        # reprocesses and Telegram edits (which can enqueue the same message again).
        is_insert = bool(persist_res.get("ok")) and str(persist_res.get("action") or "").lower() == "inserted"

        broadcast_res: Any = None
        if is_insert and ENABLE_BROADCAST and broadcast_assignments is not None:
            try:
                broadcast_assignments.send_broadcast(payload)
                broadcast_res = {"ok": True}
            except Exception as e:
                broadcast_res = {"ok": False, "error": str(e)}

        dm_res: Any = None
        if is_insert and ENABLE_DMS and send_dms is not None:
            try:
                dm_res = send_dms(payload)
            except Exception as e:
                dm_res = {"ok": False, "error": str(e)}

        meta = {
            "ts": _utc_now_iso(),
            "persist": persist_res,
            "broadcast": broadcast_res,
            "dm": dm_res,
            "normalization": norm_meta,
            "compilation_suspected": compilation_audit if compilation_audit else None,
            "llm_input": "normalized" if bool(USE_NORMALIZED_TEXT_FOR_LLM) else "raw",
            "postal_code_estimated": postal_estimated_meta,
            "time_deterministic": time_meta,
            "hard_validation": hard_meta,
            "signals": signals_meta,
        }

        ok = bool(persist_res.get("ok"))
        _mark_extraction(url, key, extraction_id, status="ok" if ok else "failed", canonical_json=payload.get(
            "parsed"), meta_patch=_with_prompt(meta), existing_meta=existing_meta, llm_model=llm_model)
        try:
            sigs = None
            if isinstance(signals_meta, dict) and isinstance(signals_meta.get("signals"), dict):
                sigs = signals_meta.get("signals")
            _quality_checks(parsed=payload.get("parsed") or {}, signals=sigs, channel=channel_link)
        except Exception:
            pass
        if not ok:
            try:
                worker_supabase_fail_total.labels(operation="persist", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
            except Exception:
                pass
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link, reason="supabase_persist_failed_final", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version
                ).inc()
            except Exception:
                pass
            _try_report_triage_message(
                kind="extraction_error",
                raw=raw,
                channel_link=channel_link,
                summary=f"persist_failed_final: {json.dumps(persist_res, ensure_ascii=False)[:500]}",
                stage="persist",
            )
        else:
            try:
                worker_parse_success_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
            except Exception:
                pass
        return "ok" if ok else "failed"


def main() -> None:
    url, key = _supabase_cfg()

    def _dep_health() -> tuple[bool, Dict[str, Any]]:
        try:
            h = dict(_headers(key))
            h["prefer"] = "count=exact"
            resp = requests.get(f"{url}/rest/v1/telegram_extractions?select=id&limit=1", headers=h, timeout=5)
            return (resp.status_code < 400), {"status_code": resp.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    start_observability_http_server(
        port=9002,
        component="worker",
        health_handlers={
            "/health/worker": lambda: (True, {"pipeline_version": _V.pipeline_version, "schema_version": _V.schema_version}),
            "/health/dependencies": _dep_health,
        },
    )

    cfg = _cfg()

    # Optional: Auto-sync broadcast channels on startup
    sync_on_startup = bool(cfg.broadcast_sync_on_startup)
    if sync_on_startup:
        try:
            log_event(logger, logging.INFO, "broadcast_sync_startup_begin")
            # Dynamic import to avoid dependency issues
            from sync_broadcast_channel import sync_channel, _parse_chat_ids, _get_bot_token
            chat_ids = _parse_chat_ids()
            token = _get_bot_token()
            if chat_ids and token:
                for chat_id in chat_ids:
                    try:
                        stats = sync_channel(chat_id, token, dry_run=False, delete_only=False, post_only=False)
                        log_event(logger, logging.INFO, "broadcast_sync_startup_complete", chat_id=chat_id, **stats)
                    except Exception as e:
                        log_event(logger, logging.WARNING, "broadcast_sync_startup_failed", chat_id=chat_id, error=str(e))
            else:
                log_event(logger, logging.WARNING, "broadcast_sync_startup_skipped", reason="no_config")
        except Exception as e:
            log_event(logger, logging.WARNING, "broadcast_sync_startup_error", error=str(e))

    pipeline_version = str(cfg.extraction_pipeline_version or DEFAULT_PIPELINE_VERSION).strip() or DEFAULT_PIPELINE_VERSION
    claim_batch_size = int(cfg.extraction_worker_batch_size or DEFAULT_CLAIM_BATCH_SIZE)
    idle_sleep_s = float(cfg.extraction_worker_idle_s or DEFAULT_IDLE_SLEEP_SECONDS)
    max_attempts = int(cfg.extraction_max_attempts or DEFAULT_MAX_ATTEMPTS)
    backoff_base_s = float(cfg.extraction_backoff_base_s or DEFAULT_BACKOFF_BASE_S)
    backoff_max_s = float(cfg.extraction_backoff_max_s or DEFAULT_BACKOFF_MAX_S)
    stale_processing_s = int(cfg.extraction_stale_processing_seconds or DEFAULT_STALE_PROCESSING_SECONDS)

    enable_broadcast = bool(cfg.enable_broadcast)
    enable_dms = bool(cfg.enable_dms)
    use_norm = bool(cfg.use_normalized_text_for_llm)
    hard_mode = str(cfg.hard_validate_mode or DEFAULT_HARD_VALIDATE_MODE).strip() or DEFAULT_HARD_VALIDATE_MODE
    enable_signals = bool(cfg.enable_deterministic_signals)
    use_det_time = bool(cfg.use_deterministic_time)

    oneshot = bool(cfg.extraction_worker_oneshot)
    max_jobs = int(cfg.extraction_worker_max_jobs or 0)
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
        stale_processing_s=stale_processing_s,
        use_normalized_text_for_llm=bool(use_norm),
        hard_validate_mode=(hard_mode or DEFAULT_HARD_VALIDATE_MODE),
        enable_deterministic_signals=bool(enable_signals),
        use_deterministic_time=bool(use_det_time),
        oneshot=oneshot,
        max_jobs=max_jobs or None,
    )

    global ENABLE_BROADCAST, ENABLE_DMS, MAX_ATTEMPTS, BACKOFF_BASE_S, BACKOFF_MAX_S, STALE_PROCESSING_SECONDS, USE_NORMALIZED_TEXT_FOR_LLM, HARD_VALIDATE_MODE, ENABLE_DETERMINISTIC_SIGNALS, USE_DETERMINISTIC_TIME, ENABLE_POSTAL_CODE_ESTIMATED
    ENABLE_BROADCAST = enable_broadcast
    ENABLE_DMS = enable_dms
    MAX_ATTEMPTS = max(1, int(max_attempts))
    BACKOFF_BASE_S = max(0.0, float(backoff_base_s))
    BACKOFF_MAX_S = max(BACKOFF_BASE_S, float(backoff_max_s)) if backoff_max_s > 0 else DEFAULT_BACKOFF_MAX_S
    STALE_PROCESSING_SECONDS = max(60, int(stale_processing_s))
    USE_NORMALIZED_TEXT_FOR_LLM = bool(use_norm)
    HARD_VALIDATE_MODE = (hard_mode or DEFAULT_HARD_VALIDATE_MODE).strip()
    ENABLE_DETERMINISTIC_SIGNALS = bool(enable_signals)
    USE_DETERMINISTIC_TIME = bool(use_det_time)
    ENABLE_POSTAL_CODE_ESTIMATED = _postal_code_estimated_enabled()
    last_requeue = 0.0
    processed = 0
    last_metrics = 0.0

    while True:
        try:
            now = time.time()
            if now - last_requeue >= max(30, STALE_PROCESSING_SECONDS // 3):
                requeued = _requeue_stale_processing(url, key, older_than_s=STALE_PROCESSING_SECONDS)
                if requeued:
                    log_event(logger, logging.INFO, "requeued_stale_jobs", count=requeued, older_than_s=STALE_PROCESSING_SECONDS)
                    try:
                        worker_requeued_stale_jobs_total.labels(pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc(requeued)
                    except Exception:
                        pass
                last_requeue = now

            if now - last_metrics >= 15.0:
                try:
                    counts = _queue_counts(url, key, ["pending", "processing", "ok", "failed"])
                    pv = _V.pipeline_version
                    sv = _V.schema_version
                    queue_pending.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("pending") or 0))
                    queue_processing.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("processing") or 0))
                    queue_ok.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("ok") or 0))
                    queue_failed.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("failed") or 0))
                    oldest_pending = _oldest_created_age_s(url, key, "pending")
                    oldest_processing = _oldest_created_age_s(url, key, "processing")
                    queue_oldest_pending_age_seconds.labels(pipeline_version=pv, schema_version=sv).set(float(oldest_pending or 0.0))
                    queue_oldest_processing_age_seconds.labels(pipeline_version=pv, schema_version=sv).set(float(oldest_processing or 0.0))
                except Exception:
                    logger.debug("queue_metrics_update_failed", exc_info=True)
                last_metrics = now

            jobs = _rpc(
                url,
                key,
                "claim_telegram_extractions",
                {"p_pipeline_version": pipeline_version, "p_limit": int(max(1, claim_batch_size))},
                timeout=30,
            )
            if not isinstance(jobs, list) or not jobs:
                if oneshot:
                    log_event(logger, logging.INFO, "worker_oneshot_done", processed=processed, pipeline_version=pipeline_version)
                    return

                time.sleep(max(0.25, float(idle_sleep_s)))
                continue

            log_event(logger, logging.INFO, "claimed_jobs", count=len(jobs), pipeline_version=pipeline_version)
            for job in jobs:
                if isinstance(job, dict):
                    extraction_id = job.get("id")
                    raw_id = job.get("raw_id")
                    channel_link = str(job.get("channel_link") or "").strip() or "t.me/unknown"
                    message_id = str(job.get("message_id") or "").strip()
                    t0 = time.perf_counter()
                    logger.info(
                        "job_begin extraction_id=%s raw_id=%s channel=%s message_id=%s",
                        extraction_id,
                        raw_id,
                        channel_link,
                        message_id,
                    )
                    try:
                        status = _work_one(url, key, job)
                        processed += 1
                        dt_s = time.perf_counter() - t0
                        dt_ms = int(dt_s * 1000)
                        try:
                            worker_job_latency_seconds.labels(pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(dt_s)
                            worker_jobs_processed_total.labels(status=str(status), pipeline_version=_V.pipeline_version,
                                                               schema_version=_V.schema_version).inc()
                        except Exception:
                            pass
                        logger.info("job_end extraction_id=%s dt_ms=%s", extraction_id, dt_ms)
                    except Exception as e:
                        dt_s = time.perf_counter() - t0
                        dt_ms = int(dt_s * 1000)
                        try:
                            worker_job_latency_seconds.labels(pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).observe(dt_s)
                            worker_jobs_processed_total.labels(status="error", pipeline_version=_V.pipeline_version,
                                                               schema_version=_V.schema_version).inc()
                        except Exception:
                            pass
                        logger.warning("job_error extraction_id=%s dt_ms=%s error=%s", extraction_id, dt_ms, str(e))
                    if max_jobs and processed >= max_jobs:
                        log_event(logger, logging.INFO, "worker_max_jobs_reached", processed=processed,
                                  max_jobs=max_jobs, pipeline_version=pipeline_version)
                        return
        except KeyboardInterrupt:
            log_event(logger, logging.INFO, "worker_interrupted")
            return
        except Exception as e:
            log_event(logger, logging.WARNING, "worker_loop_error", error=str(e))
            time.sleep(2.0)


if __name__ == "__main__":
    main()
