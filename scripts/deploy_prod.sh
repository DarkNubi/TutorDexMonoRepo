#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex PRODUCTION ==="
echo "WARNING: This will restart production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "Deployment cancelled."
  exit 0
fi

cd "$(dirname "$0")/.."

ENV_FILE=".env.prod"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

./scripts/validate_env.sh "$ENV_FILE"

_maybe_disable_missing_docker_creds_helper() {
  # Workaround for environments where Docker is configured to use the Desktop credential helper
  # but the helper binary isn't available (common on headless servers / WSL without Desktop integration).
  #
  # This repo mostly pulls public images; we can safely bypass the creds store to avoid hard failures.
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

docker compose -p tutordex-prod pull prometheus alertmanager grafana redis tempo otel-collector || true

docker compose \
  -f docker-compose.yml \
  -p tutordex-prod \
  --env-file "$ENV_FILE" \
  up -d --build

echo "Production deployment complete."
echo "Backend: http://localhost:8000"
echo "Grafana: http://localhost:3300"
echo "Prometheus: http://localhost:9090"
