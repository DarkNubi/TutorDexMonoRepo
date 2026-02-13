#!/usr/bin/env bash
set -euo pipefail

backend_url="${BACKEND_URL:-http://127.0.0.1:8000}"

worker_health_url="${AGG_WORKER_HEALTH_URL:-${backend_url}/health/worker}"
deps_health_url="${AGG_WORKER_DEPS_URL:-${backend_url}/health/dependencies}"
collector_health_url="${AGG_COLLECTOR_HEALTH_URL:-${backend_url}/health/collector}"

echo "TutorDex smoke test: aggregator (worker/collector via backend health)"
echo "  BACKEND_URL=${backend_url}"
echo "  AGG_WORKER_HEALTH_URL=${worker_health_url}"
echo "  AGG_WORKER_DEPS_URL=${deps_health_url}"
echo "  AGG_COLLECTOR_HEALTH_URL=${collector_health_url}"

python3 scripts/smoke_http_get.py "${worker_health_url}" "${deps_health_url}" "${collector_health_url}"
