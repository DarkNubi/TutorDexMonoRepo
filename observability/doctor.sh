#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PROMETHEUS_PORT="${PROMETHEUS_PORT:-9090}"
GRAFANA_PORT="${GRAFANA_PORT:-3300}"
ALERTMANAGER_PORT="${ALERTMANAGER_PORT:-9093}"

echo "TutorDex doctor"
echo "- root: ${ROOT_DIR}"
echo

check() {
  local name="$1"
  local url="$2"
  echo -n "Checking ${name} ... "
  if curl -fsS --max-time 3 "$url" >/dev/null; then
    echo "OK"
  else
    echo "FAIL ($url)"
    return 1
  fi
}

check "Prometheus" "http://127.0.0.1:${PROMETHEUS_PORT}/-/ready"
check "Alertmanager" "http://127.0.0.1:${ALERTMANAGER_PORT}/-/ready"
check "Grafana" "http://127.0.0.1:${GRAFANA_PORT}/api/health"

echo
echo "Prometheus targets (quick):"
curl -fsS "http://127.0.0.1:${PROMETHEUS_PORT}/api/v1/targets?state=active" | head -c 800 || true
echo
echo
echo "Done."

