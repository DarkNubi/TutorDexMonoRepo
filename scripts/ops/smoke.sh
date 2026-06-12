#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
project="$(project_for "${env}")"
env_file="$(env_file_for "${env}")"

# Load ports for local URL construction (non-secret).
set -a
# shellcheck disable=SC1090
source "${env_file}"
set +a

backend_url="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT:-8000}}"
prom_url="${PROMETHEUS_URL:-http://127.0.0.1:${PROMETHEUS_PORT:-9090}}"
am_url="${ALERTMANAGER_URL:-http://127.0.0.1:${ALERTMANAGER_PORT:-9093}}"
graf_url="${GRAFANA_URL:-http://127.0.0.1:${GRAFANA_PORT:-3300}}"

audit_log "smoke" "${env}" "$@"

echo "TutorDex smoke test (${env})"
echo "  BACKEND_URL=${backend_url}"
echo "  PROMETHEUS_URL=${prom_url}"
echo "  ALERTMANAGER_URL=${am_url}"
echo "  GRAFANA_URL=${graf_url}"

BACKEND_URL="${backend_url}" scripts/smoke_test_backend.sh
BACKEND_URL="${backend_url}" scripts/smoke_test_aggregator.sh
PROMETHEUS_URL="${prom_url}/-/ready" ALERTMANAGER_URL="${am_url}/-/ready" GRAFANA_URL="${graf_url}/api/health" scripts/smoke_test_observability.sh

# Extra: assert worker health directly from inside the container (covers cases where backend isn't reachable).
docker compose -f "${ROOT_DIR}/docker-compose.yml" -p "${project}" --env-file "${env_file}" exec -T aggregator-worker python - <<'PY'
import urllib.request
urls = ("http://127.0.0.1:9002/health/worker", "http://127.0.0.1:9002/health/dependencies")
for u in urls:
    with urllib.request.urlopen(u, timeout=10) as r:
        if int(getattr(r, "status", 200) or 200) >= 300:
            raise SystemExit(1)
        print("OK:", u, getattr(r, "status", 200))
PY

echo "All smoke checks passed (${env})."
