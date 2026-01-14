from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram
from shared.config import load_aggregator_config


def pipeline_version() -> str:
    cfg = load_aggregator_config()
    return str(cfg.extraction_pipeline_version or "2026-01-02_det_time_v1").strip() or "2026-01-02_det_time_v1"


def schema_version() -> str:
    cfg = load_aggregator_config()
    return str(cfg.schema_version or "v2")


@dataclass(frozen=True)
class Versions:
    pipeline_version: str
    schema_version: str


def versions() -> Versions:
    return Versions(pipeline_version=pipeline_version(), schema_version=schema_version())


# ----------------------------
# Collector
# ----------------------------
collector_messages_seen_total = Counter(
    "collector_messages_seen_total",
    "Raw Telegram messages observed by the collector.",
    ["channel", "pipeline_version", "schema_version"],
)

collector_messages_upserted_total = Counter(
    "collector_messages_upserted_total",
    "Raw Telegram messages successfully upserted into storage.",
    ["channel", "pipeline_version", "schema_version"],
)

collector_errors_total = Counter(
    "collector_errors_total",
    "Collector errors (best-effort classification).",
    ["channel", "reason", "pipeline_version", "schema_version"],
)

collector_last_message_timestamp_seconds = Gauge(
    "collector_last_message_timestamp_seconds",
    "UTC timestamp of the most recent message observed per channel.",
    ["channel", "pipeline_version", "schema_version"],
)

collector_pipeline_version = Gauge(
    "collector_pipeline_version",
    "Collector pipeline version (label value).",
    ["version"],
)

collector_schema_version = Gauge(
    "collector_schema_version",
    "Collector schema version (label value).",
    ["version"],
)


# ----------------------------
# Queue + Worker
# ----------------------------
queue_pending = Gauge(
    "queue_pending",
    "Queue pending jobs for the current pipeline version.",
    ["pipeline_version", "schema_version"],
)

queue_processing = Gauge(
    "queue_processing",
    "Queue processing jobs for the current pipeline version.",
    ["pipeline_version", "schema_version"],
)

queue_failed = Gauge(
    "queue_failed",
    "Queue failed jobs for the current pipeline version.",
    ["pipeline_version", "schema_version"],
)

queue_ok = Gauge(
    "queue_ok",
    "Queue ok jobs for the current pipeline version.",
    ["pipeline_version", "schema_version"],
)

queue_oldest_pending_age_seconds = Gauge(
    "queue_oldest_pending_age_seconds",
    "Age in seconds of the oldest pending job for the current pipeline version.",
    ["pipeline_version", "schema_version"],
)

queue_oldest_processing_age_seconds = Gauge(
    "queue_oldest_processing_age_seconds",
    "Age in seconds of the oldest processing job for the current pipeline version.",
    ["pipeline_version", "schema_version"],
)

worker_jobs_processed_total = Counter(
    "worker_jobs_processed_total",
    "Jobs processed by the worker.",
    ["status", "pipeline_version", "schema_version"],
)

worker_parse_success_total = Counter(
    "worker_parse_success_total",
    "Extractions where the parsed assignment passed schema validation and persisted ok.",
    ["channel", "pipeline_version", "schema_version"],
)

worker_parse_failure_total = Counter(
    "worker_parse_failure_total",
    "Extractions that failed (best-effort reason classification).",
    ["channel", "reason", "pipeline_version", "schema_version"],
)

worker_job_latency_seconds = Histogram(
    "worker_job_latency_seconds",
    "End-to-end job latency (seconds) for the worker.",
    ["pipeline_version", "schema_version"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 45, 90, 180, 300, 600),
)

worker_job_stage_latency_seconds = Histogram(
    "worker_job_stage_latency_seconds",
    "Stage latency (seconds) for the worker job pipeline.",
    ["stage", "pipeline_version", "schema_version"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 45, 90, 180),
)

worker_llm_call_latency_seconds = Histogram(
    "worker_llm_call_latency_seconds",
    "LLM call latency (seconds).",
    ["pipeline_version", "schema_version"],
    buckets=(0.25, 0.5, 1, 2, 5, 10, 20, 45, 90, 180, 300),
)

worker_llm_requests_total = Counter(
    "worker_llm_requests_total",
    "LLM extraction requests attempted.",
    ["model", "pipeline_version", "schema_version"],
)

worker_llm_fail_total = Counter(
    "worker_llm_fail_total",
    "LLM call failures.",
    ["pipeline_version", "schema_version"],
)

worker_supabase_requests_total = Counter(
    "worker_supabase_requests_total",
    "Supabase operations attempted.",
    ["operation", "pipeline_version", "schema_version"],
)

