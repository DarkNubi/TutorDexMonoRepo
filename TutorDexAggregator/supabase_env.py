"""
Shared environment helpers for Supabase connectivity.

Goal:
- Allow the same codebase to run both:
  - inside Docker (where `supabase-kong` is resolvable on the `supabase_default` network), and
  - on the host (Windows / macOS / Linux) where Docker-only DNS names are not resolvable.

Env vars (recommended):
- SUPABASE_URL_DOCKER: e.g. http://supabase-kong:8000
- SUPABASE_URL_HOST:  e.g. http://127.0.0.1:54321  (or your public https://<project>.supabase.co)

Fallback:
- SUPABASE_URL is still supported as a single value if you don't need split routing.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def running_in_docker() -> bool:
    # Common marker file used by Docker.
    if Path("/.dockerenv").exists():
        return True
    # Best-effort cgroup check (Linux only). Safe to ignore failures.
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
    """
    Pick the correct Supabase REST base URL for the current runtime.

    Priority:
    - In Docker: SUPABASE_URL_DOCKER, else SUPABASE_URL, else SUPABASE_URL_HOST
    - On host:  SUPABASE_URL_HOST,  else SUPABASE_URL, else SUPABASE_URL_DOCKER
    """
    url = _clean_url(os.environ.get("SUPABASE_URL"))
    url_docker = _clean_url(os.environ.get("SUPABASE_URL_DOCKER"))
    url_host = _clean_url(os.environ.get("SUPABASE_URL_HOST"))

    if running_in_docker():
        return url_docker or url or url_host
    return url_host or url or url_docker


def check_rpc_response(response, rpc_name: str):
    """
    Check Supabase RPC response for errors.
    
    PostgREST returns HTTP 300 when multiple functions match the signature (ambiguous overload).
    This is a silent failure mode that can cause data loss if not detected.
    
    Args:
        response: requests.Response object from Supabase RPC call
        rpc_name: Name of the RPC function being called
        
    Raises:
        ValueError: If RPC returned 300 (ambiguous function overload)
        RuntimeError: If RPC returned 4xx/5xx error
        
    Returns:
        response: The original response object if successful
    """
    if response.status_code == 300:
        raise ValueError(
            f"Supabase RPC '{rpc_name}' returned 300 (ambiguous function overload). "
            "Check for duplicate function definitions in schema. "
            "This usually means multiple functions exist with the same name but different signatures."
        )
    
    if response.status_code >= 400:
        error_body = (response.text or "")[:500]
        raise RuntimeError(
            f"Supabase RPC '{rpc_name}' failed: status={response.status_code} body={error_body}"
        )
    
    return response

