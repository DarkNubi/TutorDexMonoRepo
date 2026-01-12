"""
Supabase client configuration and REST client wrapper.

Extracted from supabase_persist.py.
Provides configuration dataclass and HTTP client for Supabase REST API.
"""

import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests

try:
    from supabase_env import resolve_supabase_url  # type: ignore
except Exception:
    from TutorDexAggregator.supabase_env import resolve_supabase_url  # type: ignore

try:
    from utils.field_coercion import truthy
except Exception:
    from TutorDexAggregator.utils.field_coercion import truthy

logger = logging.getLogger("supabase_persist")


@dataclass
class SupabaseConfig:
    """Configuration for Supabase persistence."""
    url: str
    key: str
    assignments_table: str = "assignments"
    enabled: bool = False
    bump_min_seconds: int = 6 * 60 * 60  # 6 hours


def load_config_from_env() -> SupabaseConfig:
    """
    Load Supabase configuration from environment variables.
    
    Environment variables:
    - SUPABASE_URL or docker-compose resolved URL
    - SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
    - SUPABASE_ASSIGNMENTS_TABLE (default: "assignments")
    - SUPABASE_ENABLED (must be truthy)
    - SUPABASE_BUMP_MIN_SECONDS (default: 21600 = 6 hours)
    """
    url = resolve_supabase_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    assignments_table = (os.environ.get("SUPABASE_ASSIGNMENTS_TABLE") or "assignments").strip()
    enabled = truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key and assignments_table)
    bump_min_seconds = int(os.environ.get("SUPABASE_BUMP_MIN_SECONDS") or str(6 * 60 * 60))
    return SupabaseConfig(
        url=url,
        key=key,
        assignments_table=assignments_table,
        enabled=enabled,
        bump_min_seconds=bump_min_seconds,
    )


class SupabaseRestClient:
    """
    HTTP client for Supabase REST API.
    
    Wraps requests.Session with Supabase authentication headers.
    """
    
    def __init__(self, cfg: SupabaseConfig):
        self.cfg = cfg
        self.base = f"{cfg.url}/rest/v1"
        self.session = requests.Session()
        try:
            host = (urlparse(cfg.url).hostname or "").lower()
            if host in {"127.0.0.1", "localhost", "::1"}:
                self.session.trust_env = False
        except Exception:
            pass
        self.session.headers.update(
            {
                "apikey": cfg.key,
                "authorization": f"Bearer {cfg.key}",
                "content-type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        """Construct full URL from path."""
        return f"{self.base}/{path.lstrip('/')}"

    def get(self, path: str, *, timeout: int = 15) -> requests.Response:
        """Execute GET request."""
        return self.session.get(self._url(path), timeout=timeout)

    def post(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        """Execute POST request."""
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.post(self._url(path), json=json_body, headers=headers, timeout=timeout)

    def patch(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        """Execute PATCH request."""
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.patch(self._url(path), json=json_body, headers=headers, timeout=timeout)


def coerce_rows(resp: requests.Response) -> List[Dict[str, Any]]:
    """
    Extract list of rows from Supabase REST response.
    
    Returns empty list if response is not valid JSON or not a list.
    """
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []
