#!/usr/bin/env bash
set -euo pipefail

prom_url="${PROMETHEUS_URL:-http://127.0.0.1:9090/-/ready}"
alert_url="${ALERTMANAGER_URL:-http://127.0.0.1:9093/-/ready}"
grafana_url="${GRAFANA_URL:-http://127.0.0.1:3300/api/health}"

echo "TutorDex smoke test: observability"
echo "  PROMETHEUS_URL=${prom_url}"
echo "  ALERTMANAGER_URL=${alert_url}"
echo "  GRAFANA_URL=${grafana_url}"

python3 - <<'PY'
import os

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

urls = [
    os.environ.get("PROMETHEUS_URL", "http://127.0.0.1:9090/-/ready"),
    os.environ.get("ALERTMANAGER_URL", "http://127.0.0.1:9093/-/ready"),
    os.environ.get("GRAFANA_URL", "http://127.0.0.1:3300/api/health"),
]

oks = [check(u) for u in urls]
raise SystemExit(0 if all(oks) else 1)
PY

