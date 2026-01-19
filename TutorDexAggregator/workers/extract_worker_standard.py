from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, Optional

from extract_key_info import extract_assignment_with_model
from extractors.non_assignment_detector import detection_meta, is_non_assignment
from observability_metrics import (
    worker_job_stage_latency_seconds,
    worker_parse_failure_total,
)
from schema_validation import validate_parsed_assignment
from workers.extract_worker_enrich import enrich_payload
from workers.extract_worker_metrics import llm_metrics
from workers.extract_worker_standard_persist import persist_and_finalize
from workers.extract_worker_store import mark_extraction
from workers.extract_worker_triage import try_report_triage_message
from workers.extract_worker_types import VersionInfo, WorkerToggles
from workers.llm_processor import extract_with_llm
from workers.utils import build_message_link, utc_now_iso
from workers.validation_pipeline import validate_schema


def process_standard_message(
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
    cid: str,
    channel_link: str,
    raw: Dict[str, Any],
    ch_info: Dict[str, Any],
    raw_text: str,
    normalized_text: str,
    norm_meta: Dict[str, Any],
    with_prompt: Callable[[Dict[str, Any]], Dict[str, Any]],
    broadcast_assignments: Any,
    send_dms: Any,
) -> str:
    is_non, non_type, non_details = is_non_assignment(raw_text)
    if is_non:
        non_meta = detection_meta(is_non, non_type, non_details)
        mark_extraction(
            url,
            key,
            extraction_id,
            status="skipped",
            meta_patch=with_prompt(
                {
                    "reason": "non_assignment",
                    "non_assignment_detection": non_meta,
                    "ts": utc_now_iso(),
                    "normalization": norm_meta,
                }
            ),
            existing_meta=existing_meta,
            llm_model=llm_model,
            version=version,
        )
        try_report_triage_message(
            cfg=cfg,
            logger=logger,
            kind="non_assignment",
            raw=raw,
            channel_link=channel_link,
            summary=f"non_assignment: {non_type} - {non_details}",
            stage="pre_extraction_filter",
        )
        return "skipped"

    llm_input = normalized_text if bool(toggles.use_normalized_text_for_llm) else raw_text
    parsed, llm_err, llm_latency = extract_with_llm(
        llm_input,
        channel_link,
        cid=cid,
        circuit_breaker=circuit_breaker,
        extract_func=extract_assignment_with_model,
        metrics=llm_metrics(version),
    )
    try:
        worker_job_stage_latency_seconds.labels(stage="llm", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(
            float(llm_latency)
        )
    except Exception:
        # Metrics must never break runtime
        pass

    if llm_err or not isinstance(parsed, dict):
        try:
            worker_parse_failure_total.labels(
                channel=channel_link,
                reason=str(llm_err or "llm_error"),
                pipeline_version=version.pipeline_version,
                schema_version=version.schema_version,
            ).inc()
        except Exception:
            pass
        mark_extraction(
            url,
            key,
            extraction_id,
            status="failed",
            error={"error": llm_err},
            meta_patch=with_prompt(
                {
                    "stage": "llm",
                    "ts": utc_now_iso(),
                    "normalization": norm_meta,
                    "llm_input": "normalized" if bool(toggles.use_normalized_text_for_llm) else "raw",
                }
            ),
            existing_meta=existing_meta,
            llm_model=llm_model,
            version=version,
        )
        try_report_triage_message(
            cfg=cfg,
            logger=logger,
            kind="extraction_error",
            raw=raw,
            channel_link=channel_link,
            summary=str(llm_err),
            stage="llm",
        )
        return "failed"

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
        "raw_text": raw_text,
        "parsed": parsed,
    }

    postal_estimated_meta, time_meta, hard_meta, signals_meta = enrich_payload(
        payload=payload,
        raw_text=raw_text,
        normalized_text=normalized_text,
        norm_meta=norm_meta,
        toggles=toggles,
    )

    t_val0 = time.perf_counter()
    ok_schema, schema_errors = validate_schema(payload.get("parsed") or {}, validate_parsed_assignment)
    try:
        worker_job_stage_latency_seconds.labels(stage="validate", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(
            max(0.0, time.perf_counter() - t_val0)
        )
    except Exception:
        # Metrics must never break runtime
        pass
    if not ok_schema:
        try:
            worker_parse_failure_total.labels(
                channel=channel_link,
                reason="schema_validation_failed",
                pipeline_version=version.pipeline_version,
                schema_version=version.schema_version,
            ).inc()
        except Exception:
            pass
        mark_extraction(
            url,
            key,
            extraction_id,
            status="failed",
            error={"error": "validation_failed", "errors": schema_errors},
            meta_patch=with_prompt(
                {
                    "stage": "validation",
                    "errors": schema_errors,
                    "ts": utc_now_iso(),
                    "normalization": norm_meta,
                    "llm_input": "normalized" if bool(toggles.use_normalized_text_for_llm) else "raw",
                    "postal_code_estimated": postal_estimated_meta,
                    "time_deterministic": time_meta,
                    "hard_validation": hard_meta,
                    "signals": signals_meta,
                }
            ),
            existing_meta=existing_meta,
            llm_model=llm_model,
            version=version,
        )
        extracted_code = None
        try:
            extracted_code = str((payload.get("parsed") or {}).get("assignment_code") or "").strip()  # type: ignore[union-attr]
        except Exception:
            extracted_code = None
        try_report_triage_message(
            cfg=cfg,
            logger=logger,
            kind="extraction_error",
            raw=raw,
            channel_link=channel_link,
            summary=f"validation_failed: {str(schema_errors)[:500]}",
            stage="validation",
            extracted_codes=[extracted_code] if extracted_code else None,
        )
        return "failed"

    return persist_and_finalize(
        cfg=cfg,
        logger=logger,
        version=version,
        toggles=toggles,
        url=url,
        key=key,
        extraction_id=extraction_id,
        existing_meta=existing_meta,
        attempt=attempt,
        llm_model=llm_model,
        channel_link=channel_link,
        raw=raw,
        payload=payload,
        with_prompt=with_prompt,
        norm_meta=norm_meta,
        postal_estimated_meta=postal_estimated_meta,
        time_meta=time_meta,
        hard_meta=hard_meta,
        signals_meta=signals_meta,
        broadcast_assignments=broadcast_assignments,
        send_dms=send_dms,
    )
