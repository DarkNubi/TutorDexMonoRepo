"""
Configuration utilities.

Pydantic-backed configuration getters (shared/config.py).
"""
from typing import Optional

from shared.config import load_backend_config

_CFG = load_backend_config()

def get_app_env() -> str:
    """Get application environment (prod, dev, etc.)."""
    return str(_CFG.app_env or "dev").strip().lower()


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
    key = str(name or "").strip().upper()
    mapping = {
        "CLICK_TRACKING_IP_COOLDOWN_SECONDS": "click_tracking_ip_cooldown_seconds",
        "PUBLIC_ASSIGNMENTS_LIMIT_CAP": "public_assignments_limit_cap",
        "PUBLIC_RPM_ASSIGNMENTS": "public_rpm_assignments",
        "PUBLIC_RPM_FACETS": "public_rpm_facets",
        "PUBLIC_CACHE_TTL_ASSIGNMENTS_SECONDS": "public_cache_ttl_assignments_seconds",
        "PUBLIC_CACHE_TTL_FACETS_SECONDS": "public_cache_ttl_facets_seconds",
    }
    field = mapping.get(key)
    if not field:
        return default
    try:
        return int(getattr(_CFG, field))
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
    return str(_CFG.redis_prefix or "tutordex").strip()


def get_public_assignments_limit_cap() -> int:
    """Get maximum limit for public assignment listings."""
    return max(1, int(_CFG.public_assignments_limit_cap))


def get_public_rpm_assignments() -> int:
    """Get requests per minute limit for public /assignments endpoint."""
    return max(0, int(_CFG.public_rpm_assignments))


def get_public_rpm_facets() -> int:
    """Get requests per minute limit for public /assignments/facets endpoint."""
    return max(0, int(_CFG.public_rpm_facets))


def get_public_cache_ttl_assignments_s() -> int:
    """Get cache TTL in seconds for public /assignments responses."""
    return max(0, int(_CFG.public_cache_ttl_assignments_seconds))


def get_public_cache_ttl_facets_s() -> int:
    """Get cache TTL in seconds for public /assignments/facets responses."""
    return max(0, int(_CFG.public_cache_ttl_facets_seconds))


def get_bot_token_for_edits() -> str:
    """Get Telegram bot token for edits/callbacks."""
    return (str(_CFG.tracking_edit_bot_token or "") or str(_CFG.group_bot_token or "")).strip()
