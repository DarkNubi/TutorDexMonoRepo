#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
project="$(project_for "${env}")"
env_file="$(env_file_for "${env}")"

audit_log "status" "${env}" "$@"
docker compose -f "${ROOT_DIR}/docker-compose.yml" -p "${project}" --env-file "${env_file}" ps
