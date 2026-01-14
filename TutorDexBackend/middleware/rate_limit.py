"""
Rate Limiting Middleware for TutorDex Backend.

Uses slowapi to provide rate limiting for public endpoints.
Protects against abuse and ensures fair usage.
"""
import os
import logging
from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from fastapi import Request, Response
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _get_rate_limit_key(request: Request) -> str:
    """
    Get the key for rate limiting.
    
    Uses X-Forwarded-For if available (for proxied requests),
    otherwise falls back to direct client IP.
    
    Args:
        request: FastAPI request object
        
    Returns:
        IP address to use for rate limiting
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For can have multiple IPs, use the first (client)
        return forwarded.split(",")[0].strip()
    
    # Fall back to direct address
    return get_remote_address(request)


def _is_rate_limit_enabled() -> bool:
    """
    Check if rate limiting is enabled via environment variable.
    
    Returns:
        True if rate limiting should be active
    """
    enabled = os.environ.get("RATE_LIMIT_ENABLED", "1").strip()
    return enabled.lower() in ("1", "true", "yes", "on")


def _get_redis_url() -> Optional[str]:
    """
    Get Redis URL for rate limit storage.
    
    If Redis is not available, slowapi will fall back to in-memory storage
    (which won't work well in multi-process deployments).
    
    Returns:
        Redis URL or None
    """
    return os.environ.get("REDIS_URL")


# Rate limit configurations for different endpoint types
class RateLimits:
    """Rate limit presets for different endpoint categories."""
    
    # Public endpoints (no auth)
    PUBLIC_STRICT = "30/minute"      # For expensive queries
    PUBLIC_MODERATE = "100/minute"   # For typical public endpoints
    PUBLIC_GENEROUS = "300/minute"   # For lightweight endpoints
    
    # Authenticated endpoints
    AUTH_DEFAULT = "300/minute"      # For authenticated users
    AUTH_GENEROUS = "1000/minute"    # For high-volume operations
    
    # Admin endpoints
    ADMIN_DEFAULT = "1000/minute"    # For admin operations
    
    # Health/monitoring endpoints
    HEALTH_CHECK = "1000/minute"     # For health checks (very permissive)


# Create limiter instance
_storage_uri = _get_redis_url()
limiter = Limiter(
    key_func=_get_rate_limit_key,
    storage_uri=_storage_uri,
    enabled=_is_rate_limit_enabled(),
    default_limits=[]  # No global default, specify per-endpoint
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom handler for rate limit exceeded errors.
    
    Returns a JSON response with clear error message and retry information.
    
    Args:
        request: The request that exceeded the limit
        exc: The rate limit exception
        
    Returns:
        JSON response with 429 status code
    """
    logger.warning(
        "rate_limit_exceeded",
        extra={
            "path": request.url.path,
            "client_ip": _get_rate_limit_key(request),
            "limit": str(exc),
        }
    )
    
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": "Too many requests. Please try again later.",
            "retry_after": exc.retry_after if hasattr(exc, "retry_after") else None,
        },
        headers={
            "Retry-After": str(getattr(exc, "retry_after", 60)),
        }
    )


# Helper function to get limiter for use in app.py
def get_limiter() -> Limiter:
    """
    Get the configured limiter instance.
    
    Returns:
        Slowapi Limiter instance
    """
    return limiter


def get_rate_limit_middleware():
    """
    Get the rate limiting middleware.
    
    Returns:
        SlowAPIMiddleware instance
    """
    return SlowAPIMiddleware


# Convenience decorator for common rate limits
def public_endpoint(func):
    """Decorator for public endpoints with moderate rate limiting."""
    return limiter.limit(RateLimits.PUBLIC_MODERATE)(func)


def expensive_endpoint(func):
    """Decorator for expensive public endpoints with strict rate limiting."""
    return limiter.limit(RateLimits.PUBLIC_STRICT)(func)


def authenticated_endpoint(func):
    """Decorator for authenticated endpoints with generous rate limiting."""
    return limiter.limit(RateLimits.AUTH_DEFAULT)(func)
