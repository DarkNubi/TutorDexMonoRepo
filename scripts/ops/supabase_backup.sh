#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/ops/supabase_backup.sh [--env prod|staging] [--container NAME] [--database NAME] [--output-dir DIR] [--dry-run]

Environment:
  TD_SUPABASE_DB_CONTAINER  Override Supabase Postgres container name.
  TD_PGDATABASE             Database name, default: postgres.
  TD_PGUSER                 Database user, default: postgres.
  TD_BACKUP_DIR             Output directory, default: $HOME/backups/tutordex/supabase.

Creates a PostgreSQL custom-format dump with pg_dump inside the Supabase DB container.
The script does not read or print env files, connection strings, passwords, or tokens.
EOF
}

env=""
container="${TD_SUPABASE_DB_CONTAINER:-}"
database="${TD_PGDATABASE:-postgres}"
pguser="${TD_PGUSER:-postgres}"
backup_dir="${TD_BACKUP_DIR:-${HOME}/backups/tutordex/supabase}"
dry_run=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      shift
      env="${1:-}"
      ;;
    --env=*)
      env="${1#--env=}"
      ;;
    --container)
      shift
      container="${1:-}"
      ;;
    --container=*)
      container="${1#--container=}"
      ;;
    --database)
      shift
      database="${1:-}"
      ;;
    --database=*)
      database="${1#--database=}"
      ;;
    --output-dir)
      shift
      backup_dir="${1:-}"
      ;;
    --output-dir=*)
      backup_dir="${1#--output-dir=}"
      ;;
    --dry-run)
      dry_run=1
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      die "Unknown argument: $1"
      ;;
  esac
  shift
done

if [[ -z "${env}" ]]; then
  env="${TD_ENV:-prod}"
fi

case "${env}" in
  prod|production) env="prod" ;;
  staging) env="staging" ;;
  *) usage; die "Invalid --env: ${env}" ;;
esac

if [[ -z "${container}" ]]; then
  expected_suffix="supabase-${env}"
  mapfile -t candidates < <(
    docker ps --format '{{.Names}}\t{{.Image}}' \
      | awk -v suffix="${expected_suffix}" '
          BEGIN { IGNORECASE = 1 }
          index($1, "supabase_db_") == 1 && index($1, suffix) > 0 && $2 ~ /postgres/ { print $1 }
        '
  )
  if [[ "${#candidates[@]}" -ne 1 ]]; then
    die "Could not auto-detect one Supabase Postgres container for ${env}; pass --container or TD_SUPABASE_DB_CONTAINER."
  fi
  container="${candidates[0]}"
fi

timestamp="$(date -u +"%Y%m%dT%H%M%SZ")"
artifact="tutordex-${env}-supabase-${database}-${timestamp}.dump"
tmp_path="/tmp/${artifact}"
local_path="${backup_dir%/}/${artifact}"

audit_log "supabase_backup" "${env}" "--container=${container}" "--database=${database}" "--output-dir=${backup_dir}" "$([[ "${dry_run}" == "1" ]] && echo "--dry-run")"

if [[ "${dry_run}" == "1" ]]; then
  echo "Would create custom-format pg_dump from container '${container}' database '${database}'."
  echo "Would write artifact to: ${local_path}"
  exit 0
fi

mkdir -p "${backup_dir}"
chmod 700 "${backup_dir}" 2>/dev/null || true

cleanup() {
  docker exec "${container}" rm -f "${tmp_path}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Creating custom-format pg_dump from container '${container}' database '${database}'."
docker exec "${container}" pg_dump -Fc --no-owner --no-acl -U "${pguser}" -d "${database}" -f "${tmp_path}"
docker exec "${container}" pg_restore --list "${tmp_path}" >/dev/null
docker cp "${container}:${tmp_path}" "${local_path}"
chmod 600 "${local_path}"

bytes="$(wc -c < "${local_path}" | tr -d ' ')"
echo "Backup artifact: ${local_path}"
echo "Backup bytes: ${bytes}"
echo "Verified: pg_restore --list succeeded inside ${container}."
