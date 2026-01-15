from __future__ import annotations

import logging
from typing import Any, Tuple

from circuit_breaker import CircuitBreaker
from logging_setup import bind_log_context, setup_logging
from observability_metrics import set_version_metrics
from otel import setup_otel
from sentry_init import setup_sentry
from shared.config import load_aggregator_config

from workers.extract_worker_types import VersionInfo


def bootstrap_worker() -> Tuple[Any, logging.Logger, VersionInfo, CircuitBreaker]:
    cfg = load_aggregator_config()

    setup_logging()
    logger = logging.getLogger("extract_worker")

    v = set_version_metrics(component="worker")
    setup_sentry(service_name=cfg.sentry_service_name or "tutordex-aggregator-worker")
    setup_otel(service_name=cfg.otel_service_name or "tutordex-aggregator-worker")

    default_ctx = bind_log_context(
        component="worker",
        pipeline_version=v.pipeline_version,
        schema_version=v.schema_version,
    )
    default_ctx.__enter__()

    llm_circuit_breaker = CircuitBreaker(
        failure_threshold=int(cfg.llm_circuit_breaker_threshold),
        timeout_seconds=int(cfg.llm_circuit_breaker_timeout_seconds),
    )

    return cfg, logger, VersionInfo(v.pipeline_version, v.schema_version), llm_circuit_breaker

