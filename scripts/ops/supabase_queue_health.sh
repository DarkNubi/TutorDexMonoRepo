#!/usr/bin/env bash
set -euo pipefail

env="${TD_ENV:-}"
if [[ -z "${env}" ]]; then
  env="staging"
fi

exec "$(dirname "$0")/supabase_rpc.sh" --env "${env}" --fn=ops_queue_health --json='{}'

