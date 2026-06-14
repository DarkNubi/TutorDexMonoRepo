#!/bin/bash
set -euo pipefail

ENV_FILE="${1:-.env.prod}"
ENV_DIR="$(cd "$(dirname "$ENV_FILE")" && pwd)"

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

resolve_env_path() {
  local p="$1"
  if [ -z "$p" ]; then
    echo ""
  elif [[ "$p" = /* ]]; then
    echo "$p"
  else
    echo "$ENV_DIR/$p"
  fi
}

check_file_required() {
  local var_name="$1"
  local raw="${!var_name:-}"
  local path
  path="$(resolve_env_path "$raw")"
  if [ -z "$raw" ] || [ ! -f "$path" ]; then
    echo "  MISSING_FILE: $var_name"
    fail=1
  else
    echo "  OK: $var_name"
  fi
}

component_value() {
  local path="$1"
  local var_name="$2"
  python3 - "$path" "$var_name" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
name = sys.argv[2]
if not path.is_file():
    raise SystemExit(0)
for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() != name:
        continue
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    print(value)
    break
PY
}

check_component_required() {
  local label="$1"
  local path="$2"
  local var_name="$3"
  local var_value
  var_value="$(component_value "$path" "$var_name")"
  if [ -z "$var_value" ]; then
    echo "  MISSING: ${label}.${var_name}"
    fail=1
  else
    echo "  OK: ${label}.${var_name}"
  fi
}

check_component_true() {
  local label="$1"
  local path="$2"
  local var_name="$3"
  local var_value
  var_value="$(component_value "$path" "$var_name")"
  case "${var_value,,}" in
    true|1|yes|on)
      echo "  OK: ${label}.${var_name}"
      ;;
    *)
      echo "  INVALID: ${label}.${var_name} must be true"
      fail=1
      ;;
  esac
}

check_component_not_true() {
  local label="$1"
  local path="$2"
  local var_name="$3"
  local var_value
  var_value="$(component_value "$path" "$var_name")"
  case "${var_value,,}" in
    true|1|yes|on)
      echo "  INVALID: ${label}.${var_name} must not be true in staging"
      fail=1
      ;;
    *)
      echo "  OK: ${label}.${var_name} staging-safe"
      ;;
  esac
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
check_required "AGGREGATOR_ENV_FILE"
check_required "BACKEND_ENV_FILE"
check_required "FIREBASE_ADMIN_JSON"
check_file_required "AGGREGATOR_ENV_FILE"
check_file_required "BACKEND_ENV_FILE"
check_file_required "FIREBASE_ADMIN_JSON"

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
  case "${SUPABASE_NETWORK:-}" in
    *staging*) ;;
    *)
      echo "  INVALID: Staging SUPABASE_NETWORK must be staging-specific"
      fail=1
      ;;
  esac
else
  echo "  WARNING: APP_ENV is neither staging nor prod (found: $env)"
fi

if [ "$env" = "prod" ] || [ "$env" = "production" ] || [ "$env" = "staging" ]; then
  aggregator_env_path="$(resolve_env_path "${AGGREGATOR_ENV_FILE:-}")"
  backend_env_path="$(resolve_env_path "${BACKEND_ENV_FILE:-}")"

  if [ -f "$backend_env_path" ]; then
    check_component_true "backend" "$backend_env_path" "SUPABASE_ENABLED"
    check_component_required "backend" "$backend_env_path" "SUPABASE_URL_DOCKER"
    check_component_required "backend" "$backend_env_path" "SUPABASE_URL_HOST"
    check_component_required "backend" "$backend_env_path" "SUPABASE_SERVICE_ROLE_KEY"
    check_component_required "backend" "$backend_env_path" "REDIS_URL"
    check_component_required "backend" "$backend_env_path" "ADMIN_API_KEY"
  fi

  if [ -f "$aggregator_env_path" ]; then
    check_component_true "aggregator" "$aggregator_env_path" "SUPABASE_ENABLED"
    check_component_true "aggregator" "$aggregator_env_path" "SUPABASE_RAW_ENABLED"
    check_component_required "aggregator" "$aggregator_env_path" "SUPABASE_URL_DOCKER"
    check_component_required "aggregator" "$aggregator_env_path" "SUPABASE_URL_HOST"
    check_component_required "aggregator" "$aggregator_env_path" "SUPABASE_SERVICE_ROLE_KEY"
    check_component_required "aggregator" "$aggregator_env_path" "CHANNEL_LIST"
    check_component_required "aggregator" "$aggregator_env_path" "TELEGRAM_API_ID"
    check_component_required "aggregator" "$aggregator_env_path" "TELEGRAM_API_HASH"
    check_component_required "aggregator" "$aggregator_env_path" "SESSION_STRING"
    check_component_required "aggregator" "$aggregator_env_path" "EXTRACTION_PIPELINE_VERSION"
    check_component_required "aggregator" "$aggregator_env_path" "SCHEMA_VERSION"
    check_component_required "aggregator" "$aggregator_env_path" "DM_BOT_TOKEN"
    check_component_required "aggregator" "$aggregator_env_path" "ALERT_CHAT_ID"
    alert_bot_token="$(component_value "$aggregator_env_path" "ALERT_BOT_TOKEN")"
    group_bot_token="$(component_value "$aggregator_env_path" "GROUP_BOT_TOKEN")"
    if [ -z "$alert_bot_token" ] && [ -z "$group_bot_token" ]; then
      echo "  MISSING: aggregator.ALERT_BOT_TOKEN or aggregator.GROUP_BOT_TOKEN"
      fail=1
    else
      echo "  OK: aggregator.ALERT_BOT_TOKEN or aggregator.GROUP_BOT_TOKEN"
    fi
    if [ "$env" = "staging" ]; then
      check_component_not_true "aggregator" "$aggregator_env_path" "ENABLE_BROADCAST"
      check_component_not_true "aggregator" "$aggregator_env_path" "ENABLE_DMS"
      check_component_not_true "aggregator" "$aggregator_env_path" "DM_ENABLED"
      check_component_not_true "aggregator" "$aggregator_env_path" "BROADCAST_SYNC_ON_STARTUP"
      check_component_not_true "aggregator" "$aggregator_env_path" "FRESHNESS_PROPAGATE_TELEGRAM_ENABLED"
      check_component_not_true "aggregator" "$aggregator_env_path" "FRESHNESS_DELETE_EXPIRED_TELEGRAM_ENABLED"
    fi
  fi
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
