"""
Health check service.

Provides health status for all system components.
"""
import logging
from typing import Any, Dict
import requests
from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.supabase_store import SupabaseStore
from shared.observability.exception_handler import swallow_exception

logger = logging.getLogger("tutordex_backend")


class HealthService:
    """Aggregate health checks for all services."""

    def __init__(self, store: TutorStore, sb: SupabaseStore):
        self.store = store
        self.sb = sb

    def basic_health(self) -> Dict[str, Any]:
        """Basic health check (always returns ok=True)."""
        return {"ok": True}

    def redis_health(self) -> Dict[str, Any]:
        """Check Redis connectivity."""
        try:
            pong = bool(self.store.r.ping())
            return {"ok": pong}
        except Exception as e:
            logger.warning("health_redis_failed error=%s", e)
            return {"ok": False, "error": str(e)}

    def supabase_health(self) -> Dict[str, Any]:
        """Check Supabase connectivity and auth."""
        if not self.sb.enabled():
            return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

        try:
            # Cheap PostgREST query to validate connectivity and auth
            resp = self.sb.client.get("assignments?select=id&limit=1", timeout=10)
            ok = resp.status_code < 400
            return {"ok": ok, "status_code": resp.status_code}
        except Exception as e:
            logger.warning("health_supabase_failed error=%s", e)
            return {"ok": False, "error": str(e)}

    def full_health(self) -> Dict[str, Any]:
        """Aggregate health check for all core services."""
        base = self.basic_health()
        redis_h = self.redis_health()
        supabase_h = self.supabase_health()

        ok = (
            bool(base.get("ok")) and
            bool(redis_h.get("ok")) and
            (bool(supabase_h.get("ok")) or bool(supabase_h.get("skipped")))
        )

        return {
            "ok": ok,
            "base": base,
            "redis": redis_h,
            "supabase": supabase_h
        }

    def collector_health(self) -> Dict[str, Any]:
        """Check collector service health."""
        res = self.check_service_health("http://collector-tail:9001/health/collector")
        return {"ok": bool(res.get("ok")), "collector": res}

    def worker_health(self) -> Dict[str, Any]:
        """Check worker service health."""
        res = self.check_service_health("http://aggregator-worker:9002/health/worker")
        return {"ok": bool(res.get("ok")), "worker": res}

    def dependencies_health(self) -> Dict[str, Any]:
        """Alias for full_health for backward compatibility."""
        return self.full_health()

    def webhook_health(self, bot_token: str) -> Dict[str, Any]:
        """
        Check Telegram webhook status for the broadcast bot.

        Args:
            bot_token: Telegram bot token

        Returns:
            Dict with webhook information including URL, pending updates, and errors
        """
        if not bot_token:
            return {
                "ok": False,
                "error": "no_bot_token",
                "message": "GROUP_BOT_TOKEN not configured"
            }

        try:
            resp = requests.get(
                f"https://api.telegram.org/bot{bot_token}/getWebhookInfo",
                timeout=10
            )
            resp.raise_for_status()
            result = resp.json()

            if not result.get("ok"):
                return {
                    "ok": False,
                    "error": "telegram_api_error",
                    "description": result.get("description", "Unknown error")
                }

            info = result.get("result", {})
            webhook_url = info.get("url", "")
            has_webhook = bool(webhook_url)

            # Determine health status
            ok = has_webhook and info.get("pending_update_count", 0) < 100
            if info.get("last_error_date"):
                ok = False

            return {
                "ok": ok,
                "has_webhook": has_webhook,
                "webhook_url": webhook_url or None,
                "pending_updates": info.get("pending_update_count", 0),
                "max_connections": info.get("max_connections"),
                "allowed_updates": info.get("allowed_updates", []),
                "last_error_date": info.get("last_error_date"),
                "last_error_message": info.get("last_error_message"),
                "has_custom_certificate": info.get("has_custom_certificate", False),
            }
        except requests.RequestException as e:
            return {
                "ok": False,
                "error": "request_failed",
                "message": str(e)
            }

    @staticmethod
    def check_service_health(url: str, timeout_s: float = 2.0) -> Dict[str, Any]:
        """
        Check health of a service via HTTP GET.

        Args:
            url: Service health endpoint URL
            timeout_s: Request timeout in seconds

        Returns:
            Dict with ok, status_code, and optional body/error
        """
        try:
            resp = requests.get(url, timeout=timeout_s)
            ok = resp.status_code < 400
            body = None
            try:
                body = resp.json()
            except Exception as e:
                swallow_exception(e, context="health_check_json_parse", extra={"module": __name__})
            return {"ok": ok, "status_code": resp.status_code, "body": body}
        except Exception as e:
            return {"ok": False, "error": str(e)}
