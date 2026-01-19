#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex STAGING ==="

# Change to repo root
cd "$(dirname "$0")/.."

# Validate environment file exists
if [ ! -f .env.staging ]; then
    echo "ERROR: .env.staging not found"
    exit 1
fi

# Pull latest images (optional, for base images)
docker compose -p tutordex-staging pull prometheus alertmanager grafana redis tempo otel-collector || true

# Build and start services
docker compose \
    -f docker-compose.yml \
    -p tutordex-staging \
    --env-file .env.staging \
    up -d --build

echo "Staging deployment complete."
echo "Backend: http://localhost:8001"
echo "Grafana: http://localhost:3301"
echo "Prometheus: http://localhost:9091"
