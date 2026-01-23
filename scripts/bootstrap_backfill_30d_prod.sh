#!/usr/bin/env bash
set -euo pipefail

# Bootstrap: backfill N days of Telegram history into Supabase (prod),
# enqueue extraction jobs, and drain the queue WITHOUT broadcast/DM side-effects.
#
# Usage:
#   ./scripts/bootstrap_backfill_30d_prod.sh            # defaults to 30 days
#   ./scripts/bootstrap_backfill_30d_prod.sh 60         # backfill 60 days
#
# Notes:
# - Stops `collector-tail` and `aggregator-worker` to avoid Telethon session conflicts and side effects.
# - Runs `collector.py backfill` as a one-off container (uses prod env file).
# - Runs the worker in oneshot mode with side effects disabled to build assignments safely.

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  sed -n '1,120p' "$0"
  exit 0
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DAYS="${1:-30}"
if ! [[ "$DAYS" =~ ^[0-9]+$ ]] || [[ "$DAYS" -le 0 ]] || [[ "$DAYS" -gt 365 ]]; then
  echo "Invalid DAYS=$DAYS (expected integer 1..365)" >&2
  exit 2
fi

PROJECT="tutordex-prod"
ENV_FILE=".env.prod"

SINCE="$(date -u -d "$DAYS days ago" '+%Y-%m-%dT%H:%M:%S+00:00')"
UNTIL="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"

echo "[bootstrap] project=$PROJECT env_file=$ENV_FILE since=$SINCE until=$UNTIL"

echo "[bootstrap] stopping long-running services (avoid session conflicts / side effects)"
docker compose -p "$PROJECT" --env-file "$ENV_FILE" stop collector-tail aggregator-worker || true

echo "[bootstrap] backfilling raw messages + enqueueing extractions"
docker compose -p "$PROJECT" --env-file "$ENV_FILE" run --rm \
  collector-tail \
  python collector.py backfill --since "$SINCE" --until "$UNTIL"

echo "[bootstrap] draining extraction queue (no broadcast/DM side effects)"
docker compose -p "$PROJECT" --env-file "$ENV_FILE" run --rm \
  -e ENABLE_BROADCAST=0 \
  -e ENABLE_DMS=0 \
  -e EXTRACTION_WORKER_ONESHOT=1 \
  aggregator-worker \
  python workers/extract_worker.py

echo "[bootstrap] restarting long-running services"
docker compose -p "$PROJECT" --env-file "$ENV_FILE" up -d collector-tail aggregator-worker

echo "[bootstrap] done"

