"""
Database utilities.

PostgreSQL and Supabase query helper functions extracted from app.py.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote as _url_quote

logger = logging.getLogger("tutordex_backend")


def pg_array_literal(items: List[str]) -> str:
    """
    Format Python list as PostgreSQL array literal.
    
    PostgREST array operators expect format: {"value1","value2"}
    
    Args:
        items: List of string values
        
    Returns:
        PostgreSQL array literal string
        
    Example:
        ["Junior College", "IB"] -> '{"Junior College","IB"}'
    """
    out: List[str] = []
    for raw in items or []:
        s = str(raw or "").strip()
        if not s:
            continue
        # Escape backslashes and quotes for Postgres
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        out.append(f'"{s}"')
    return "{" + ",".join(out) + "}"


def extract_count_from_header(value: Optional[str]) -> Optional[int]:
    """
    Extract total count from PostgREST Content-Range header.
    
    Args:
        value: Content-Range header value
        
    Returns:
        Total count or None if not parseable
        
    Example:
        "0-9/100" -> 100
        "*/1234" -> 1234
    """
    if not value:
        return None
    if "/" not in value:
        return None
    try:
        return int(value.split("/")[-1])
    except Exception:
        return None


def count_matching_assignments(
    supabase_client,
    *,
    days: int,
    levels: List[str],
    specific_student_levels: List[str],
    subjects_canonical: List[str],
    subjects_general: List[str],
) -> Optional[int]:
    """
    Count assignments matching given criteria in time window.
    
    Uses published_at (source publish time) not last_seen (processing time)
    to avoid backfill inflation.
    
    Args:
        supabase_client: Supabase client with get() method
        days: Days of history to include
        levels: Level filters
        specific_student_levels: Specific level filters
        subjects_canonical: Canonical subject filters
        subjects_general: General subject filters
        
    Returns:
        Count of matching assignments or None on error
    """
    if not supabase_client:
        return None
    
    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    since_iso = since.isoformat()
    
    # Count all assignments (open + closed) for historical volume
    # Use published_at (source time), not last_seen (our processing time)
    q = f"assignments?select=id&published_at=gte.{_url_quote(since_iso, safe='')}&limit=0"
    
    if levels:
        arr = pg_array_literal(levels)
        q += f"&signals_levels=ov.{_url_quote(arr, safe='')}"
    if specific_student_levels:
        arr = pg_array_literal(specific_student_levels)
        q += f"&signals_specific_student_levels=ov.{_url_quote(arr, safe='')}"
    if subjects_canonical:
        arr = pg_array_literal(subjects_canonical)
        q += f"&subjects_canonical=ov.{_url_quote(arr, safe='')}"
    if subjects_general:
        arr = pg_array_literal(subjects_general)
        q += f"&subjects_general=ov.{_url_quote(arr, safe='')}"
    
    try:
        resp = supabase_client.get(q, timeout=20, prefer="count=exact")
    except Exception:
        return None
    
    if resp.status_code >= 300:
        logger.warning(
            "match_counts_query_failed status=%s body=%s",
            resp.status_code,
            resp.text[:300]
        )
        return None
    
    return extract_count_from_header(resp.headers.get("content-range"))
