#!/usr/bin/env bash
set -euo pipefail

worker_health_url="${AGG_WORKER_HEALTH_URL:-http://127.0.0.1:9002/health/worker}"
deps_health_url="${AGG_WORKER_DEPS_URL:-http://127.0.0.1:9002/health/dependencies}"

echo "TutorDex smoke test: aggregator (worker health endpoints)"
echo "  AGG_WORKER_HEALTH_URL=${worker_health_url}"
echo "  AGG_WORKER_DEPS_URL=${deps_health_url}"

python3 - <<'PY'
import os
import sys

def _require_requests():
    try:
        import requests  # type: ignore
        return requests
    except Exception:
        print("SKIP: python dependency missing: requests")
        print("Install with: pip install requests")
        raise SystemExit(2)

def check(url: str) -> bool:
    requests = _require_requests()
    try:
        r = requests.get(url, timeout=10)
        ok = r.status_code < 300
        print(("OK" if ok else "FAIL") + f": GET {url} status={r.status_code}")
        return ok
    except Exception as e:
        print(f"FAIL: GET {url} error={e}")
        return False

worker_url = os.environ.get("AGG_WORKER_HEALTH_URL", "http://127.0.0.1:9002/health/worker")
deps_url = os.environ.get("AGG_WORKER_DEPS_URL", "http://127.0.0.1:9002/health/dependencies")

ok1 = check(worker_url)
ok2 = check(deps_url)
raise SystemExit(0 if (ok1 and ok2) else 1)
PY

