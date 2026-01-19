#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex PRODUCTION ==="
echo "WARNING: This will restart production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Change to repo root
cd "$(dirname "$0")/.."

# Validate environment file exists
if [ ! -f .env.prod ]; then
    echo "ERROR: .env.prod not found"
    exit 1
fi

# Pull latest images
docker compose -p tutordex-prod pull prometheus alertmanager grafana redis tempo otel-collector || true

# Build and start services
docker compose \
    -f docker-compose.yml \
    -p tutordex-prod \
    --env-file .env.prod \
    up -d --build

echo "Production deployment complete."
echo "Backend: http://localhost:8000"
echo "Grafana: http://localhost:3300"
echo "Prometheus: http://localhost:9090"
