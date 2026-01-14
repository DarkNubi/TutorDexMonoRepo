from __future__ import annotations

import logging

from shared.config import load_backend_config


logger = logging.getLogger("tutordex_backend.otel")

def setup_otel() -> None:
    """
    Optional OpenTelemetry tracing hook.

    - No hard dependency: if opentelemetry packages aren't installed, this is a no-op.
    - Enable with `OTEL_ENABLED=1`.
    - Export via OTLP to `OTEL_EXPORTER_OTLP_ENDPOINT` (defaults to http://otel-collector:4318).
    """
    cfg = load_backend_config()
    if not bool(cfg.otel_enabled):
        return

    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.sdk.resources import Resource  # type: ignore
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter  # type: ignore
    except Exception:
        logger.info("otel_disabled_missing_packages")
        return

    service_name = str(cfg.otel_service_name or "tutordex-backend").strip() or "tutordex-backend"
    endpoint = str(cfg.otel_exporter_otlp_endpoint or "http://otel-collector:4318").strip()

    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=endpoint)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        logger.info("otel_enabled", extra={"service_name": service_name, "endpoint": endpoint})
    except Exception:
        logger.exception("otel_setup_failed")
