"""
Caching and rate limiting service.

Handles public endpoint rate limiting and response caching.
"""
import time
import json
import asyncio
import logging
from typing import Any, Dict, List, Tuple, Optional
from fastapi import HTTPException, Request
from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.utils.request_utils import get_client_ip, hash_ip, build_cache_key
from TutorDexBackend.utils.config_utils import (
    get_redis_prefix,
    get_public_rpm_assignments,
    get_public_rpm_facets,
    get_public_cache_ttl_assignments_s,
    get_public_cache_ttl_facets_s,
    get_public_assignments_limit_cap,
)
from shared.observability.exception_handler import swallow_exception

logger = logging.getLogger("tutordex_backend")

# Module-level state for fallback when Redis unavailable.
# NOTE: These dictionaries are intentionally module-level (shared across service instances)
# to provide consistent rate limiting behavior even when Redis is down. This matches the
# original implementation pattern in app.py and ensures rate limits work across all requests.
_RATE_LIMIT_LOCAL: Dict[str, Tuple[int, float]] = {}
_RATE_LIMIT_LOCK = asyncio.Lock()

_PUBLIC_CACHE_LOCAL: Dict[str, Tuple[str, float]] = {}
_PUBLIC_CACHE_LOCK = asyncio.Lock()


class CacheService:
    """Rate limiting and caching for public endpoints."""

    def __init__(self, store: TutorStore):
        self.store = store

    async def enforce_rate_limit(self, request: Request, endpoint: str) -> None:
        """
        Enforce rate limit for endpoint.

        Args:
            request: FastAPI request object
            endpoint: Endpoint name for rate limiting ("assignments" or "facets")

        Raises:
            HTTPException: 429 if rate limited
        """
        if endpoint == "assignments":
            rpm = get_public_rpm_assignments()
        elif endpoint == "facets":
            rpm = get_public_rpm_facets()
        else:
            rpm = 60  # Default fallback

        if rpm <= 0:
            return

        ip_hash_str = hash_ip(get_client_ip(request))
        bucket = int(time.time() // 60)
        key = f"{get_redis_prefix()}:rl:{endpoint}:{ip_hash_str}:{bucket}"

        try:
            n = self.store.r.incr(key)
            if int(n) == 1:
                self.store.r.expire(key, 120)
            if int(n) > int(rpm):
                raise HTTPException(status_code=429, detail="rate_limited")
            return
        except HTTPException:
            raise
        except Exception as e:
            swallow_exception(e, context="cache_rate_limit_redis", extra={"module": __name__})

        # Fallback if Redis isn't available (best-effort)
        now = time.time()
        async with _RATE_LIMIT_LOCK:
            n, expires_at = _RATE_LIMIT_LOCAL.get(key, (0, 0.0))
            if float(expires_at) <= now:
                n, expires_at = 0, now + 120.0
            n += 1
            _RATE_LIMIT_LOCAL[key] = (int(n), float(expires_at))
            if int(n) > int(rpm):
                raise HTTPException(status_code=429, detail="rate_limited")

    async def get_cached(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached response if available.

        Args:
            key: Cache key

        Returns:
            Cached response dict or None if not found/expired
        """
        try:
            raw = self.store.r.get(key)
            if raw:
                return json.loads(raw)
        except Exception as e:
            swallow_exception(e, context="cache_redis_get", extra={"module": __name__})

        now = time.time()
        async with _PUBLIC_CACHE_LOCK:
            raw, exp = _PUBLIC_CACHE_LOCAL.get(key, ("", 0.0))
            if raw and float(exp) > now:
                try:
                    return json.loads(raw)
                except Exception as e:
                    swallow_exception(e, context="cache_local_json_parse", extra={"module": __name__})
                    return None
            if float(exp) <= now:
                _PUBLIC_CACHE_LOCAL.pop(key, None)
        return None

    async def set_cached(self, key: str, payload: Dict[str, Any], ttl_s: int) -> None:
        """
        Set cached response.

        Args:
            key: Cache key
            payload: Response payload to cache
            ttl_s: Time to live in seconds
        """
        if ttl_s <= 0:
            return
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            self.store.r.setex(key, int(ttl_s), raw)
            return
        except Exception:
            pass

        now = time.time()
        async with _PUBLIC_CACHE_LOCK:
            _PUBLIC_CACHE_LOCAL[key] = (raw, now + float(ttl_s))
            # Clean up expired entries if cache gets too large
            if len(_PUBLIC_CACHE_LOCAL) > 2000:
                for k, (_, exp) in list(_PUBLIC_CACHE_LOCAL.items())[:500]:
                    if float(exp) <= now:
                        _PUBLIC_CACHE_LOCAL.pop(k, None)

    def is_anonymous(self, request: Request) -> bool:
        """
        Check if request is anonymous (no bearer token).

        Args:
            request: FastAPI request object

        Returns:
            True if anonymous, False if bearer token present
        """
        header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
        return not header

    def build_cache_key_for_request(
        self,
        request: Request,
        *,
        namespace: str,
        extra_items: Optional[List[Tuple[str, str]]] = None
    ) -> str:
        """
        Build cache key for request.

        Args:
            request: FastAPI request object
            namespace: Cache namespace
            extra_items: Extra (key, value) tuples to include in cache key

        Returns:
            Cache key string
        """
        try:
            q_items = list(request.query_params.multi_items())
        except Exception:
            q_items = []

        if extra_items:
            q_items.extend(extra_items)

        return build_cache_key(
            str(request.url.path),
            q_items,
            namespace=namespace,
            redis_prefix=get_redis_prefix()
        )

    @staticmethod
    def get_cache_ttl(endpoint: str) -> int:
        """
        Get cache TTL for endpoint.

        Args:
            endpoint: "assignments" or "facets"

        Returns:
            TTL in seconds
        """
        if endpoint == "assignments":
            return get_public_cache_ttl_assignments_s()
        elif endpoint == "facets":
            return get_public_cache_ttl_facets_s()
        return 0

    @staticmethod
    def get_public_limit_cap() -> int:
        """Get maximum limit for public assignment listings."""
        return get_public_assignments_limit_cap()
