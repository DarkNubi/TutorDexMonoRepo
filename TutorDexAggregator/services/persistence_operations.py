"""
Persistence Operations Service

Database operations for assignment persistence.
Handles agency upsert and related database operations.
"""
import logging
from typing import Optional
import requests

try:
    from utils.supabase_client import SupabaseRestClient, coerce_rows
except Exception:
    from TutorDexAggregator.utils.supabase_client import SupabaseRestClient, coerce_rows


logger = logging.getLogger("persistence_operations")


def upsert_agency(client: SupabaseRestClient, *, name: str, channel_link: Optional[str]) -> Optional[int]:
    """
    Find or create agency by name/channel_link.
    
    Args:
        client: Supabase REST client
        name: Agency name
        channel_link: Optional channel link (e.g., t.me/channel_name)
    
    Returns:
        agency_id or None if operation fails
    """
    if not name:
        return None

    # Try lookup by channel_link first (if present), else by name.
    if channel_link:
        q = f"agencies?select=id&channel_link=eq.{requests.utils.quote(channel_link, safe='')}&limit=1"
        try:
            r = client.get(q, timeout=15)
            if r.status_code < 400:
                rows = coerce_rows(r)
                if rows:
                    return rows[0].get("id")
        except Exception:
            logger.debug("Agency lookup by channel_link failed", exc_info=True)

    q2 = f"agencies?select=id&name=eq.{requests.utils.quote(name, safe='')}&limit=1"
    try:
        r2 = client.get(q2, timeout=15)
        if r2.status_code < 400:
            rows = coerce_rows(r2)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency lookup by name failed", exc_info=True)

    try:
        ins = client.post(
            "agencies",
            [{"name": name, "channel_link": channel_link}],
            timeout=20,
            prefer="return=representation",
        )
        if ins.status_code < 400:
            rows = coerce_rows(ins)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency insert failed", exc_info=True)
        return None
    return None
