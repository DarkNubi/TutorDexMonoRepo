#!/usr/bin/env bash
set -euo pipefail

source "$(dirname "$0")/_lib.sh"

env="$(resolve_env "$@")"
source_env_file_for "${env}"

fn="${TD_RPC_FN:-}"
payload="${TD_RPC_JSON:-{} }"

for i in "$@"; do
  if [[ "$i" == "--fn="* ]]; then
    fn="${i#--fn=}"
  elif [[ "$i" == "--json="* ]]; then
    payload="${i#--json=}"
  fi
done

if [[ -z "${fn}" ]]; then
  die "Missing --fn=<rpc_name> (or TD_RPC_FN)"
fi

# Default local Kong ports for self-hosted Supabase.
base_url="${SUPABASE_URL:-}"
if [[ -z "${base_url}" ]]; then
  if [[ "${env}" == "prod" ]]; then
    base_url="http://127.0.0.1:54321"
  else
    base_url="http://127.0.0.1:54322"
  fi
fi
base_url="${base_url%/}"

api_key="${SUPABASE_API_KEY:-${SUPABASE_ANON_KEY:-}}"
if [[ -z "${api_key}" ]]; then
  die "Missing SUPABASE_API_KEY (recommended: Supabase anon key)."
fi

# Guardrail: refuse using service_role as the Kong api key unless explicitly allowed.
if [[ "${api_key}" == *.*.* ]]; then
  role="$(TD_API_KEY="${api_key}" python3 - <<'PY' 2>/dev/null || true
import base64, json, os, sys
t = os.environ.get("TD_API_KEY","")
parts = t.split(".")
if len(parts) != 3:
    raise SystemExit(0)
payload = parts[1] + "==="
payload = payload.replace("-", "+").replace("_", "/")
try:
    data = base64.b64decode(payload.encode("ascii"))
    obj = json.loads(data.decode("utf-8", errors="ignore"))
    print(str(obj.get("role") or ""))
except Exception:
    pass
PY
)"
  if [[ "${role}" == "service_role" && "${ALLOW_SERVICE_ROLE_APIKEY:-}" != "yes" ]]; then
    die "Refusing SUPABASE_API_KEY with role=service_role. Use the anon key instead (or set ALLOW_SERVICE_ROLE_APIKEY=yes)."
  fi
fi

token="${SUPABASE_OPS_AGENT_JWT:-}"
if [[ -z "${token}" ]]; then
  secret="${SUPABASE_JWT_SECRET:-${SUPABASE_OPS_AGENT_JWT_SECRET:-}}"
  if [[ -z "${secret}" ]]; then
    die "Missing SUPABASE_OPS_AGENT_JWT or SUPABASE_JWT_SECRET."
  fi
  ttl="${SUPABASE_OPS_AGENT_JWT_TTL_SECONDS:-3600}"
  token="$(python3 scripts/ops/generate_supabase_ops_jwt.py --secret "${secret}" --ttl-seconds "${ttl}")"
fi

audit_log "supabase_rpc" "${env}" "$@"

url="${base_url}/rest/v1/rpc/${fn}"
curl -fsS \
  -H "apikey: ${api_key}" \
  -H "Authorization: Bearer ${token}" \
  -H "Content-Type: application/json" \
  --data "${payload}" \
  "${url}"
