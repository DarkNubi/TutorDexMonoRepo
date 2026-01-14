"""
Workers package for TutorDex extraction pipeline.

This package contains the extraction worker and supporting modules.
"""

from workers.job_manager import (
    claim_jobs,
    get_job_attempt,
    mark_job_status,
    merge_meta,
    requeue_stale_jobs,
)
from workers.supabase_operations import (
    build_headers,
    call_rpc,
    fetch_channel,
    fetch_raw_message,
    get_one,
    get_oldest_created_age_seconds,
    get_queue_counts,
    patch_table,
)
from workers.triage_reporter import (
    get_thread_id_for_category,
    get_triage_config,
    send_telegram_message,
    try_report_triage_message,
)
from workers.worker_config import WorkerConfig, load_worker_config

__all__ = [
    # job_manager
    "claim_jobs",
    "get_job_attempt",
    "mark_job_status",
    "merge_meta",
    "requeue_stale_jobs",
    # supabase_operations
    "build_headers",
    "call_rpc",
    "fetch_channel",
    "fetch_raw_message",
    "get_one",
    "get_oldest_created_age_seconds",
    "get_queue_counts",
    "patch_table",
    # triage_reporter
    "get_thread_id_for_category",
    "get_triage_config",
    "send_telegram_message",
    "try_report_triage_message",
    # worker_config
    "WorkerConfig",
    "load_worker_config",
]
