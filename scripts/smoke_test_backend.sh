#!/usr/bin/env bash
set -euo pipefail

backend_url="${BACKEND_URL:-http://127.0.0.1:8000}"
supabase_url="${SUPABASE_URL:-${SUPABASE_URL_HOST:-${SUPABASE_URL_DOCKER:-}}}"
supabase_key="${SUPABASE_SERVICE_ROLE_KEY:-${SUPABASE_KEY:-}}"

echo "TutorDex smoke test: backend"
echo "  BACKEND_URL=${backend_url}"

args=(--backend-url "${backend_url}")
if [[ -n "${supabase_url}" && -n "${supabase_key}" ]]; then
  echo "  SUPABASE_URL=${supabase_url}"
  args+=(--supabase-url "${supabase_url}" --supabase-key "${supabase_key}")
else
  echo "  SUPABASE_URL/SUPABASE_KEY not set; skipping direct Supabase RPC checks"
  args+=(--skip-supabase-rpcs)
fi

python3 scripts/smoke_test.py "${args[@]}"

