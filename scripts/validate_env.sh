#!/bin/bash
set -euo pipefail

ENV_FILE="${1:-.env.prod}"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Environment file not found: $ENV_FILE"
    exit 1
fi

echo "Validating $ENV_FILE..."

# Source the env file
set -a
source "$ENV_FILE"
set +a

# Validation functions
check_required() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    
    if [ -z "$var_value" ]; then
        echo "  ❌ MISSING: $var_name is required but not set"
        return 1
    else
        echo "  ✅ SET: $var_name"
        return 0
    fi
}

check_prod_ports() {
    local env="${APP_ENV:-dev}"
    
    if [ "$env" == "prod" ]; then
        if [ "${BACKEND_PORT:-8000}" != "8000" ]; then
            echo "  ⚠️  WARNING: Production BACKEND_PORT is not 8000 (found: ${BACKEND_PORT})"
        fi
        if [ "${PROMETHEUS_PORT:-9090}" != "9090" ]; then
            echo "  ⚠️  WARNING: Production PROMETHEUS_PORT is not 9090 (found: ${PROMETHEUS_PORT})"
        fi
    fi
}

check_staging_ports() {
    local env="${APP_ENV:-dev}"
    
    if [ "$env" == "staging" ]; then
        if [ "${BACKEND_PORT:-8001}" == "8000" ]; then
            echo "  ❌ ERROR: Staging BACKEND_PORT conflicts with production (8000)"
            return 1
        fi
        if [ "${PROMETHEUS_PORT:-9091}" == "9090" ]; then
            echo "  ❌ ERROR: Staging PROMETHEUS_PORT conflicts with production (9090)"
            return 1
        fi
    fi
}

check_supabase_url() {
    local env="${APP_ENV:-dev}"
    local url="${SUPABASE_URL:-}"
    
    if [ "$env" == "prod" ] && [[ "$url" == *":54322"* ]]; then
        echo "  ❌ FATAL: Production using staging Supabase port (:54322)"
        return 1
    fi
    
    if [ "$env" == "staging" ] && [[ "$url" == *":54321"* ]] && [[ "$url" != *":54322"* ]]; then
        echo "  ❌ FATAL: Staging using production Supabase port (:54321)"
        return 1
    fi
}

# Run validations
ERRORS=0

echo ""
echo "Required Variables:"
check_required "APP_ENV" || ERRORS=$((ERRORS + 1))
check_required "COMPOSE_PROJECT_NAME" || ERRORS=$((ERRORS + 1))

echo ""
echo "Port Configuration:"
check_prod_ports || ERRORS=$((ERRORS + 1))
check_staging_ports || ERRORS=$((ERRORS + 1))

echo ""
echo "Database Configuration:"
check_supabase_url || ERRORS=$((ERRORS + 1))

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✅ Validation PASSED: $ENV_FILE"
    exit 0
else
    echo "❌ Validation FAILED: $ERRORS error(s) found in $ENV_FILE"
    exit 1
fi
