"""
Supabase database operations for the extraction worker.

This module encapsulates all direct Supabase REST API interactions:
- RPC calls (function invocations)
- GET operations for fetching records
- PATCH operations for updating records
- Queue metrics and monitoring
"""

import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

from observability_metrics import (
    worker_supabase_fail_total,
    worker_supabase_latency_seconds,
    worker_supabase_requests_total,
)


def build_headers(api_key: str) -> Dict[str, str]:
    """Build standard Supabase API headers."""
    return {
        "apikey": api_key,
        "authorization": f"Bearer {api_key}",
        "content-type": "application/json"
    }


def call_rpc(
    url: str,
    key: str,
    function_name: str,
    body: Dict[str, Any],
    *,
    timeout: int = 30,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Any:
    """
    Call a Supabase RPC function.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        function_name: Name of the RPC function to call
        body: JSON body to send
        timeout: Request timeout in seconds
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        JSON response or None on error
    """
    t0 = time.perf_counter()
    op = f"rpc:{function_name}"
    
    try:
        worker_supabase_requests_total.labels(
            operation=op,
            pipeline_version=pipeline_version,
            schema_version=schema_version
        ).inc()
    except Exception:
        pass
    
    try:
        resp = requests.post(
            f"{url}/rest/v1/rpc/{function_name}",
            headers=build_headers(key),
            json=body,
            timeout=timeout
        )
        
        # Check for ambiguous overloads (HTTP 300) and other errors
        from supabase_env import check_rpc_response  # noqa: E402
        check_rpc_response(resp, function_name)
        
        try:
            return resp.json()
        except Exception:
            return None
    finally:
        try:
            worker_supabase_latency_seconds.labels(
                operation=op,
                pipeline_version=pipeline_version,
                schema_version=schema_version
            ).observe(max(0.0, time.perf_counter() - t0))
        except Exception:
            pass


def get_one(
    url: str,
    key: str,
    table: str,
    query: str,
    *,
    timeout: int = 30,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Fetch a single row from a Supabase table.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        table: Table name
        query: Query string (e.g., "select=*&id=eq.123")
        timeout: Request timeout in seconds
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        First row as dict, or None if not found or error
    """
    t0 = time.perf_counter()
    op = f"get:{table}"
    
    try:
        worker_supabase_requests_total.labels(
            operation=op,
            pipeline_version=pipeline_version,
            schema_version=schema_version
        ).inc()
    except Exception:
        pass
    
    try:
        resp = requests.get(
            f"{url}/rest/v1/{table}?{query}",
            headers=build_headers(key),
            timeout=timeout
        )
        
        if resp.status_code >= 400:
            return None
        
        try:
            data = resp.json()
        except Exception:
            return None
        
        if isinstance(data, list) and data:
            row = data[0]
            return row if isinstance(row, dict) else None
        
        return None
    finally:
        try:
            worker_supabase_latency_seconds.labels(
                operation=op,
                pipeline_version=pipeline_version,
                schema_version=schema_version
            ).observe(max(0.0, time.perf_counter() - t0))
        except Exception:
            pass


def patch_table(
    url: str,
    key: str,
    table: str,
    where: str,
    body: Dict[str, Any],
    *,
    timeout: int = 30,
    pipeline_version: str = "",
    schema_version: str = ""
) -> bool:
    """
    Update rows in a Supabase table.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        table: Table name
        where: WHERE clause (e.g., "id=eq.123")
        body: JSON body with fields to update
        timeout: Request timeout in seconds
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        True if successful (status < 400), False otherwise
    """
    t0 = time.perf_counter()
    op = f"patch:{table}"
    
    try:
        worker_supabase_requests_total.labels(
            operation=op,
            pipeline_version=pipeline_version,
            schema_version=schema_version
        ).inc()
    except Exception:
        pass
    
    h = dict(build_headers(key))
    h["prefer"] = "return=minimal"
    
    resp = requests.patch(
        f"{url}/rest/v1/{table}?{where}",
        headers=h,
        json=body,
        timeout=timeout
    )
    
    try:
        worker_supabase_latency_seconds.labels(
            operation=op,
            pipeline_version=pipeline_version,
            schema_version=schema_version
        ).observe(max(0.0, time.perf_counter() - t0))
    except Exception:
        pass
    
    return resp.status_code < 400


def count_from_range(content_range: Optional[str]) -> Optional[int]:
    """
    Extract total count from a Supabase content-range header.
    
    Args:
        content_range: Header value like "0-9/42"
        
    Returns:
        Total count or None if parsing fails
    """
    if not content_range or "/" not in content_range:
        return None
    try:
        return int(content_range.split("/")[-1])
    except Exception:
        return None


def get_queue_counts(
    url: str,
    key: str,
    statuses: List[str]
) -> Dict[str, Optional[int]]:
    """
    Get counts of extraction jobs by status.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        statuses: List of statuses to count (e.g., ["pending", "ok", "failed"])
        
    Returns:
        Dict mapping status to count
    """
    counts: Dict[str, Optional[int]] = {}
    h = dict(build_headers(key))
    h["prefer"] = "count=exact"
    
    for status in statuses:
        try:
            resp = requests.get(
                f"{url}/rest/v1/telegram_extractions"
                f"?status=eq.{requests.utils.quote(status, safe='')}"
                f"&select=id&limit=0",
                headers=h,
                timeout=15
            )
            counts[status] = count_from_range(resp.headers.get("content-range"))
        except Exception:
            counts[status] = None
    
    return counts


def get_oldest_created_age_seconds(
    url: str,
    key: str,
    status: str
) -> Optional[float]:
    """
    Get age in seconds of the oldest extraction job with given status.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        status: Job status to query
        
    Returns:
        Age in seconds, or None if no jobs found
    """
    row = get_one(
        url,
        key,
        "telegram_extractions",
        f"select=created_at"
        f"&status=eq.{requests.utils.quote(status, safe='')}"
        f"&order=created_at.asc&limit=1",
        timeout=15
    )
    
    if not row or "created_at" not in row:
        return None
    
    try:
        created = row["created_at"]
        if isinstance(created, str):
            dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        else:
            return None
        return max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds())
    except Exception:
        return None


def fetch_raw_message(
    url: str,
    key: str,
    raw_id: Any,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Fetch a raw telegram message by ID.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        raw_id: Raw message ID
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        Raw message row or None if not found
    """
    rid = requests.utils.quote(str(raw_id), safe="")
    select = "id,channel_link,channel_id,message_id,message_date,edit_date,raw_text,is_forward,deleted_at"
    return get_one(
        url,
        key,
        "telegram_messages_raw",
        f"select={select}&id=eq.{rid}&limit=1",
        pipeline_version=pipeline_version,
        schema_version=schema_version
    )


# Simple cache for channel lookups to avoid repeated queries
_CHANNEL_CACHE: Dict[str, Dict[str, Any]] = {}


def fetch_channel(
    url: str,
    key: str,
    channel_link: str,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Fetch channel metadata by channel_link.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        channel_link: Channel link string
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        Channel row or None if not found
    """
    if channel_link in _CHANNEL_CACHE:
        return _CHANNEL_CACHE[channel_link]
    
    cl = requests.utils.quote(str(channel_link), safe="")
    row = get_one(
        url,
        key,
        "telegram_channels",
        f"select=channel_link,channel_id,title&channel_link=eq.{cl}&limit=1",
        pipeline_version=pipeline_version,
        schema_version=schema_version
    )
    
    if isinstance(row, dict):
        _CHANNEL_CACHE[channel_link] = row
        return row
    
    _CHANNEL_CACHE[channel_link] = {}
    return None
