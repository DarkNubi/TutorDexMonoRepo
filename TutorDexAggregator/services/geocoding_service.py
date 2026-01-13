"""
Geocoding Service

Geocode Singapore postal codes using Nominatim API with caching and retry logic.
"""
import os
import logging
from functools import lru_cache
from typing import Optional, Tuple

try:
    from utils.field_coercion import truthy, normalize_sg_postal_code
except Exception:
    from TutorDexAggregator.utils.field_coercion import truthy, normalize_sg_postal_code


logger = logging.getLogger("geocoding_service")


def nominatim_disabled() -> bool:
    """Check if Nominatim geocoding is disabled."""
    return truthy(os.environ.get("DISABLE_NOMINATIM"))


@lru_cache(maxsize=2048)
def geocode_sg_postal(postal_code: str, *, timeout: int = 10) -> Optional[Tuple[float, float]]:
    """
    Geocode Singapore postal code using Nominatim API.
    
    Returns (lat, lon) tuple or None if geocoding fails.
    Caches results to avoid repeated API calls.
    
    Args:
        postal_code: Singapore postal code (6 digits)
        timeout: Request timeout in seconds
    
    Returns:
        Tuple of (latitude, longitude) or None if geocoding fails
    """
    if nominatim_disabled():
        return None
    
    pc = normalize_sg_postal_code(postal_code)
    if not pc:
        return None

    import requests
    
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"Singapore {pc}", "format": "jsonv2", "limit": 1, "countrycodes": "sg"}
    headers = {"User-Agent": os.environ.get("NOMINATIM_USER_AGENT") or "TutorDexAggregator/1.0"}

    max_attempts = int(os.environ.get("NOMINATIM_RETRIES") or "3")
    backoff_s = float(os.environ.get("NOMINATIM_BACKOFF_SECONDS") or "1.0")

    resp = None
    for attempt in range(max(1, min(max_attempts, 6))):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        except Exception:
            logger.debug("postal_geocode_failed", exc_info=True)
            resp = None

        if resp is None:
            # transient network issue
            if attempt < max_attempts - 1:
                try:
                    import time
                    time.sleep(min(10.0, backoff_s * (2**attempt)))
                except Exception:
                    pass
            continue

        if resp.status_code in {429, 503} and attempt < max_attempts - 1:
            try:
                import time
                time.sleep(min(10.0, backoff_s * (2**attempt)))
            except Exception:
                pass
            continue

        if resp.status_code >= 400:
            return None
        break

    if resp is None:
        return None

    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None

    try:
        lat = float(data[0].get("lat"))
        lon = float(data[0].get("lon"))
        return (lat, lon)
    except Exception:
        return None
