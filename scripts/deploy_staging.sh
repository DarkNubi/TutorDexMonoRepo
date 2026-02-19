#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex STAGING ==="

cd "$(dirname "$0")/.."

ENV_FILE=".env.staging"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

./scripts/validate_env.sh "$ENV_FILE"

_maybe_disable_missing_docker_creds_helper() {
  local docker_cfg_dir="${DOCKER_CONFIG:-$HOME/.docker}"
  local docker_cfg_file="${docker_cfg_dir}/config.json"

  if [ ! -f "$docker_cfg_file" ]; then
    return 0
  fi

  if ! grep -Eq '"credsStore"[[:space:]]*:[[:space:]]*"desktop"' "$docker_cfg_file"; then
    return 0
  fi

  if command -v docker-credential-desktop >/dev/null 2>&1 || command -v docker-credential-desktop.exe >/dev/null 2>&1; then
    return 0
  fi

  local tmp_cfg_dir
  tmp_cfg_dir="$(mktemp -d 2>/dev/null || mktemp -d -t tutordex-docker-config)"
  printf '%s\n' '{}' > "${tmp_cfg_dir}/config.json"
  export DOCKER_CONFIG="$tmp_cfg_dir"
  echo "WARN: docker-credential-desktop helper not found; temporarily using empty DOCKER_CONFIG=${DOCKER_CONFIG} for this deploy."
}

_maybe_disable_missing_docker_creds_helper

docker compose -p tutordex-staging pull prometheus alertmanager grafana redis tempo otel-collector || true

docker compose \
  -f docker-compose.yml \
  -p tutordex-staging \
  --env-file "$ENV_FILE" \
  up -d --build \
  --scale homepage=0

echo "Staging deployment complete."
echo "Backend: http://localhost:8001"
echo "Grafana: http://localhost:3301"
echo "Prometheus: http://localhost:9091"
