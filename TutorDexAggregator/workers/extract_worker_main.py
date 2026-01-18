from __future__ import annotations

import logging
import time
from typing import Any, Dict

import requests

from logging_setup import log_event
from observability_http import start_observability_http_server
from observability_metrics import (
    queue_failed,
    queue_ok,
    queue_oldest_pending_age_seconds,
    queue_oldest_processing_age_seconds,
    queue_pending,
    queue_processing,
    worker_job_latency_seconds,
    worker_jobs_processed_total,
    worker_requeued_stale_jobs_total,
)
from workers.extract_worker_bootstrap import bootstrap_worker
from workers.extract_worker_job import work_one
from workers.extract_worker_store import supabase_cfg
from workers.extract_worker_types import WorkerToggles
from workers.job_manager import claim_jobs, requeue_stale_jobs
from workers.supabase_operations import build_headers, get_oldest_created_age_seconds, get_queue_counts


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
DEFAULT_ENABLE_BROADCAST = True
DEFAULT_ENABLE_DMS = True


def _resolve_side_effect_toggles(cfg: Any) -> tuple[bool, bool]:
    fields_set = set(getattr(cfg, "model_fields_set", set()) or [])
    enable_broadcast = bool(getattr(cfg, "enable_broadcast", DEFAULT_ENABLE_BROADCAST))
    if "enable_broadcast" not in fields_set:
        has_bot_config = bool(getattr(cfg, "group_bot_token", None) or getattr(cfg, "bot_api_url", None))
        has_target_chat = bool(getattr(cfg, "aggregator_channel_id", None) or getattr(cfg, "aggregator_channel_ids", None))
        enable_broadcast = bool(has_bot_config and has_target_chat)

    enable_dms = bool(getattr(cfg, "enable_dms", DEFAULT_ENABLE_DMS))
    if "enable_dms" not in fields_set:
        enable_dms = bool(getattr(cfg, "dm_enabled", False))

    return enable_broadcast, enable_dms


def _import_side_effects() -> tuple[Any, Any]:
    try:
        import broadcast_assignments
    except Exception:
        broadcast_assignments = None  # type: ignore

    try:
        from dm_assignments import send_dms
    except Exception:
        send_dms = None  # type: ignore

    return broadcast_assignments, send_dms


