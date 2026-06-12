#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
require_confirm_prod "${env}" "$@"

env_file="$(env_file_for "${env}")"
[[ -f "${env_file}" ]] || die "Env file not found: ${env_file}"

audit_log "deploy" "${env}" "$@"

cd "${ROOT_DIR}"

./scripts/validate_env.sh "${env_file}"

project="$(project_for "${env}")"

# Keep the pull list aligned with scripts/deploy_prod.sh.
docker compose -p "${project}" pull prometheus alertmanager grafana redis tempo otel-collector || true

docker compose -f docker-compose.yml -p "${project}" --env-file "${env_file}" up -d --build

echo "Deploy complete (${env})."

