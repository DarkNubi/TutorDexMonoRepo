from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence

from compilation_message_handler import (
    order_verified_identifiers,
    split_compilation_message,
)
from extract_key_info import extract_assignment_with_model
from normalize import normalize_text
from observability_metrics import (
    worker_job_stage_latency_seconds,
    worker_parse_failure_total,
    worker_supabase_latency_seconds,
    worker_supabase_requests_total,
)
from schema_validation import validate_parsed_assignment
from workers.extract_worker_enrich import enrich_payload
from workers.extract_worker_metrics import llm_metrics
from workers.extract_worker_store import mark_extraction
from workers.extract_worker_triage import try_report_triage_message
from workers.extract_worker_types import VersionInfo, WorkerToggles
from workers.llm_processor import extract_with_llm
from workers.utils import build_message_link, sha256_hash, utc_now_iso
from workers.validation_pipeline import validate_schema


def process_compilation_confirmed(
    *,
    cfg: Any,
    logger: logging.Logger,
    version: VersionInfo,
    toggles: WorkerToggles,
    circuit_breaker: Any,
    url: str,
    key: str,
    extraction_id: Any,
    existing_meta: Any,
    attempt: int,
    llm_model: Optional[str],
    channel_link: str,
    message_id: str,
    raw_id: Any,
    cid: str,
    raw: Dict[str, Any],
    ch_info: Dict[str, Any],
    raw_text: str,
    norm_meta: Dict[str, Any],
    compilation_audit: Dict[str, Any],
    comp_details: Sequence[Any],
    with_prompt: Callable[[Dict[str, Any]], Dict[str, Any]],
    broadcast_assignments: Any,
    send_dms: Any,
) -> str:
    ordered = order_verified_identifiers(raw_message=raw_text, verified=list(compilation_audit.get("verified") or []))
    segments = split_compilation_message(raw_message=raw_text, identifiers=ordered)
    results: List[Dict[str, Any]] = []
    any_failed = False
    any_requeueable_persist_fail = False

    for seg_code_verbatim, seg_text in segments:
        seg_code_norm = str(seg_code_verbatim or "").strip().upper()
        normalized_seg_text = normalize_text(seg_text)

        llm_input = normalized_seg_text if bool(toggles.use_normalized_text_for_llm) else seg_text
        parsed, llm_err, lat = extract_with_llm(
            llm_input,
            channel_link,
            cid=f"{cid}:seg:{seg_code_norm}",
            circuit_breaker=circuit_breaker,
            extract_func=extract_assignment_with_model,
            metrics=llm_metrics(version),
        )
        try:
            worker_job_stage_latency_seconds.labels(stage="llm", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(
                float(lat)
            )
        except Exception:
            # Metrics must never break runtime
            pass

        if llm_err or not isinstance(parsed, dict):
            any_failed = True
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link,
                    reason=str(llm_err or "llm_error"),
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
                summary=f"compilation_segment_llm_failed: {llm_err}",
                stage="compilation_llm",
                extracted_codes=[seg_code_norm] if seg_code_norm else None,
            )
            results.append(
                {
                    "ok": False,
                    "identifier_verbatim": seg_code_verbatim,
                    "identifier_normalized": seg_code_norm,
                    "segment_chars": len(seg_text),
                    "llm_error": llm_err,
                }
            )
            continue

        payload: Dict[str, Any] = {
            "cid": cid,
            "pipeline_version": version.pipeline_version,
            "schema_version": version.schema_version,
            "channel_link": channel_link,
            "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
            "channel_title": ch_info.get("title"),
            "channel_username": channel_link.replace("t.me/", "") if channel_link.startswith("t.me/") else None,
            "message_id": raw.get("message_id"),
            "message_link": build_message_link(channel_link, str(raw.get("message_id") or "")),
            "date": raw.get("message_date"),
            "source_last_seen": raw.get("edit_date") or raw.get("message_date"),
            "raw_text": seg_text,
            "parsed": parsed,
            "meta": {"compilation": {"identifier_verbatim": seg_code_verbatim, "identifier_normalized": seg_code_norm}},
        }

        postal_estimated_meta, time_meta, hard_meta, signals_meta = enrich_payload(
            payload=payload,
            raw_text=seg_text,
            normalized_text=normalized_seg_text,
            norm_meta={
                "sha256": sha256_hash(normalized_seg_text),
                "chars": len(normalized_seg_text),
                "preview": normalized_seg_text[:200] if normalized_seg_text else "",
            },
            toggles=toggles,
        )

        ok_schema, schema_errors = validate_schema(payload.get("parsed") or {}, validate_parsed_assignment)
        if not ok_schema:
            any_failed = True
            try:
                worker_parse_failure_total.labels(
                    channel=channel_link,
                    reason="schema_validation_failed",
                    pipeline_version=version.pipeline_version,
                    schema_version=version.schema_version,
                ).inc()
            except Exception:
                # Metrics must never break runtime
                pass
            try_report_triage_message(
                cfg=cfg,
                logger=logger,
                kind="extraction_error",
                raw=raw,
                channel_link=channel_link,
                summary=f"compilation_segment_validation_failed: {str(schema_errors)[:500]}",
                stage="compilation_validation",
                extracted_codes=[seg_code_norm] if seg_code_norm else None,
            )
            results.append(
                {
                    "ok": False,
                    "identifier_verbatim": seg_code_verbatim,
                    "identifier_normalized": seg_code_norm,
                    "segment_chars": len(seg_text),
                    "validation_errors": schema_errors,
                    "llm_input": "normalized" if bool(toggles.use_normalized_text_for_llm) else "raw",
                    "postal_code_estimated": postal_estimated_meta,
                    "time_deterministic": time_meta,
                    "hard_validation": hard_meta,
                    "signals": signals_meta,
                }
            )
            continue

        try:
            worker_supabase_requests_total.labels(operation="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).inc()
        except Exception:
            # Metrics must never break runtime
            pass
        t_persist0 = time.perf_counter()
        try:
            from supabase_persist import persist_assignment_to_supabase

            persist_res = persist_assignment_to_supabase(payload)
            persist_res = persist_res if isinstance(persist_res, dict) else {}
        except Exception as e:
            persist_res = {"ok": False, "error": str(e)}
        try:
            dt = max(0.0, time.perf_counter() - t_persist0)
            worker_supabase_latency_seconds.labels(operation="persist", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(dt)
        except Exception:
            pass

        ok_persist = bool(persist_res.get("ok"))
        is_insert = ok_persist and str(persist_res.get("action") or "").lower() == "inserted"

        broadcast_res: Any = None
        if is_insert and toggles.enable_broadcast and broadcast_assignments is not None:
            try:
                broadcast_res = broadcast_assignments.broadcast_single_assignment(payload)
            except Exception as e:
                broadcast_res = {"ok": False, "error": str(e)}

        dm_res: Any = None
        if is_insert and toggles.enable_dms and send_dms is not None:
            try:
                dm_res = send_dms(payload)
            except Exception as e:
                dm_res = {"ok": False, "error": str(e)}

        if (not ok_persist) and (attempt + 1 < int(toggles.max_attempts or 0)):
            any_requeueable_persist_fail = True

        results.append(
            {
                "ok": ok_persist,
                "identifier_verbatim": seg_code_verbatim,
                "identifier_normalized": seg_code_norm,
                "segment_chars": len(seg_text),
                "persist": persist_res,
                "broadcast": broadcast_res,
                "dm": dm_res,
                "llm_input": "normalized" if bool(toggles.use_normalized_text_for_llm) else "raw",
                "postal_code_estimated": postal_estimated_meta,
                "time_deterministic": time_meta,
                "hard_validation": hard_meta,
                "signals": signals_meta,
            }
        )

    if any_requeueable_persist_fail:
        meta_patch = {
            "attempt": int(attempt) + 1,
            "reason": "compilation_persist_failed",
            "compilation": {"triggers": list(comp_details or []), "identifiers": compilation_audit, "segments": results},
        }
        mark_extraction(
            url,
            key,
            extraction_id,
            status="pending",
            error={"error": "persist_failed", "details": {"compilation_segments": results}},
            meta_patch=with_prompt(meta_patch),
            existing_meta=existing_meta,
            llm_model=llm_model,
            version=version,
        )
        return "requeued"

    status = "ok" if (segments and not any_failed) else "failed"
    meta = {
        "ts": utc_now_iso(),
        "reason": "compilation_processed",
        "compilation_details": list(comp_details or []),
        "compilation": {"identifiers": compilation_audit, "segments": results},
        "normalization": norm_meta,
    }
    mark_extraction(url, key, extraction_id, status=status, meta_patch=with_prompt(meta), existing_meta=existing_meta, llm_model=llm_model, version=version)
    if status != "ok":
        try_report_triage_message(
            cfg=cfg,
            logger=logger,
            kind="extraction_error",
            raw=raw,
            channel_link=channel_link,
            summary=f"compilation_failed: {json.dumps(results, ensure_ascii=False)[:500]}",
            stage="compilation",
        )
    return status
