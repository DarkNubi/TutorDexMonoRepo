#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, Optional, Tuple


def _env_first(*names: str) -> Optional[str]:
    for name in names:
        v = os.environ.get(name)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


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


def _require_requests():
    try:
        import requests  # type: ignore

        return requests
    except Exception:
        print("FAIL: python dependency missing: requests")
        print("Install with: pip install requests")
        raise SystemExit(2)


def _http_get(url: str, *, timeout_s: int = 10) -> Tuple[bool, str]:
    requests = _require_requests()
    try:
        resp = requests.get(url, timeout=timeout_s)
        ok = resp.status_code < 400
        return ok, f"status={resp.status_code}"
    except Exception as e:
        return False, f"error={e}"


def _supabase_rpc(supabase_url: str, supabase_key: str, fn: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
    requests = _require_requests()
    url = _join_url(supabase_url, f"rest/v1/rpc/{fn}")
    headers = {"apikey": supabase_key, "authorization": f"Bearer {supabase_key}", "content-type": "application/json"}
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=20)
        ok = resp.status_code < 400
        detail = f"status={resp.status_code}"
        if not ok:
            detail += f" body={resp.text[:300]}"
        return ok, detail
    except Exception as e:
        return False, f"error={e}"


def main() -> int:
    p = argparse.ArgumentParser(description="TutorDex smoke test (backend + deps + key RPCs).")
    p.add_argument("--backend-url", default=_env_first("BACKEND_URL") or "http://127.0.0.1:8000", help="Backend base URL.")
    p.add_argument(
        "--supabase-url",
        default=_env_first("SUPABASE_URL_HOST", "SUPABASE_URL_DOCKER", "SUPABASE_URL"),
        help="Supabase base URL (no /rest/v1 suffix).",
    )
    p.add_argument("--supabase-key", default=_env_first("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_KEY"), help="Supabase key for RPC checks.")
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

