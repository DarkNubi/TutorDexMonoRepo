"""
Message processing for the extraction worker.

Handles message loading, filtering, and initial classification.
"""

import logging
from typing import Any, Dict, Optional

from workers.supabase_operations import fetch_channel, fetch_raw_message
from workers.utils import build_message_link

logger = logging.getLogger("message_processor")


class MessageFilterResult:
    """Result of message filtering."""
    
    def __init__(
        self,
        should_skip: bool,
        reason: Optional[str] = None,
        close_payload: Optional[Dict[str, Any]] = None
    ):
        self.should_skip = should_skip
        self.reason = reason
        self.close_payload = close_payload


def load_raw_message(
    url: str,
    key: str,
    raw_id: Any,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Load raw message from database.
    
    Args:
        url: Supabase URL
        key: Supabase API key
        raw_id: Raw message ID
        pipeline_version: For metrics
        schema_version: For metrics
        
    Returns:
        Raw message dict or None if not found
    """
    return fetch_raw_message(url, key, raw_id, pipeline_version, schema_version)


def load_channel_info(
    url: str,
    key: str,
    channel_link: str,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Dict[str, Any]:
    """
    Load channel information from database.
    
    Args:
        url: Supabase URL
        key: Supabase API key
        channel_link: Channel link
        pipeline_version: For metrics
        schema_version: For metrics
        
    Returns:
        Channel info dict (empty dict if not found)
    """
    return fetch_channel(url, key, channel_link, pipeline_version, schema_version) or {}


def filter_message(
    raw: Dict[str, Any],
    channel_link: str,
    ch_info: Dict[str, Any]
) -> MessageFilterResult:
    """
    Apply filters to determine if message should be skipped.
    
    Filters:
    - Deleted messages -> skip (with close payload)
    - Forwarded messages -> skip
    - Reply messages -> skip (bump parent instead)
    - Empty text -> skip
    
    Args:
        raw: Raw message dict
        channel_link: Channel link
        ch_info: Channel info dict
        
    Returns:
        MessageFilterResult indicating if message should be skipped
    """
    # Check if deleted
    if raw.get("deleted_at"):
        cid = f"deleted:{channel_link}:{raw.get('message_id')}"
        close_payload = {
            "cid": cid,
            "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
            "channel_link": channel_link,
            "channel_username": channel_link.replace("https://", "").replace("http://", "").replace("t.me/", ""),
            "message_id": raw.get("message_id"),
            "message_link": build_message_link(channel_link, str(raw.get("message_id") or "")),
            "raw_text": raw.get("raw_text"),
            "parsed": {},
        }
        return MessageFilterResult(
            should_skip=True,
            reason="deleted",
            close_payload=close_payload
        )
    
    # Check if forwarded
    if bool(raw.get("is_forward")):
        return MessageFilterResult(should_skip=True, reason="forward")
    
    # Check if reply - bump parent assignment instead of processing
    if bool(raw.get("is_reply")):
        return MessageFilterResult(should_skip=True, reason="reply")
    
    # Check if empty text
    raw_text = str(raw.get("raw_text") or "").strip()
    if not raw_text:
        return MessageFilterResult(should_skip=True, reason="empty_text")
    
    # Message passed all filters
    return MessageFilterResult(should_skip=False)


def build_extraction_context(
    job: Dict[str, Any],
    raw: Dict[str, Any],
    ch_info: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Build context object for extraction processing.
    
    Args:
        job: Job dict from queue
        raw: Raw message dict
        ch_info: Channel info dict
        
    Returns:
        Context dict with all necessary information
    """
    extraction_id = job.get("id")
    raw_id = job.get("raw_id")
    channel_link = str(job.get("channel_link") or "").strip() or "t.me/unknown"
    message_id = str(job.get("message_id") or "").strip()
    
    cid = f"worker:{channel_link}:{message_id}:{extraction_id}"
    
    return {
        "extraction_id": extraction_id,
        "raw_id": raw_id,
        "channel_link": channel_link,
        "message_id": message_id,
        "cid": cid,
        "raw_text": str(raw.get("raw_text") or "").strip(),
        "channel_id": raw.get("channel_id") or ch_info.get("channel_id"),
        "channel_title": ch_info.get("title"),
        "channel_username": channel_link.replace("t.me/", "") if channel_link.startswith("t.me/") else None,
        "message_date": raw.get("message_date"),
        "edit_date": raw.get("edit_date"),
        "message_link": build_message_link(channel_link, message_id),
        "existing_meta": job.get("meta"),
    }
