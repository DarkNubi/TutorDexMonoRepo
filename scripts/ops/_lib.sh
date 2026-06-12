#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

require_cmd docker
require_cmd curl

_usage_env() {
  cat >&2 <<'EOF'
Usage: --env {prod|staging}
Optional: TD_ENV=prod|staging
EOF
}

resolve_env() {
  local env="${TD_ENV:-}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --env)
        shift
        env="${1:-}"
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  if [[ -z "${env}" ]]; then
    _usage_env
    die "Missing --env"
  fi

  case "${env}" in
    prod|production)
      echo "prod"
      ;;
    staging)
      echo "staging"
      ;;
    *)
      _usage_env
      die "Invalid --env: ${env}"
      ;;
  esac
}

env_file_for() {
  local env="$1"
  case "${env}" in
    prod) echo "${ROOT_DIR}/.env.prod" ;;
    staging) echo "${ROOT_DIR}/.env.staging" ;;
    *) die "Unknown env: ${env}" ;;
  esac
}

source_env_file_for() {
  local env="$1"
  local env_file
  env_file="$(env_file_for "${env}")"
  [[ -f "${env_file}" ]] || die "Env file not found: ${env_file}"
  set -a
  # shellcheck disable=SC1090
  source "${env_file}"
  set +a
}

project_for() {
  local env="$1"
  case "${env}" in
    prod) echo "tutordex-prod" ;;
    staging) echo "tutordex-staging" ;;
    *) die "Unknown env: ${env}" ;;
  esac
}

compose_base() {
  local env="$1"
  local env_file
  env_file="$(env_file_for "${env}")"
  [[ -f "${env_file}" ]] || die "Env file not found: ${env_file}"

  local project
  project="$(project_for "${env}")"

  echo "docker compose -f \"${ROOT_DIR}/docker-compose.yml\" -p \"${project}\" --env-file \"${env_file}\""
}

require_confirm_prod() {
  local env="$1"
  local yes="${TD_YES:-}"
  for arg in "$@"; do
    if [[ "${arg}" == "--yes" || "${arg}" == "--yes-really" ]]; then
      yes="yes"
    fi
  done
  if [[ "${env}" == "prod" && "${yes}" != "yes" ]]; then
    die "Refusing to run on prod without --yes (or TD_YES=yes)"
  fi
}

audit_log() {
  local action="$1"
  local env="$2"
  shift 2 || true
  local ts
  ts="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || true)"
  local who
  who="$(whoami 2>/dev/null || echo "unknown")"
  local cwd
  cwd="$(pwd 2>/dev/null || echo "")"
  local args_json
  args_json="$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' "$@" 2>/dev/null || echo "[]")"
  printf '{"ts":"%s","who":"%s","cwd":"%s","action":"%s","env":"%s","args":%s}\n' \
    "${ts:-}" "${who}" "${cwd}" "${action}" "${env}" "${args_json}" >> "${ROOT_DIR}/ops_audit.jsonl" || true
}
