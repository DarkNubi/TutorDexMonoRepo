"""
Request/response utilities.

HTTP request parsing utilities extracted from app.py.
"""
import hashlib
from typing import Optional, List, Tuple
from urllib.parse import quote as _url_quote
from fastapi import Request


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request headers or client object.
    
    Checks X-Forwarded-For header first, falls back to client.host.
    
    Args:
        request: FastAPI request object
        
    Returns:
        Client IP address or "unknown"
    """
    xff = (request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        first = xff.split(",", 1)[0].strip()
        return first or "unknown"
    return getattr(getattr(request, "client", None), "host", None) or "unknown"


def hash_ip(ip: str) -> str:
    """
    Hash IP address for privacy (SHA256, first 16 chars).
    
    Args:
        ip: IP address string
        
    Returns:
        Hashed IP (16 character hex string)
    """
    try:
        return hashlib.sha256(str(ip).encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "unknown"


def parse_traceparent(value: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse W3C traceparent header.
    
    Format: version-traceid-spanid-flags
    Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
    
    Args:
        value: traceparent header value
        
    Returns:
        Tuple of (trace_id, span_id) or (None, None) if invalid
    """
    s = (value or "").strip()
    if not s:
        return None, None
    parts = s.split("-")
    if len(parts) != 4:
        return None, None
    trace_id = parts[1].strip().lower()
    span_id = parts[2].strip().lower()
    if len(trace_id) != 32 or len(span_id) != 16:
        return None, None
    return trace_id, span_id


def clean_optional_string(value: Optional[str]) -> Optional[str]:
    """
    Clean optional string value (strip whitespace, return None if empty).
    
    Args:
        value: Optional string to clean
        
    Returns:
        Cleaned string or None
    """
    if value is None:
        return None
    v = str(value).strip()
    return v or None


def canonical_query_string(items: List[Tuple[str, str]]) -> str:
    """
    Generate stable canonical query string for caching.
    
    Sorts query parameters for consistent cache keys.
    
    Args:
        items: List of (key, value) tuples
        
    Returns:
        Canonical query string (sorted, URL-encoded)
    """
    items = [(str(k), str(v)) for k, v in (items or [])]
    items.sort(key=lambda kv: (kv[0], kv[1]))
    return "&".join([f"{k}={_url_quote(v)}" for k, v in items])


def build_cache_key(path: str, items: List[Tuple[str, str]], *, namespace: str, redis_prefix: str) -> str:
    """
    Build cache key from path and query parameters.
    
    Args:
        path: Request path
        items: Query parameter (key, value) tuples
        namespace: Cache namespace
        redis_prefix: Redis key prefix
        
    Returns:
        Cache key string
    """
    base = f"{path}?{canonical_query_string(items)}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]
    return f"{redis_prefix}:{namespace}:{h}"
