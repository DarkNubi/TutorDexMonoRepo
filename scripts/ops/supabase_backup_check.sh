#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage:
  scripts/ops/supabase_backup_check.sh [--env prod|staging] [--database NAME] [--backup-dir DIR]
                                      [--max-age-hours HOURS] [--min-bytes BYTES]
                                      [--container NAME] [--prometheus-file PATH]

Environment:
  TD_BACKUP_DIR                 Backup directory, default: $HOME/backups/tutordex/supabase.
  TD_PGDATABASE                 Database name, default: postgres.
  TD_SUPABASE_DB_CONTAINER      Optional Supabase DB container override.

Checks the newest TutorDex Supabase custom-format dump for:
  - existence
  - max age
  - minimum size
  - pg_restore --list readability

This script does not read or print env files, connection strings, passwords, or tokens.
EOF
}

die() {
  echo "CRITICAL: $*" >&2
  exit 2
}

env="${TD_ENV:-prod}"
database="${TD_PGDATABASE:-postgres}"
backup_dir="${TD_BACKUP_DIR:-${HOME}/backups/tutordex/supabase}"
max_age_hours="${TD_BACKUP_MAX_AGE_HOURS:-26}"
min_bytes="${TD_BACKUP_MIN_BYTES:-1024}"
container="${TD_SUPABASE_DB_CONTAINER:-}"
prometheus_file=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env)
      shift
      env="${1:-}"
      ;;
    --env=*)
      env="${1#--env=}"
      ;;
    --database)
      shift
      database="${1:-}"
      ;;
    --database=*)
      database="${1#--database=}"
      ;;
    --backup-dir|--output-dir)
      shift
      backup_dir="${1:-}"
      ;;
    --backup-dir=*|--output-dir=*)
      backup_dir="${1#*=}"
      ;;
    --max-age-hours)
      shift
      max_age_hours="${1:-}"
      ;;
    --max-age-hours=*)
      max_age_hours="${1#--max-age-hours=}"
      ;;
    --min-bytes)
      shift
      min_bytes="${1:-}"
      ;;
    --min-bytes=*)
      min_bytes="${1#--min-bytes=}"
      ;;
    --container)
      shift
      container="${1:-}"
      ;;
    --container=*)
      container="${1#--container=}"
      ;;
    --prometheus-file)
      shift
      prometheus_file="${1:-}"
      ;;
    --prometheus-file=*)
      prometheus_file="${1#--prometheus-file=}"
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

case "${env}" in
  prod|production) env="prod" ;;
  staging) env="staging" ;;
  *) die "Invalid --env: ${env}" ;;
esac

[[ "${max_age_hours}" =~ ^[0-9]+$ ]] || die "--max-age-hours must be a positive integer"
[[ "${min_bytes}" =~ ^[0-9]+$ ]] || die "--min-bytes must be a positive integer"
[[ -d "${backup_dir}" ]] || die "Backup directory not found: ${backup_dir}"

pattern="tutordex-${env}-supabase-${database}-*.dump"
latest="$(
  find "${backup_dir}" -maxdepth 1 -type f -name "${pattern}" -printf '%T@ %p\n' 2>/dev/null \
    | sort -nr \
    | awk 'NR == 1 { sub(/^[^ ]+ /, ""); print }'
)"

[[ -n "${latest}" ]] || die "No backup dump found in ${backup_dir} matching ${pattern}"

now_epoch="$(date +%s)"
mtime_epoch="$(stat -c %Y "${latest}")"
age_seconds=$((now_epoch - mtime_epoch))
max_age_seconds=$((max_age_hours * 3600))
bytes="$(wc -c < "${latest}" | tr -d ' ')"

status=0
reason="ok"

if (( bytes < min_bytes )); then
  status=2
  reason="too_small"
elif (( age_seconds > max_age_seconds )); then
  status=2
  reason="too_old"
fi

verify_method=""
if (( status == 0 )); then
  if command -v pg_restore >/dev/null 2>&1; then
    if pg_restore --list "${latest}" >/dev/null; then
      verify_method="local_pg_restore"
    else
      status=2
      reason="pg_restore_list_failed"
    fi
  else
    if [[ -z "${container}" ]] && command -v docker >/dev/null 2>&1; then
      expected_suffix="supabase-${env}"
      mapfile -t candidates < <(
        docker ps --format '{{.Names}}\t{{.Image}}' \
          | awk -v suffix="${expected_suffix}" '
              BEGIN { IGNORECASE = 1 }
              index($1, "supabase_db_") == 1 && index($1, suffix) > 0 && $2 ~ /postgres/ { print $1 }
            '
      )
      if [[ "${#candidates[@]}" -eq 1 ]]; then
        container="${candidates[0]}"
      fi
    fi

    if [[ -z "${container}" ]]; then
      status=2
      reason="pg_restore_unavailable"
    else
    tmp_path="/tmp/tutordex-backup-check-$$.dump"
    cleanup() {
      docker exec "${container}" rm -f "${tmp_path}" >/dev/null 2>&1 || true
    }
    trap cleanup EXIT
    docker cp "${latest}" "${container}:${tmp_path}" >/dev/null
    if docker exec "${container}" pg_restore --list "${tmp_path}" >/dev/null; then
      verify_method="container_pg_restore"
    else
      status=2
      reason="container_pg_restore_list_failed"
    fi
    fi
  fi
fi

if [[ -n "${prometheus_file}" ]]; then
  mkdir -p "$(dirname "${prometheus_file}")"
  tmp_prom="${prometheus_file}.tmp"
  cat > "${tmp_prom}" <<EOF
# HELP tutordex_supabase_backup_fresh Backup freshness/readability status; 1 is healthy.
# TYPE tutordex_supabase_backup_fresh gauge
tutordex_supabase_backup_fresh{env="${env}",database="${database}",reason="${reason}"} $([[ "${status}" == "0" ]] && echo 1 || echo 0)
# HELP tutordex_supabase_backup_age_seconds Age of the newest matching backup artifact.
# TYPE tutordex_supabase_backup_age_seconds gauge
tutordex_supabase_backup_age_seconds{env="${env}",database="${database}"} ${age_seconds}
# HELP tutordex_supabase_backup_bytes Size of the newest matching backup artifact.
# TYPE tutordex_supabase_backup_bytes gauge
tutordex_supabase_backup_bytes{env="${env}",database="${database}"} ${bytes}
EOF
  mv "${tmp_prom}" "${prometheus_file}"
fi

if (( status == 0 )); then
  echo "OK: latest backup is fresh and readable (${latest}, age_seconds=${age_seconds}, bytes=${bytes}, verify=${verify_method})"
  exit 0
fi

echo "CRITICAL: latest backup check failed (${latest}, reason=${reason}, age_seconds=${age_seconds}, bytes=${bytes})" >&2
exit "${status}"
