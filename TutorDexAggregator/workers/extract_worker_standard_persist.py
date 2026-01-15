from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, Optional, Tuple

from observability_metrics import (
    worker_job_stage_latency_seconds,
    worker_parse_failure_total,
    worker_parse_success_total,
    worker_supabase_fail_total,
    worker_supabase_latency_seconds,
    worker_supabase_requests_total,
)
from workers.extract_worker_metrics import quality_metrics
from workers.extract_worker_store import mark_extraction
from workers.extract_worker_triage import try_report_triage_message
from workers.extract_worker_types import VersionInfo, WorkerToggles
from workers.utils import utc_now_iso
from workers.validation_pipeline import run_quality_checks


def persist_and_finalize(
    *,
    cfg: Any,
    logger: logging.Logger,
    version: VersionInfo,
    toggles: WorkerToggles,
    url: str,
    key: str,
    extraction_id: Any,
    existing_meta: Any,
    attempt: int,
    llm_model: Optional[str],
    channel_link: str,
    raw: Dict[str, Any],
    payload: Dict[str, Any],
    with_prompt: Callable[[Dict[str, Any]], Dict[str, Any]],
    norm_meta: Dict[str, Any],
    postal_estimated_meta: Any,
    time_meta: Any,
    hard_meta: Any,
    signals_meta: Any,
    broadcast_assignments: Any,
    send_dms: Any,
) -> str:
    persist_res: Dict[str, Any] = {}
    t_persist0 = time.perf_counter()
    try:
        try:
            worker_supabase_requests_total.labels(operation="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).inc()
        except Exception:
            pass
        from supabase_persist import persist_assignment_to_supabase

        r = persist_assignment_to_supabase(payload)
        persist_res = r if isinstance(r, dict) else {}
    except Exception as e:
        persist_res = {"ok": False, "error": str(e)}
    try:
        dt = max(0.0, time.perf_counter() - t_persist0)
        worker_supabase_latency_seconds.labels(operation="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(dt)
        worker_job_stage_latency_seconds.labels(stage="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(dt)
    except Exception:
        pass

    if (not bool(persist_res.get("ok"))) and (attempt + 1 < int(toggles.max_attempts or 0)):
        try:
            worker_supabase_fail_total.labels(operation="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).inc()
        except Exception:
            pass
        try:
            worker_parse_failure_total.labels(
                channel=channel_link,
                reason="supabase_persist_failed",
                pipeline_version=version.pipeline_version,
                schema_version=version.schema_version,
            ).inc()
        except Exception:
            pass
        meta_patch = {"attempt": attempt + 1, "persist_error": persist_res}
        mark_extraction(
            url,
            key,
            extraction_id,
            status="pending",
            error={"error": "persist_failed", "details": persist_res},
            meta_patch=with_prompt(meta_patch),
            existing_meta=existing_meta,
            llm_model=llm_model,
            version=version,
        )
        return "requeued"

    is_insert = bool(persist_res.get("ok")) and str(persist_res.get("action") or "").lower() == "inserted"

    broadcast_res: Any = None
    if is_insert and toggles.enable_broadcast and broadcast_assignments is not None:
        try:
            broadcast_assignments.send_broadcast(payload)
            broadcast_res = {"ok": True}
        except Exception as e:
            broadcast_res = {"ok": False, "error": str(e)}

    dm_res: Any = None
    if is_insert and toggles.enable_dms and send_dms is not None:
        try:
            dm_res = send_dms(payload)
        except Exception as e:
            dm_res = {"ok": False, "error": str(e)}

    meta = {
        "ts": utc_now_iso(),
        "persist": persist_res,
        "broadcast": broadcast_res,
        "dm": dm_res,
        "normalization": norm_meta,
        "llm_input": "normalized" if bool(toggles.use_normalized_text_for_llm) else "raw",
        "postal_code_estimated": postal_estimated_meta,
        "time_deterministic": time_meta,
        "hard_validation": hard_meta,
        "signals": signals_meta,
    }

    ok = bool(persist_res.get("ok"))
    mark_extraction(
        url,
        key,
        extraction_id,
        status="ok" if ok else "failed",
        canonical_json=payload.get("parsed"),
        meta_patch=with_prompt(meta),
        existing_meta=existing_meta,
        llm_model=llm_model,
        version=version,
    )

    try:
        sigs = None
        if isinstance(signals_meta, dict) and isinstance(signals_meta.get("signals"), dict):
            sigs = signals_meta.get("signals")
        run_quality_checks(payload.get("parsed") or {}, sigs, channel_link, quality_metrics(version))
    except Exception:
        pass

    if not ok:
        try:
            worker_supabase_fail_total.labels(operation="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).inc()
        except Exception:
            pass
        try:
            worker_parse_failure_total.labels(
                channel=channel_link,
                reason="supabase_persist_failed_final",
                pipeline_version=version.pipeline_version,
                schema_version=version.schema_version,
            ).inc()
        except Exception:
            pass
        try_report_triage_message(
            cfg=cfg,
            logger=logger,
            kind="extraction_error",
            raw=raw,
            channel_link=channel_link,
            summary=f"persist_failed_final: {json.dumps(persist_res, ensure_ascii=False)[:500]}",
            stage="persist",
        )
    else:
        try:
            worker_parse_success_total.labels(channel=channel_link, pipeline_version=version.pipeline_version, schema_version=version.schema_version).inc()
        except Exception:
            pass

    return "ok" if ok else "failed"

