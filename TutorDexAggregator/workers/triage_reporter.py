"""
Triage message reporting to Telegram.

Handles reporting of various categories of filtered/failed messages
to Telegram threads for manual review.
"""

import logging
import os
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger("triage_reporter")


def get_triage_config() -> Dict[str, Optional[str]]:
    """
    Get triage reporting configuration from environment.
    
    Returns:
        Dict with chat_id, bot_token, and api_base
    """
    return {
        "chat_id": (os.environ.get("SKIPPED_MESSAGES_CHAT_ID") or "").strip() or None,
        "bot_token": _get_bot_token(),
        "api_base": (os.environ.get("BOT_API_URL") or os.environ.get("TG_BOT_API_URL") or "").strip() or None,
    }


def _get_bot_token() -> Optional[str]:
    """Get bot token for triage reporting (prefers GROUP_BOT_TOKEN)."""
    return (os.environ.get("GROUP_BOT_TOKEN") or os.environ.get("DM_BOT_TOKEN") or "").strip() or None


def _parse_int_env(name: str) -> Optional[int]:
    """Parse integer from environment variable."""
    v = (os.environ.get(name) or "").strip()
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


def get_thread_id_for_category(category: str) -> Optional[int]:
    """
    Get Telegram thread ID for a triage category.
    
    Args:
        category: Category like "extraction_error", "non_assignment", "compilation"
        
    Returns:
        Thread ID or None
    """
    default_thread = _parse_int_env("SKIPPED_MESSAGES_THREAD_ID")
    
    k = str(category or "").strip().lower()
    
    if k in {"extraction_error", "extraction_errors", "extraction"}:
        return _parse_int_env("SKIPPED_MESSAGES_THREAD_ID_EXTRACTION_ERRORS") or default_thread
    
    if k in {"non_assignment", "non-assignments", "nonassignment"}:
        return _parse_int_env("SKIPPED_MESSAGES_THREAD_ID_NON_ASSIGNMENT") or default_thread
    
    if k in {"compilation", "compilations"}:
        return _parse_int_env("SKIPPED_MESSAGES_THREAD_ID_COMPILATIONS") or default_thread
    
    return default_thread


def send_telegram_message(
    *,
    to_chat_id: str,
    text: str,
    thread_id: Optional[int] = None,
    bot_token: Optional[str] = None,
    api_base: Optional[str] = None
) -> Dict[str, Any]:
    """
    Send a message to Telegram.
    
    Args:
        to_chat_id: Target chat ID
        text: Message text
        thread_id: Optional thread/topic ID
        bot_token: Bot token (if None, fetched from config)
        api_base: API base URL (if None, uses default or fetched from config)
        
    Returns:
        Response dict with "ok" status
    """
    if bot_token is None:
        bot_token = _get_bot_token()
    
    if not bot_token and not api_base:
        return {"ok": False, "error": "no_bot_token_or_api_url"}
    
    url = api_base
    if not url and bot_token:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    elif url and not url.endswith("/sendMessage"):
        url = url.rstrip("/") + "/sendMessage"
    
    if not url:
        return {"ok": False, "error": "no_api_url"}
    
    payload: Dict[str, Any] = {"chat_id": to_chat_id, "text": text}
    if thread_id is not None:
        payload["message_thread_id"] = int(thread_id)
    
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code >= 400:
            return {"ok": False, "status_code": resp.status_code, "error": resp.text[:200]}
        
        try:
            return resp.json()
        except Exception:
            return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def chunk_text(text: str, *, max_length: int = 4000) -> List[str]:
    """
    Split text into chunks that fit Telegram's message length limit.
    
    Args:
        text: Text to chunk
        max_length: Maximum chunk length
        
    Returns:
        List of text chunks
    """
    if len(text) <= max_length:
        return [text]
    
    chunks: List[str] = []
    current = text
    while len(current) > max_length:
        chunks.append(current[:max_length])
        current = current[max_length:]
    if current:
        chunks.append(current)
    
    return chunks


def try_report_triage_message(
    *,
    category: str,
    message_link: Optional[str],
    channel: str,
    message_id: str,
    raw_text: str,
    reason: str,
    details: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Report a filtered/failed message to the triage Telegram channel.
    
    Args:
        category: Triage category (e.g., "extraction_error", "non_assignment")
        message_link: Link to original message
        channel: Channel name
        message_id: Message ID
        raw_text: Raw message text
        reason: Short reason for triage
        details: Additional details dict
        
    Returns:
        True if reported successfully, False otherwise
    """
    config = get_triage_config()
    chat_id = config.get("chat_id")
    
    if not chat_id:
        return False
    
    thread_id = get_thread_id_for_category(category)
    
    # Build triage message
    lines = [
        f"🚨 **{category.upper()}**",
        f"",
        f"**Reason:** {reason}",
        f"**Channel:** {channel}",
        f"**Message ID:** {message_id}",
    ]
    
    if message_link:
        lines.append(f"**Link:** {message_link}")
    
    if details:
        lines.append(f"")
        lines.append(f"**Details:**")
        for key, value in details.items():
            lines.append(f"  • {key}: {value}")
    
    lines.append(f"")
    lines.append(f"**Raw Text:**")
    lines.append(f"```")
    lines.append(raw_text[:1000] if len(raw_text) > 1000 else raw_text)
    if len(raw_text) > 1000:
        lines.append(f"... (truncated, {len(raw_text)} total chars)")
    lines.append(f"```")
    
    full_text = "\n".join(lines)
    
    # Split into chunks if needed
    chunks = chunk_text(full_text, max_length=4000)
    
    success = True
    for i, chunk in enumerate(chunks):
        if i > 0:
            # Add continuation marker
            chunk = f"(continued {i+1}/{len(chunks)})\n\n" + chunk
        
        result = send_telegram_message(
            to_chat_id=chat_id,
            text=chunk,
            thread_id=thread_id,
            bot_token=config.get("bot_token"),
            api_base=config.get("api_base")
        )
        
        if not result.get("ok"):
            logger.warning(
                f"Failed to send triage message (chunk {i+1}/{len(chunks)}): {result.get('error')}"
            )
            success = False
    
    return success
