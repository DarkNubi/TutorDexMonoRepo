#!/bin/bash
set -euo pipefail

echo "=== Stopping TutorDex PRODUCTION ==="
echo "WARNING: This will stop production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
  echo "Operation cancelled."
  exit 0
fi

cd "$(dirname "$0")/.."

docker compose \
  -f docker-compose.yml \
  -p tutordex-prod \
  --env-file .env.prod \
  down

echo "Production stopped."
