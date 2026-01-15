from __future__ import annotations

import logging
from pathlib import Path

from logging_setup import bind_log_context, setup_logging
from observability_metrics import set_version_metrics
from otel import setup_otel
from sentry_init import setup_sentry
from shared.config import load_aggregator_config
from workers.extract_worker_types import VersionInfo

from collection.types import CollectorContext


def bootstrap_collector() -> CollectorContext:
    setup_logging()
    logger = logging.getLogger("collector")
    v = set_version_metrics(component="collector")
    cfg = load_aggregator_config()
    setup_sentry(service_name=cfg.sentry_service_name or "tutordex-collector")
    setup_otel(service_name=cfg.otel_service_name or "tutordex-collector")
    default_ctx = bind_log_context(component="collector", pipeline_version=v.pipeline_version, schema_version=v.schema_version)
    default_ctx.__enter__()
    return CollectorContext(cfg=cfg, logger=logger, version=VersionInfo(v.pipeline_version, v.schema_version), here=Path(__file__).resolve().parents[1])

