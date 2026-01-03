from __future__ import annotations

import time
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


def observe_request(*, method: str, path: str, status_code: int, latency_s: float) -> None:
    http_requests_total.labels(method=method, path=path, status_code=str(status_code)).inc()
    http_request_latency_seconds.labels(method=method, path=path).observe(max(0.0, float(latency_s)))


def metrics_payload() -> tuple[bytes, str]:
    data = generate_latest()
    return data, CONTENT_TYPE_LATEST

