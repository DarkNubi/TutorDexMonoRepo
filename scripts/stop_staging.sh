#!/bin/bash
set -euo pipefail

echo "=== Stopping TutorDex STAGING ==="

cd "$(dirname "$0")/.."

docker compose \
  -f docker-compose.yml \
  -p tutordex-staging \
  --env-file .env.staging \
  down

echo "Staging stopped."
