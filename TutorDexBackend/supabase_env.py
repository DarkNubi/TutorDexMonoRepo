"""
Supabase environment helpers (backend).

Supports a split configuration so the same repo can run:
- inside Docker (where `supabase-kong` is resolvable on the `supabase_default` network), and
- on the host (Windows/macOS/Linux) where Docker-only DNS names are not resolvable.

Env vars (recommended):
- SUPABASE_URL_DOCKER: e.g. http://supabase-kong:8000
- SUPABASE_URL_HOST:  e.g. http://127.0.0.1:54321 (or https://<project-ref>.supabase.co)

Fallback:
- SUPABASE_URL is still supported as a single value.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def running_in_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        p = Path("/proc/1/cgroup")
        if p.exists():
            s = p.read_text(encoding="utf-8", errors="ignore")
            if "docker" in s or "containerd" in s or "kubepods" in s:
                return True
    except Exception:
        pass
    return False


def _clean_url(value: Optional[str]) -> str:
    return (value or "").strip().rstrip("/")


def resolve_supabase_url() -> str:
    url = _clean_url(os.environ.get("SUPABASE_URL"))
    url_docker = _clean_url(os.environ.get("SUPABASE_URL_DOCKER"))
    url_host = _clean_url(os.environ.get("SUPABASE_URL_HOST"))

    if running_in_docker():
        return url_docker or url or url_host
    return url_host or url or url_docker

