"""
Configuration utilities.

Environment variable parsing and configuration getters extracted from app.py.
"""
import os
from typing import Optional


def get_app_env() -> str:
    """Get application environment (prod, dev, etc.)."""
    return (os.environ.get("APP_ENV") or os.environ.get("ENV") or "dev").strip().lower()


def is_production() -> bool:
    """Check if running in production environment."""
    return get_app_env() in {"prod", "production"}


def get_env_int(name: str, default: int) -> int:
    """
    Parse integer from environment variable with fallback.
    
    Args:
        name: Environment variable name
        default: Default value if not set or invalid
        
    Returns:
        Integer value from env or default
    """
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def parse_truthy(value: Optional[str]) -> bool:
    """
    Parse truthy string value.
    
    Args:
        value: String value to parse ("1", "true", "yes", etc.)
        
    Returns:
        True if value is truthy, False otherwise
    """
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def get_redis_prefix() -> str:
    """Get Redis key prefix from environment (default: tutordex)."""
    return os.environ.get("REDIS_PREFIX", "tutordex").strip()


def get_public_assignments_limit_cap() -> int:
    """Get maximum limit for public assignment listings."""
    return max(1, get_env_int("PUBLIC_ASSIGNMENTS_LIMIT_CAP", 50))


def get_public_rpm_assignments() -> int:
    """Get requests per minute limit for public /assignments endpoint."""
    return max(0, get_env_int("PUBLIC_RPM_ASSIGNMENTS", 60))


def get_public_rpm_facets() -> int:
    """Get requests per minute limit for public /assignments/facets endpoint."""
    return max(0, get_env_int("PUBLIC_RPM_FACETS", 120))


def get_public_cache_ttl_assignments_s() -> int:
    """Get cache TTL in seconds for public /assignments responses."""
    return max(0, get_env_int("PUBLIC_CACHE_TTL_ASSIGNMENTS_SECONDS", 15))


def get_public_cache_ttl_facets_s() -> int:
    """Get cache TTL in seconds for public /assignments/facets responses."""
    return max(0, get_env_int("PUBLIC_CACHE_TTL_FACETS_SECONDS", 30))


def get_bot_token_for_edits() -> str:
    """Get Telegram bot token for edits/callbacks."""
    return (os.environ.get("TRACKING_EDIT_BOT_TOKEN") or os.environ.get("GROUP_BOT_TOKEN") or "").strip()
