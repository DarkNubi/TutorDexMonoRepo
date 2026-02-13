#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
require_confirm_prod "${env}" "$@"
project="$(project_for "${env}")"
env_file="$(env_file_for "${env}")"

service="${TD_SERVICE:-}"
for i in "$@"; do
  if [[ "$i" == "--service="* ]]; then
    service="${i#--service=}"
  fi
done

if [[ -z "${service}" ]]; then
  die "Missing --service=<name> (or TD_SERVICE)"
fi

audit_log "restart" "${env}" "$@"
docker compose -f "${ROOT_DIR}/docker-compose.yml" -p "${project}" --env-file "${env_file}" restart "${service}"
