from __future__ import annotations

from typing import Optional

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


http_requests_total = Counter(
    "backend_http_requests_total",
    "HTTP requests served by the backend.",
    ["method", "path", "status_code"],
)

http_request_latency_seconds = Histogram(
    "backend_http_request_latency_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

# Exception handling metrics
swallowed_exceptions_total = Counter(
    "backend_swallowed_exceptions_total",
    "Exceptions that were swallowed (logged but not re-raised) for observability.",
    ["context", "exception_type"],
)


def observe_request(
    *,
    method: str,
    path: str,
    status_code: Optional[int] = None,
    status: Optional[int] = None,
    latency_s: Optional[float] = None,
    latency_ms: Optional[float] = None,
    **_: object,
) -> None:
    code = int(status_code if status_code is not None else (status if status is not None else 200))
    if latency_s is None:
        latency_s = (float(latency_ms) / 1000.0) if latency_ms is not None else 0.0
    http_requests_total.labels(method=method, path=path, status_code=str(code)).inc()
    http_request_latency_seconds.labels(method=method, path=path).observe(max(0.0, float(latency_s)))


def metrics_payload() -> tuple[bytes, str]:
    data = generate_latest()
    return data, CONTENT_TYPE_LATEST
