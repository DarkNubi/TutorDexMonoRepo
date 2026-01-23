#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex STAGING ==="

cd "$(dirname "$0")/.."

ENV_FILE=".env.staging"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

./scripts/validate_env.sh "$ENV_FILE"

docker compose -p tutordex-staging pull prometheus alertmanager grafana redis tempo otel-collector || true

docker compose \
  -f docker-compose.yml \
  -p tutordex-staging \
  --env-file "$ENV_FILE" \
  up -d --build

echo "Staging deployment complete."
echo "Backend: http://localhost:8001"
echo "Grafana: http://localhost:3301"
echo "Prometheus: http://localhost:9091"
