from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram


def pipeline_version() -> str:
    return (os.environ.get("EXTRACTION_PIPELINE_VERSION") or "2026-01-02_det_time_v1").strip() or "2026-01-02_det_time_v1"


def schema_version() -> str:
    # Bump when the `canonical_json` contract changes in a way that affects downstream consumers/alerts.
    return "v2"


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


def set_version_metrics(*, component: str, v: Optional[Versions] = None) -> Versions:
    v = v or versions()
    if component == "collector":
        collector_pipeline_version.labels(version=v.pipeline_version).set(1)
        collector_schema_version.labels(version=v.schema_version).set(1)
    if component == "worker":
        worker_pipeline_version.labels(version=v.pipeline_version).set(1)
        worker_schema_version.labels(version=v.schema_version).set(1)
    return v
