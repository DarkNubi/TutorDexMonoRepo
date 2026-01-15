from __future__ import annotations

from typing import Any, Dict

from observability_metrics import (
    assignment_quality_inconsistency_total,
    assignment_quality_missing_field_total,
    worker_llm_call_latency_seconds,
    worker_llm_fail_total,
    worker_llm_requests_total,
)
from workers.extract_worker_types import VersionInfo


def quality_metrics(version: VersionInfo) -> Dict[str, Any]:
    return {
        "assignment_quality_missing_field_total": assignment_quality_missing_field_total,
        "assignment_quality_inconsistency_total": assignment_quality_inconsistency_total,
        "pipeline_version": version.pipeline_version,
        "schema_version": version.schema_version,
    }


def llm_metrics(version: VersionInfo) -> Dict[str, Any]:
    return {
        "llm_requests_total": worker_llm_requests_total,
        "llm_call_latency_seconds": worker_llm_call_latency_seconds,
        "llm_fail_total": worker_llm_fail_total,
        "pipeline_version": version.pipeline_version,
        "schema_version": version.schema_version,
    }