def main() -> None:
    cfg, logger, version, circuit_breaker = bootstrap_worker()
    url, key = supabase_cfg(cfg)
    broadcast_assignments, send_dms = _import_side_effects()

    def _dep_health() -> tuple[bool, Dict[str, Any]]:
        try:
            h = dict(build_headers(key))
            h["prefer"] = "count=exact"
            resp = requests.get(f"{url}/rest/v1/telegram_extractions?select=id&limit=1", headers=h, timeout=5)
            return (resp.status_code < 400), {"status_code": resp.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    start_observability_http_server(
        port=9002,
        component="worker",
        health_handlers={
            "/health/worker": lambda: (True, {"pipeline_version": version.pipeline_version, "schema_version": version.schema_version}),
            "/health/dependencies": _dep_health,
        },
    )

    sync_on_startup = bool(getattr(cfg, "broadcast_sync_on_startup", False))
    if sync_on_startup:
        try:
            log_event(logger, logging.INFO, "broadcast_sync_startup_begin")
            from sync_broadcast_channel import _get_bot_token, _parse_chat_ids, sync_channel

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

    pipeline_version = str(getattr(cfg, "extraction_pipeline_version", None) or DEFAULT_PIPELINE_VERSION).strip() or DEFAULT_PIPELINE_VERSION
    claim_batch_size = int(getattr(cfg, "extraction_worker_batch_size", None) or DEFAULT_CLAIM_BATCH_SIZE)
    idle_sleep_s = float(getattr(cfg, "extraction_worker_idle_s", None) or DEFAULT_IDLE_SLEEP_SECONDS)

    enable_broadcast, enable_dms = _resolve_side_effect_toggles(cfg)
    toggles = WorkerToggles(
        enable_broadcast=enable_broadcast,
        enable_dms=enable_dms,
        max_attempts=int(getattr(cfg, "extraction_max_attempts", None) or DEFAULT_MAX_ATTEMPTS),
        backoff_base_s=float(getattr(cfg, "extraction_backoff_base_s", None) or DEFAULT_BACKOFF_BASE_S),
        backoff_max_s=float(getattr(cfg, "extraction_backoff_max_s", None) or DEFAULT_BACKOFF_MAX_S),
        stale_processing_seconds=int(getattr(cfg, "extraction_stale_processing_seconds", None) or DEFAULT_STALE_PROCESSING_SECONDS),
        use_normalized_text_for_llm=bool(getattr(cfg, "use_normalized_text_for_llm", DEFAULT_USE_NORMALIZED_TEXT_FOR_LLM)),
        hard_validate_mode=str(getattr(cfg, "hard_validate_mode", None) or DEFAULT_HARD_VALIDATE_MODE).strip() or DEFAULT_HARD_VALIDATE_MODE,
        enable_deterministic_signals=bool(getattr(cfg, "enable_deterministic_signals", DEFAULT_ENABLE_DETERMINISTIC_SIGNALS)),
        use_deterministic_time=bool(getattr(cfg, "use_deterministic_time", DEFAULT_USE_DETERMINISTIC_TIME)),
        enable_postal_code_estimated=bool(getattr(cfg, "enable_postal_code_estimated", DEFAULT_ENABLE_POSTAL_CODE_ESTIMATED)),
    )

    oneshot = bool(getattr(cfg, "extraction_worker_oneshot", False))
    max_jobs = int(getattr(cfg, "extraction_worker_max_jobs", 0) or 0)
    if max_jobs < 0:
        max_jobs = 0

    log_event(
        logger,
        logging.INFO,
        "worker_start",
        pipeline_version=pipeline_version,
        batch_size=claim_batch_size,
        broadcast=toggles.enable_broadcast and broadcast_assignments is not None,
        dms=toggles.enable_dms and send_dms is not None,
        max_attempts=toggles.max_attempts,
        backoff_base_s=toggles.backoff_base_s,
        backoff_max_s=toggles.backoff_max_s,
        stale_processing_s=toggles.stale_processing_seconds,
        use_normalized_text_for_llm=bool(toggles.use_normalized_text_for_llm),
        hard_validate_mode=toggles.hard_validate_mode,
        enable_deterministic_signals=bool(toggles.enable_deterministic_signals),
        use_deterministic_time=bool(toggles.use_deterministic_time),
        enable_postal_code_estimated=bool(toggles.enable_postal_code_estimated),
        oneshot=oneshot,
        max_jobs=max_jobs or None,
    )

    processed = 0
    last_metrics = 0.0
    last_requeue = 0.0
    requeue_interval_s = 60.0
    metrics_interval_s = 15.0

    channel_cache: Dict[str, Dict[str, Any]] = {}

    try:
        while True:
            now = time.time()
            pv = version.pipeline_version
            sv = version.schema_version

            if toggles.stale_processing_seconds and (now - last_requeue) > requeue_interval_s:
                last_requeue = now
                try:
                    count = requeue_stale_jobs(
                        url,
                        key,
                        older_than_seconds=int(toggles.stale_processing_seconds),
                        pipeline_version=pv,
                        schema_version=sv,
                    )
                    if count:
                        worker_requeued_stale_jobs_total.labels(pipeline_version=pv, schema_version=sv).inc(float(count))
                except Exception:
                    logger.debug("requeue_stale_failed", exc_info=True)

            if (now - last_metrics) > metrics_interval_s:
                try:
                    counts = get_queue_counts(url, key, ["pending", "processing", "ok", "failed"])
                    queue_pending.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("pending") or 0))
                    queue_processing.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("processing") or 0))
                    queue_ok.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("ok") or 0))
                    queue_failed.labels(pipeline_version=pv, schema_version=sv).set(float(counts.get("failed") or 0))
                    oldest_pending = get_oldest_created_age_seconds(url, key, "pending")
                    oldest_processing = get_oldest_created_age_seconds(url, key, "processing")
                    queue_oldest_pending_age_seconds.labels(pipeline_version=pv, schema_version=sv).set(float(oldest_pending or 0.0))
                    queue_oldest_processing_age_seconds.labels(pipeline_version=pv, schema_version=sv).set(float(oldest_processing or 0.0))
                except Exception:
                    logger.debug("queue_metrics_update_failed", exc_info=True)
                last_metrics = now

            jobs = claim_jobs(url, key, pipeline_version=pipeline_version, limit=int(max(1, claim_batch_size)), schema_version=sv)
            if not jobs:
                if oneshot:
                    log_event(logger, logging.INFO, "worker_oneshot_done", processed=processed, pipeline_version=pipeline_version)
                    return
                time.sleep(max(0.25, float(idle_sleep_s)))
                continue

            log_event(logger, logging.INFO, "claimed_jobs", count=len(jobs), pipeline_version=pipeline_version)
            for job in jobs:
                if not isinstance(job, dict):
                    continue
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
                    status = work_one(
                        cfg=cfg,
                        logger=logger,
                        version=version,
                        toggles=toggles,
                        circuit_breaker=circuit_breaker,
                        channel_cache=channel_cache,
                        url=url,
                        key=key,
                        job=job,
                        broadcast_assignments=broadcast_assignments,
                        send_dms=send_dms,
                    )
                    processed += 1
                    dt_s = time.perf_counter() - t0
                    dt_ms = int(dt_s * 1000)
                    try:
                        worker_job_latency_seconds.labels(pipeline_version=pv, schema_version=sv).observe(dt_s)
                        worker_jobs_processed_total.labels(status=str(status), pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                    logger.info("job_end extraction_id=%s dt_ms=%s", extraction_id, dt_ms)
                except Exception as e:
                    dt_s = time.perf_counter() - t0
                    dt_ms = int(dt_s * 1000)
                    try:
                        worker_job_latency_seconds.labels(pipeline_version=pv, schema_version=sv).observe(dt_s)
                        worker_jobs_processed_total.labels(status="error", pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                    logger.warning("job_error extraction_id=%s dt_ms=%s error=%s", extraction_id, dt_ms, str(e))
                if max_jobs and processed >= max_jobs:
                    log_event(
                        logger,
                        logging.INFO,
                        "worker_max_jobs_reached",
                        processed=processed,
                        max_jobs=max_jobs,
                        pipeline_version=pipeline_version,
                    )
                    return
    except KeyboardInterrupt:
        log_event(logger, logging.INFO, "worker_interrupted")
        return
    except Exception as e:
        log_event(logger, logging.WARNING, "worker_loop_error", error=str(e))
        time.sleep(2.0)
