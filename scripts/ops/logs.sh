#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
project="$(project_for "${env}")"
env_file="$(env_file_for "${env}")"

audit_log "logs" "${env}" "$@"

# Pass-through remaining args (except --env <x>) to docker compose logs.
args=()
skip_next=0
for a in "$@"; do
  if [[ $skip_next -eq 1 ]]; then
    skip_next=0
    continue
  fi
  if [[ "$a" == "--env" ]]; then
    skip_next=1
    continue
  fi
  args+=("$a")
done

docker compose -f "${ROOT_DIR}/docker-compose.yml" -p "${project}" --env-file "${env_file}" logs -f "${args[@]:-}"
