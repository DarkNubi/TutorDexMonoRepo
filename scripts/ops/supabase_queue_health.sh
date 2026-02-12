#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"

exec "$(dirname "$0")/supabase_rpc.sh" --env "${env}" --fn=ops_queue_health --json='{}'
