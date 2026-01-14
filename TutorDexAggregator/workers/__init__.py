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

# Phase 2 modules
from workers.utils import (
    build_message_link,
    coerce_list_of_str,
    extract_sg_postal_codes,
    sha256_hash,
    utc_now_iso,
)
from workers.message_processor import (
    MessageFilterResult,
    build_extraction_context,
    filter_message,
    load_channel_info,
    load_raw_message,
)
from workers.llm_processor import (
    classify_llm_error,
    extract_with_llm,
    get_examples_metadata,
    get_llm_model_name,
    get_prompt_metadata,
)
from workers.enrichment_pipeline import (
    apply_deterministic_time,
    apply_hard_validation,
    apply_postal_code_estimated,
    build_signals,
    fill_postal_code_from_text,
    run_enrichment_pipeline,
)
from workers.validation_pipeline import (
    increment_quality_inconsistency,
    increment_quality_missing,
    run_quality_checks,
    validate_schema,
)

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
    # utils
    "build_message_link",
    "coerce_list_of_str",
    "extract_sg_postal_codes",
    "sha256_hash",
    "utc_now_iso",
    # message_processor
    "MessageFilterResult",
    "build_extraction_context",
    "filter_message",
    "load_channel_info",
    "load_raw_message",
    # llm_processor
    "classify_llm_error",
    "extract_with_llm",
    "get_examples_metadata",
    "get_llm_model_name",
    "get_prompt_metadata",
    # enrichment_pipeline
    "apply_deterministic_time",
    "apply_hard_validation",
    "apply_postal_code_estimated",
    "build_signals",
    "fill_postal_code_from_text",
    "run_enrichment_pipeline",
    # validation_pipeline
    "increment_quality_inconsistency",
    "increment_quality_missing",
    "run_quality_checks",
    "validate_schema",
]
