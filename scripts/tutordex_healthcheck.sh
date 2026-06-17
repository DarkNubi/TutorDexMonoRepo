#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

env_name=""
public_url=""
skip_docker=0

usage() {
  cat <<'EOF'
Usage: scripts/tutordex_healthcheck.sh [--env staging|prod] [--public-url URL] [--skip-docker]

Read-only orientation helper for TutorDex agents.
Does not source or print env files. When --env is used, Docker Compose may read
the selected env file for interpolation.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: --env requires staging or prod" >&2
        exit 2
      fi
      env_name="${1:-}"
      shift
      ;;
    --public-url)
      shift
      if [[ $# -eq 0 ]]; then
        echo "ERROR: --public-url requires a URL" >&2
        exit 2
      fi
      public_url="${1:-}"
      shift
      ;;
    --skip-docker)
      skip_docker=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

case "${env_name}" in
  ""|staging|prod) ;;
  production) env_name="prod" ;;
  *)
    echo "ERROR: --env must be staging or prod" >&2
    exit 2
    ;;
esac

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

section() {
  printf '\n== %s ==\n' "$1"
}

status_line() {
  printf '%-24s %s\n' "$1:" "$2"
}

env_file_for() {
  case "$1" in
    prod) echo "${ROOT_DIR}/.env.prod" ;;
    staging) echo "${ROOT_DIR}/.env.staging" ;;
    *) echo "" ;;
  esac
}

project_for() {
  case "$1" in
    prod) echo "tutordex-prod" ;;
    staging) echo "tutordex-staging" ;;
    *) echo "" ;;
  esac
}

section "surface"
status_line "repo" "${ROOT_DIR}"
status_line "host" "$(hostname 2>/dev/null || echo unknown)"
status_line "kernel" "$(uname -a 2>/dev/null || echo unknown)"
status_line "user" "$(whoami 2>/dev/null || echo unknown)"
status_line "env requested" "${env_name:-none}"
status_line "public url" "${public_url:-none}"

section "git"
if have_cmd git && git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  status_line "branch" "$(git -C "${ROOT_DIR}" branch --show-current 2>/dev/null || echo unknown)"
  status_line "commit" "$(git -C "${ROOT_DIR}" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  dirty_count="$(git -C "${ROOT_DIR}" status --short 2>/dev/null | wc -l | tr -d ' ')"
  status_line "dirty files" "${dirty_count}"
else
  status_line "git" "unavailable"
fi

section "canonical docs"
for path in AGENTS.md docs/OPERATIONS.md docs/SYSTEM_INTERNAL.md TutorDexAggregator/AGENTS.md; do
  if [[ -f "${ROOT_DIR}/${path}" ]]; then
    status_line "${path}" "present"
  else
    status_line "${path}" "missing"
  fi
done

section "env files"
for name in staging prod; do
  env_file="$(env_file_for "${name}")"
  if [[ -f "${env_file}" ]]; then
    status_line ".env.${name}" "present (not sourced/printed by helper)"
  else
    status_line ".env.${name}" "missing"
  fi
done

section "ops scripts"
for path in scripts/ops/status.sh scripts/ops/smoke.sh scripts/ops/logs.sh scripts/ops/restart.sh scripts/ops/rollback.sh; do
  if [[ -x "${ROOT_DIR}/${path}" ]]; then
    status_line "${path}" "executable"
  elif [[ -f "${ROOT_DIR}/${path}" ]]; then
    status_line "${path}" "present, not executable"
  else
    status_line "${path}" "missing"
  fi
done

section "docker"
if [[ "${skip_docker}" == "1" ]]; then
  status_line "docker" "skipped"
elif ! have_cmd docker; then
  status_line "docker" "unavailable"
else
  status_line "context" "$(docker context show 2>/dev/null || echo unknown)"
  if docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
    status_line "server" "$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"
  else
    status_line "server" "unreachable"
  fi

  if [[ -n "${env_name}" ]]; then
    env_file="$(env_file_for "${env_name}")"
    project="$(project_for "${env_name}")"
    if [[ ! -f "${env_file}" ]]; then
      status_line "compose ${env_name}" "unknown (.env file missing)"
    else
      echo "compose project: ${project}"
      docker compose -f "${ROOT_DIR}/docker-compose.yml" -p "${project}" --env-file "${env_file}" ps || true
    fi
  else
    status_line "compose" "not checked (pass --env staging|prod)"
  fi
fi

section "public health"
if [[ -z "${public_url}" ]]; then
  status_line "public /health" "not checked (pass --public-url)"
elif ! have_cmd curl; then
  status_line "curl" "unavailable"
else
  health_url="${public_url%/}/health"
  if body="$(curl -fsS --max-time 10 "${health_url}" 2>/dev/null)"; then
    status_line "${health_url}" "ok"
    printf '%s\n' "${body}" | head -c 500
    printf '\n'
  else
    status_line "${health_url}" "failed"
  fi
fi

section "next steps"
echo "For live ops, pair this with docs/OPERATIONS.md and state the exact surface checked."
echo "For prod changes, use scripts/ops/* with rollback and verification evidence."
