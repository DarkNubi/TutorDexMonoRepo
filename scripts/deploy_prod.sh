#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex PRODUCTION ==="
echo "WARNING: This will restart production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "Deployment cancelled."
  exit 0
fi

cd "$(dirname "$0")/.."

ENV_FILE=".env.prod"
if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

./scripts/validate_env.sh "$ENV_FILE"

docker compose -p tutordex-prod pull prometheus alertmanager grafana redis tempo otel-collector || true

docker compose \
  -f docker-compose.yml \
  -p tutordex-prod \
  --env-file "$ENV_FILE" \
  up -d --build

echo "Production deployment complete."
echo "Backend: http://localhost:8000"
echo "Grafana: http://localhost:3300"
echo "Prometheus: http://localhost:9090"
