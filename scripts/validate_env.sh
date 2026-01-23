#!/bin/bash
set -euo pipefail

ENV_FILE="${1:-.env.prod}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: Environment file not found: $ENV_FILE"
  exit 1
fi

echo "Validating $ENV_FILE..."

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

fail=0

check_required() {
  local var_name="$1"
  local var_value="${!var_name:-}"
  if [ -z "$var_value" ]; then
    echo "  MISSING: $var_name"
    fail=1
  else
    echo "  OK: $var_name"
  fi
}

check_required "APP_ENV"
check_required "COMPOSE_PROJECT_NAME"
check_required "BACKEND_PORT"
check_required "PROMETHEUS_PORT"
check_required "ALERTMANAGER_PORT"
check_required "GRAFANA_PORT"
check_required "TEMPO_HTTP_PORT"
check_required "TEMPO_OTLP_GRPC_PORT"
check_required "TEMPO_OTLP_HTTP_PORT"
check_required "SUPABASE_NETWORK"

env="${APP_ENV:-dev}"
if [ "$env" = "prod" ] || [ "$env" = "production" ]; then
  if [ "${BACKEND_PORT:-8000}" != "8000" ]; then
    echo "  WARNING: Production BACKEND_PORT is not 8000 (found: ${BACKEND_PORT})"
  fi
  if [ "${PROMETHEUS_PORT:-9090}" != "9090" ]; then
    echo "  WARNING: Production PROMETHEUS_PORT is not 9090 (found: ${PROMETHEUS_PORT})"
  fi
  if [ "${GRAFANA_PORT:-3300}" != "3300" ]; then
    echo "  WARNING: Production GRAFANA_PORT is not 3300 (found: ${GRAFANA_PORT})"
  fi
elif [ "$env" = "staging" ]; then
  if [ "${BACKEND_PORT:-8000}" = "8000" ]; then
    echo "  WARNING: Staging BACKEND_PORT is 8000; expected alternate port (e.g., 8001)"
  fi
else
  echo "  WARNING: APP_ENV is neither staging nor prod (found: $env)"
fi

if [ "${GRAFANA_ADMIN_PASSWORD:-}" = "admin" ]; then
  echo "  WARNING: GRAFANA_ADMIN_PASSWORD is default 'admin'"
fi
if [ "${GRAFANA_ADMIN_PASSWORD:-}" = "[generate_secure_password]" ]; then
  echo "  WARNING: GRAFANA_ADMIN_PASSWORD still placeholder"
fi

if [ "$fail" -ne 0 ]; then
  echo "Validation FAILED."
  exit 1
fi

echo "Validation PASSED."

