#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from shared.config import load_aggregator_config, load_backend_config
except Exception:
    load_aggregator_config = None  # type: ignore[assignment]
    load_backend_config = None  # type: ignore[assignment]


def _join_url(base: str, path: str) -> str:
    b = str(base or "").rstrip("/")
    p = str(path or "").lstrip("/")
    return f"{b}/{p}"


def _print_result(ok: bool, name: str, detail: str = "") -> None:
    status = "OK" if ok else "FAIL"
    msg = f"{status}: {name}"
    if detail:
        msg += f" ({detail})"
    print(msg)


def _http_get(url: str, *, timeout_s: int = 10) -> Tuple[bool, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            ok = status < 300
            return ok, f"status={status}"
    except urllib.error.HTTPError as e:
        return False, f"status={getattr(e, 'code', 'unknown')}"
    except Exception as e:
        return False, f"error={e}"


def _supabase_rpc(supabase_url: str, supabase_key: str, fn: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    url = _join_url(supabase_url, f"rest/v1/rpc/{fn}")
    headers = {"apikey": supabase_key, "authorization": f"Bearer {supabase_key}", "content-type": "application/json"}
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=20) as resp:
            status = int(getattr(resp, "status", 200) or 200)
            ok = status < 300
            return ok, f"status={status}"
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="ignore")[:300] if hasattr(e, "read") else ""
        except Exception:
            body = ""
        detail = f"status={getattr(e, 'code', 'unknown')}"
        if body:
            detail += f" body={body}"
        return False, detail
    except Exception as e:
        return False, f"error={e}"


def main() -> int:
    default_backend_url = "http://127.0.0.1:8000"
    default_supabase_url: Optional[str] = None
    default_supabase_key: Optional[str] = None

    if callable(load_backend_config) and callable(load_aggregator_config):
        cfg_backend = load_backend_config()
        cfg_agg = load_aggregator_config()
        default_backend_url = str(getattr(cfg_backend, "backend_url", "") or "").strip() or default_backend_url
        default_supabase_url = (
            str(getattr(cfg_backend, "supabase_rest_url", "") or "").strip()
            or str(getattr(cfg_agg, "supabase_rest_url", "") or "").strip()
            or None
        )
        default_supabase_key = (
            str(getattr(cfg_backend, "supabase_auth_key", "") or "").strip()
            or str(getattr(cfg_agg, "supabase_auth_key", "") or "").strip()
            or None
        )
    else:
        # Minimal mode: avoid pydantic-settings dependency; use env vars only.
        default_backend_url = str(os.environ.get("BACKEND_URL") or "").strip() or default_backend_url
        default_supabase_url = (
            str(os.environ.get("SUPABASE_URL") or "").strip()
            or str(os.environ.get("SUPABASE_URL_HOST") or "").strip()
            or str(os.environ.get("SUPABASE_URL_DOCKER") or "").strip()
            or None
        )
        default_supabase_key = (
            str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
            or str(os.environ.get("SUPABASE_KEY") or "").strip()
            or None
        )

    p = argparse.ArgumentParser(description="TutorDex smoke test (backend + deps + key RPCs).")
    p.add_argument("--backend-url", default=default_backend_url, help="Backend base URL.")
    p.add_argument(
        "--supabase-url",
        default=default_supabase_url,
        help="Supabase base URL (no /rest/v1 suffix).",
    )
    p.add_argument("--supabase-key", default=default_supabase_key, help="Supabase key for RPC checks.")
    p.add_argument("--skip-supabase-rpcs", action="store_true", help="Skip direct Supabase RPC checks.")
    args = p.parse_args()

    ok_all = True
    backend = str(args.backend_url).strip().rstrip("/")
    if not backend:
        print("FAIL: backend url is empty")
        return 2

    checks = [
        ("backend /health", _join_url(backend, "health")),
        ("backend /health/redis", _join_url(backend, "health/redis")),
        ("backend /health/supabase", _join_url(backend, "health/supabase")),
    ]
    for name, url in checks:
        ok, detail = _http_get(url)
        _print_result(ok, name, detail)
        ok_all = ok_all and ok

    # Optional: confirm required DB RPCs exist by calling them directly via PostgREST.
    supabase_url = str(args.supabase_url or "").strip().rstrip("/") if args.supabase_url else ""
    supabase_key = str(args.supabase_key or "").strip() if args.supabase_key else ""
    if args.skip_supabase_rpcs:
        _print_result(True, "supabase rpcs", "skipped")
    elif not supabase_url or not supabase_key:
        _print_result(False, "supabase rpcs", "missing SUPABASE_URL_* or SUPABASE_SERVICE_ROLE_KEY")
        ok_all = False
    else:
        ok, detail = _supabase_rpc(supabase_url, supabase_key, "list_open_assignments_v2", {"p_limit": 1, "p_sort": "newest"})
        _print_result(ok, "rpc list_open_assignments_v2", detail)
        ok_all = ok_all and ok

        ok, detail = _supabase_rpc(supabase_url, supabase_key, "open_assignment_facets", {})
        _print_result(ok, "rpc open_assignment_facets", detail)
        ok_all = ok_all and ok

    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
