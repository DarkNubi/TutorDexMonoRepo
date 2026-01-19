"""
Analytics and tracking service.

Handles click tracking, analytics events, and URL resolution.
"""
import time
import asyncio
import logging
from typing import Any, Dict, Optional
from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.supabase_store import SupabaseStore
from TutorDexBackend.utils.request_utils import get_client_ip, hash_ip
from TutorDexBackend.utils.config_utils import get_env_int, get_redis_prefix
from fastapi import Request
from shared.observability.exception_handler import swallow_exception

logger = logging.getLogger("tutordex_backend")

# Module-level state for click cooldown fallback.
# NOTE: This dictionary is intentionally module-level (shared across service instances)
# to provide consistent click tracking behavior even when Redis is down. This matches the
# original implementation pattern in app.py.
_CLICK_COOLDOWN_LOCAL: Dict[str, float] = {}
_CLICK_COOLDOWN_LOCK = asyncio.Lock()


class AnalyticsService:
    """Analytics events and click tracking."""

    def __init__(self, sb: SupabaseStore, store: TutorStore):
        self.sb = sb
        self.store = store

    async def check_click_cooldown(self, request: Request, external_id: str) -> bool:
        """
        Check if click should be tracked (respects cooldown).

        Args:
            request: FastAPI request object
            external_id: Assignment external ID

        Returns:
            True if click should be incremented, False if within cooldown
        """
        cooldown_s = max(0, get_env_int("CLICK_TRACKING_IP_COOLDOWN_SECONDS", 10))
        if cooldown_s <= 0:
            return True

        ip_hash_str = hash_ip(get_client_ip(request))
        prefix = get_redis_prefix()
        key = f"{prefix}:click_cd:{external_id}:{ip_hash_str}"

        try:
            ok = self.store.r.set(key, "1", nx=True, ex=int(cooldown_s))
            return bool(ok)
        except Exception as e:
            swallow_exception(e, context="analytics_click_cooldown_redis", extra={"module": __name__})

        now = time.time()
        async with _CLICK_COOLDOWN_LOCK:
            expires_at = float(_CLICK_COOLDOWN_LOCAL.get(key) or 0.0)
            if expires_at > now:
                return False
            _CLICK_COOLDOWN_LOCAL[key] = now + float(cooldown_s)
            # Clean up old entries
            if len(_CLICK_COOLDOWN_LOCAL) > 5000:
                for k, exp in list(_CLICK_COOLDOWN_LOCAL.items())[:1000]:
                    if float(exp) <= now:
                        _CLICK_COOLDOWN_LOCAL.pop(k, None)
        return True

    async def resolve_broadcast_url(
        self,
        *,
        external_id: Optional[str],
        destination_url: Optional[str]
    ) -> Optional[str]:
        """
        Resolve original URL from external_id or use provided destination_url.

        Args:
            external_id: Assignment external ID
            destination_url: Direct destination URL

        Returns:
            Resolved URL or None
        """
        if destination_url:
            url = destination_url.strip()
            if url:
                return url

        ext = (external_id or "").strip()
        if not ext or not self.sb.enabled():
            return None

        try:
            bm = self.sb.get_broadcast_message(external_id=ext)
        except Exception as e:
            swallow_exception(e, context="analytics_broadcast_message_get", extra={"module": __name__})
            bm = None

        if bm:
            url = str(bm.get("original_url") or "").strip()
            if url:
                return url
        return None

    def insert_analytics_event(
        self,
        user_id: int,
        assignment_id: Optional[int],
        event_type: str,
        meta: Optional[Dict[str, Any]]
    ) -> None:
        """
        Insert analytics event into Supabase.

        Args:
            user_id: User ID
            assignment_id: Optional assignment ID
            event_type: Event type string
            meta: Optional metadata dict
        """
        if not self.sb.enabled():
            return

        self.sb.insert_event(
            user_id=user_id,
            assignment_id=assignment_id,
            event_type=event_type,
            meta=meta or {}
        )
