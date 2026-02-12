from __future__ import annotations

import logging
import time
import traceback
from typing import Any, Dict

from compilation_detection import is_compilation
from compilation_message_handler import confirm_compilation_identifiers
from extract_key_info import get_examples_meta, get_system_prompt_meta
from logging_setup import bind_log_context, log_event
from normalize import normalize_text
from observability_metrics import (
    worker_job_stage_latency_seconds,
    worker_parse_failure_total,
)
from supabase_persist import mark_assignment_closed
from workers.extract_worker_compilation import process_compilation_confirmed
from workers.extract_worker_standard import process_standard_message
from workers.extract_worker_store import channel_info_cached, mark_extraction
from workers.extract_worker_triage import try_report_triage_message
from workers.extract_worker_types import VersionInfo, WorkerToggles
from workers.job_manager import get_job_attempt
from workers.llm_processor import get_examples_metadata, get_llm_model_name, get_prompt_metadata
from workers.message_processor import filter_message, load_raw_message
from workers.utils import sha256_hash, utc_now_iso


def work_one(
    *,
    cfg: Any,
    logger: logging.Logger,
    version: VersionInfo,
    toggles: WorkerToggles,
    circuit_breaker: Any,
    channel_cache: Dict[str, Dict[str, Any]],
    url: str,
    key: str,
    job: Dict[str, Any],
    broadcast_assignments: Any,
    send_dms: Any,
) -> str:
    extraction_id = job.get("id")
    raw_id = job.get("raw_id")
    channel_link = str(job.get("channel_link") or "").strip() or "t.me/unknown"
    message_id = str(job.get("message_id") or "").strip()
    cid = f"worker:{channel_link}:{message_id}:{extraction_id}"
    existing_meta = job.get("meta")

    llm_model = str(getattr(cfg, "llm_model_name", "") or "").strip() or None
    if not llm_model:
        m = get_llm_model_name()
        llm_model = None if m == "unknown" else m

    prompt_meta = get_prompt_metadata(get_system_prompt_meta)
    examples_meta = get_examples_metadata(get_examples_meta, channel_link)

    def _with_prompt(meta_patch: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(meta_patch)
        if prompt_meta is not None:
            out["prompt"] = prompt_meta
        if examples_meta is not None:
            out["examples"] = examples_meta
        return out

    def _run() -> str:
        attempt = int(get_job_attempt(job))
        if attempt >= int(toggles.max_attempts or 0):
            last_error = job.get("error_json")
            if not isinstance(last_error, dict):
                last_error = None

            # Preserve the last known error for diagnostics. "max_attempts" is a terminal condition,
            # but overwriting the error_json makes downstream analytics lose the real failure cause.
            error_payload: Dict[str, Any] = {"error": "max_attempts", "attempt": attempt}
            if last_error:
                error_payload = dict(last_error)
                error_payload["attempt"] = attempt
                error_payload["final_error"] = "max_attempts"

            try:
                worker_parse_failure_total.labels(
                    channel=channel_link,
                    reason="max_attempts",
                    pipeline_version=version.pipeline_version,
                    schema_version=version.schema_version,
                ).inc()
            except Exception:
                # Metrics must never break runtime
                pass
            mark_extraction(
                url,
                key,
                extraction_id,
                status="failed",
                error=error_payload,
                meta_patch=_with_prompt({"reason": "max_attempts", "ts": utc_now_iso()}),
                existing_meta=existing_meta,
                llm_model=llm_model,
                version=version,
            )
            return "failed"

        if attempt > 1 and float(toggles.backoff_base_s or 0) > 0:
            delay = min(float(toggles.backoff_max_s or 0), float(toggles.backoff_base_s or 0) * (2 ** max(0, attempt - 1)))
            time.sleep(delay)

        with bind_log_context(
            cid=cid,
            channel=channel_link,
            message_id=message_id,
            assignment_id=str(extraction_id) if extraction_id is not None else None,
            step="worker.process",
            component="worker",
            pipeline_version=version.pipeline_version,
            schema_version=version.schema_version,
        ):
            t_load0 = time.perf_counter()
            ch_info = channel_info_cached(channel_cache=channel_cache, url=url, key=key, channel_link=channel_link, version=version)
            raw = load_raw_message(url, key, raw_id, pipeline_version=version.pipeline_version, schema_version=version.schema_version)
            try:
                worker_job_stage_latency_seconds.labels(stage="load_raw", pipeline_version=version.pipeline_version, schema_version=version.schema_version).observe(
                    max(0.0, time.perf_counter() - t_load0)
                )
            except Exception:
                # Metrics must never break runtime
                pass

            if not raw:
                mark_extraction(
                    url,
                    key,
                    extraction_id,
                    status="failed",
                    error={"error": "raw_missing"},
                    meta_patch=_with_prompt({"ts": utc_now_iso()}),
                    existing_meta=existing_meta,
                    llm_model=llm_model,
                    version=version,
                )
                try:
                    worker_parse_failure_total.labels(
                        channel=channel_link,
                        reason="raw_missing",
                        pipeline_version=version.pipeline_version,
                        schema_version=version.schema_version,
                    ).inc()
                except Exception:
                    pass
                return "failed"

            filter_res = filter_message(raw, channel_link, ch_info)
            if filter_res.should_skip:
                meta: Dict[str, Any] = {"reason": filter_res.reason, "ts": utc_now_iso()}
                if filter_res.reason == "deleted":
                    try:
                        close_payload = filter_res.close_payload or {}
                        close_res = mark_assignment_closed(close_payload)
                    except Exception:
                        close_res = None
                    meta["close_res"] = close_res
                elif filter_res.reason == "reply":
                    # Bump the parent assignment instead of processing the reply
                    try:
                        from reply_bump import bump_assignment_from_reply

                        message_json = raw.get("message_json") or {}
                        reply_to_msg_id = message_json.get("reply_to_msg_id")

                        if reply_to_msg_id:
                            bump_res = bump_assignment_from_reply(
                                channel_link=channel_link,
                                reply_to_msg_id=str(reply_to_msg_id),
                                supabase_url=url,
                                supabase_key=key,
                            )
                            meta["bump_res"] = bump_res
                            log_event(
                                logger,
                                logging.INFO,
                                "reply_message_bumped_parent",
                                extraction_id=extraction_id,
                                channel_link=channel_link,
                                message_id=raw.get("message_id"),
                                reply_to_msg_id=reply_to_msg_id,
                                bump_result=bump_res,
                            )
                        else:
                            meta["bump_res"] = {"ok": False, "reason": "No reply_to_msg_id in message_json"}
                    except Exception as e:
                        meta["bump_res"] = {"ok": False, "error": str(e)}
                        log_event(
                            logger,
                            logging.ERROR,
                            "reply_bump_failed",
                            extraction_id=extraction_id,
                            error=str(e),
                        )
                mark_extraction(
                    url,
                    key,
                    extraction_id,
                    status="skipped",
                    meta_patch=_with_prompt(meta),
                    existing_meta=existing_meta,
                    llm_model=llm_model,
                    version=version,
                )
                return "skipped"

            raw_text = str(raw.get("raw_text") or "").strip()
            normalized_text = normalize_text(raw_text)
            norm_meta = {
                "sha256": sha256_hash(normalized_text),
                "chars": len(normalized_text),
                "preview": normalized_text[:200] if normalized_text else "",
            }

            is_comp_suspected, comp_details = is_compilation(raw_text)
            if is_comp_suspected:
                compilation_audit = confirm_compilation_identifiers(raw_message=raw_text, cid=cid, channel=channel_link)

                triggers = [str(t).strip() for t in (comp_details or []) if str(t).strip()]
                triggers_preview = "; ".join(triggers[:6]) if triggers else ""

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

                try_report_triage_message(
                    cfg=cfg,
                    logger=logger,
                    kind="compilation",
                    raw=raw,
                    channel_link=channel_link,
                    summary=(
                        f"compilation_suspected: triggers=[{triggers_preview or 'unknown'}]; "
                        f"verified_ids={len(compilation_audit.get('verified') or [])}; "
                        f"candidates={len(compilation_audit.get('candidates') or [])}"
                    ),
                    stage="compilation_identifiers",
                    extracted_codes=[str(c) for c in (compilation_audit.get('verified') or []) if isinstance(c, str) and c],
                )

                if bool(compilation_audit.get("confirmed")):
                    return process_compilation_confirmed(
                        cfg=cfg,
                        logger=logger,
                        version=version,
                        toggles=toggles,
                        circuit_breaker=circuit_breaker,
                        url=url,
                        key=key,
                        extraction_id=extraction_id,
                        existing_meta=existing_meta,
                        attempt=attempt,
                        llm_model=llm_model,
                        channel_link=channel_link,
                        message_id=message_id,
                        raw_id=raw_id,
                        cid=cid,
                        raw=raw,
                        ch_info=ch_info,
                        raw_text=raw_text,
                        norm_meta=norm_meta,
                        compilation_audit=compilation_audit,
                        comp_details=comp_details or [],
                        with_prompt=_with_prompt,
                        broadcast_assignments=broadcast_assignments,
                        send_dms=send_dms,
                    )

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

            return process_standard_message(
                cfg=cfg,
                logger=logger,
                version=version,
                toggles=toggles,
                circuit_breaker=circuit_breaker,
                url=url,
                key=key,
                extraction_id=extraction_id,
                existing_meta=existing_meta,
                attempt=attempt,
                llm_model=llm_model,
                cid=cid,
                channel_link=channel_link,
                raw=raw,
                ch_info=ch_info,
                raw_text=raw_text,
                normalized_text=normalized_text,
                norm_meta=norm_meta,
                with_prompt=_with_prompt,
                broadcast_assignments=broadcast_assignments,
                send_dms=send_dms,
            )

    try:
        return _run()
    except Exception as e:
        tb = traceback.format_exc()
        log_event(
            logger,
            logging.ERROR,
            "work_one_unhandled_exception",
            extraction_id=extraction_id,
            raw_id=raw_id,
            channel_link=channel_link,
            message_id=message_id,
            error_type=type(e).__name__,
            error=str(e),
            traceback=(tb[-3500:] if tb else None),
        )
        try:
            worker_parse_failure_total.labels(
                channel=channel_link,
                reason=f"exception:{type(e).__name__}",
                pipeline_version=version.pipeline_version,
                schema_version=version.schema_version,
            ).inc()
        except Exception:
            pass
        try:
            mark_extraction(
                url,
                key,
                extraction_id,
                status="failed",
                error={"error": "unhandled_exception", "type": type(e).__name__, "detail": str(e)},
                meta_patch=_with_prompt({"stage": "exception", "ts": utc_now_iso()}),
                existing_meta=existing_meta,
                llm_model=llm_model,
                version=version,
            )
        except Exception:
            logger.debug("mark_extraction_failed_unhandled_exception", exc_info=True)
        return "failed"