worker_supabase_latency_seconds = Histogram(
    "worker_supabase_latency_seconds",
    "Supabase operation latency (seconds).",
    ["operation", "pipeline_version", "schema_version"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)

worker_supabase_fail_total = Counter(
    "worker_supabase_fail_total",
    "Supabase operation failures.",
    ["operation", "pipeline_version", "schema_version"],
)

worker_requeued_stale_jobs_total = Counter(
    "worker_requeued_stale_jobs_total",
    "Jobs requeued from stale processing back to pending.",
    ["pipeline_version", "schema_version"],
)


# ----------------------------
# Tutor types extraction metrics
# ----------------------------
worker_tutor_types_extracted_total = Counter(
    "worker_tutor_types_extracted_total",
    "Tutor type mentions extracted by deterministic extractor.",
    ["channel", "pipeline_version", "schema_version"],
)

worker_tutor_types_low_confidence_total = Counter(
    "worker_tutor_types_low_confidence_total",
    "Tutor type extractions below confidence threshold.",
    ["channel", "pipeline_version", "schema_version"],
)

worker_tutor_types_unmapped_total = Counter(
    "worker_tutor_types_unmapped_total",
    "Tutor type mentions that could not be mapped to canonical type.",
    ["channel", "pipeline_version", "schema_version"],
)

assignment_quality_missing_field_total = Counter(
    "assignment_quality_missing_field_total",
    "Parsed assignments missing important fields (quality signal, not a hard failure).",
    ["field", "channel", "pipeline_version", "schema_version"],
)

assignment_quality_inconsistency_total = Counter(
    "assignment_quality_inconsistency_total",
    "Detected inconsistencies between text/signals/fields (quality signal, not a hard failure).",
    ["kind", "channel", "pipeline_version", "schema_version"],
)

worker_pipeline_version = Gauge(
    "worker_pipeline_version",
    "Worker pipeline version (label value).",
    ["version"],
)

worker_schema_version = Gauge(
    "worker_schema_version",
    "Worker schema version (label value).",
    ["version"],
)


# ----------------------------
# Broadcast / DM
# ----------------------------
broadcast_sent_total = Counter(
    "broadcast_sent_total",
    "Broadcast messages successfully sent.",
    ["pipeline_version", "schema_version"],
)

broadcast_fail_total = Counter(
    "broadcast_fail_total",
    "Broadcast message send failures.",
    ["pipeline_version", "schema_version"],
)

broadcast_fail_reason_total = Counter(
    "broadcast_fail_reason_total",
    "Broadcast send failures by reason (best-effort classification).",
    ["reason", "pipeline_version", "schema_version"],
)

dm_sent_total = Counter(
    "dm_sent_total",
    "DM messages successfully sent.",
    ["pipeline_version", "schema_version"],
)

dm_fail_total = Counter(
    "dm_fail_total",
    "DM send failures.",
    ["pipeline_version", "schema_version"],
)

dm_fail_reason_total = Counter(
    "dm_fail_reason_total",
    "DM send failures by reason (best-effort classification).",
    ["reason", "pipeline_version", "schema_version"],
)

dm_rate_limited_total = Counter(
    "dm_rate_limited_total",
    "DM sends that hit Telegram rate limits.",
    ["pipeline_version", "schema_version"],
)


# ----------------------------
# Duplicate Detection
# ----------------------------
duplicate_detected_total = Counter(
    "tutordex_duplicate_detected_total",
    "Total number of duplicates detected.",
    ["confidence_level", "pipeline_version"],
)

duplicate_group_size = Histogram(
    "tutordex_duplicate_group_size",
    "Size of duplicate groups.",
    buckets=[2, 3, 4, 5, 10, 20, 50],
)

duplicate_detection_seconds = Histogram(
    "tutordex_duplicate_detection_seconds",
    "Time taken to detect duplicates for a single assignment.",
    buckets=[0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0],
)

dm_skipped_duplicate_total = Counter(
    "tutordex_dm_skipped_duplicate_total",
    "DMs skipped due to duplicate filtering.",
)

broadcast_skipped_duplicate_total = Counter(
    "tutordex_broadcast_skipped_duplicate_total",
    "Broadcasts skipped due to duplicate filtering.",
)

duplicate_detection_errors_total = Counter(
    "tutordex_duplicate_detection_errors_total",
    "Errors during duplicate detection.",
    ["error_type"],
)


# ----------------------------
# Business Metrics (Task 6)
# ----------------------------

# Assignments per hour (rolling window)
assignments_created_per_hour = Gauge(
    "tutordex_assignments_created_per_hour",
    "Number of assignments created in the last hour (rolling window).",
)

# Active tutors with DM subscriptions
tutors_with_active_dms = Gauge(
    "tutordex_tutors_with_active_dm_subscriptions",
    "Number of tutors with active DM subscriptions in Redis.",
)

# Time to first match histogram
time_to_first_match_seconds = Histogram(
    "tutordex_assignment_time_to_first_match_seconds",
    "Time from assignment creation to first tutor match (DM sent).",
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400, 28800],  # 1min to 8hours
)

# Active assignments by status
assignments_by_status = Gauge(
    "tutordex_assignments_by_status",
    "Number of assignments in each status.",
    ["status"],  # open, closed, hidden, expired, deleted
)

# Tutor engagement metrics
tutors_with_profiles = Gauge(
    "tutordex_tutors_with_profiles",
    "Total number of tutors with saved profiles.",
)

tutors_with_telegram_linked = Gauge(
    "tutordex_tutors_with_telegram_linked",
    "Number of tutors with Telegram accounts linked.",
)

# Assignment quality metrics
assignments_with_parsed_rate = Gauge(
    "tutordex_assignments_with_parsed_rate",
    "Percentage of assignments with successfully parsed rate information.",
)

assignments_with_location = Gauge(
    "tutordex_assignments_with_location",
    "Percentage of assignments with location information (region or postal code).",
)

# Matching efficiency
average_matches_per_assignment = Gauge(
    "tutordex_average_matches_per_assignment",
    "Average number of tutors matched per assignment.",
)


def set_version_metrics(*, component: str, v: Optional[Versions] = None) -> Versions:
    v = v or versions()
    if component == "collector":
        collector_pipeline_version.labels(version=v.pipeline_version).set(1)
        collector_schema_version.labels(version=v.schema_version).set(1)
    if component == "worker":
        worker_pipeline_version.labels(version=v.pipeline_version).set(1)
        worker_schema_version.labels(version=v.schema_version).set(1)
    return v
