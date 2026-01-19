from __future__ import annotations

from typing import Any, Dict, Optional


def _derive_external_id_for_tracking(payload: Dict[str, Any]) -> str:
    parsed = payload.get("parsed") or {}
    assignment_code = _join_text(parsed.get("assignment_code"))
    if assignment_code:
        # TutorCity API repeats the same assignment_code for updates. Track by assignment_code.
        return assignment_code
    channel_id = payload.get("channel_id")
    message_id = payload.get("message_id")
    if channel_id is not None and message_id is not None:
        return f"tg:{channel_id}:{message_id}"
    message_link = payload.get("message_link")
    if message_link:
        return str(message_link)
    cid = payload.get("cid")
    if cid:
        return str(cid)
    return "unknown"

def _build_message_link_from_payload(payload: Dict[str, Any]) -> str:
    """Best-effort reconstruction of a Telegram message link.

    Many payloads already include message_link; for those that do not, try to
    derive a usable URL from channel identifiers and message_id.
    """

    try:
        message_link = str(payload.get("message_link") or "").strip()
    except Exception:
        message_link = ""
    if message_link:
        return message_link

    try:
        msg_id = int(payload.get("message_id"))
    except Exception:
        msg_id = None

    try:
        channel_link = str(payload.get("channel_link") or "").strip()
    except Exception:
        channel_link = ""

    if channel_link:
        link = channel_link.rstrip('/')
        lower = link.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return f"{link}/{msg_id}" if msg_id is not None else link
        if lower.startswith("t.me/"):
            base = link.split('t.me/', 1)[-1].lstrip('/')
            if base:
                return f"https://t.me/{base}/{msg_id}" if msg_id is not None else f"https://t.me/{base}"
        if channel_link.startswith("@"):
            uname = channel_link.lstrip("@")
            return f"https://t.me/{uname}/{msg_id}" if msg_id is not None else f"https://t.me/{uname}"
        # If it's a bare username, treat it as such.
        return f"https://t.me/{channel_link}/{msg_id}" if msg_id is not None else f"https://t.me/{channel_link}"

    try:
        channel_username = str(payload.get("channel_username") or "").strip()
    except Exception:
        channel_username = ""
    if channel_username:
        uname = channel_username
        if uname.startswith("http://") or uname.startswith("https://"):
            uname = uname.rstrip('/').split('/')[-1]
        if uname.startswith("t.me/"):
            uname = uname.split('/')[-1]
        uname = uname.lstrip("@")
        if uname:
            return f"https://t.me/{uname}/{msg_id}" if msg_id is not None else f"https://t.me/{uname}"

    try:
        channel_id = int(payload.get("channel_id"))
    except Exception:
        channel_id = None
    if channel_id is not None and msg_id is not None:
        return f"https://t.me/c/{abs(channel_id)}/{msg_id}"

    return ""

def build_inline_keyboard(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a simple inline keyboard to surface the source message."""
    message_link = _build_message_link_from_payload(payload)
    if not message_link:
        return None

    # CLICK TRACKING DISABLED: Always use direct URL buttons instead of callback buttons
    # # Prefer using a callback button so Telegram clients open the URL natively
    # # while the bot receives a callback to record the click. Fallback to a
    # # direct URL button when no compact external id is available or it would
    # # exceed Telegram's callback_data size limits.
    # try:
    #     # Use tracking external id (assignment_code or tg:... id) where possible.
    #     ext = _derive_external_id_for_tracking(payload)
    # except Exception:
    #     ext = ""
    #
    # callback_prefix = "open:"
    # # Telegram limits callback_data to 64 bytes; reserve a small margin.
    # if ext and len(callback_prefix + ext) <= 60:
    #     button: Dict[str, Any] = {"text": "Open original post", "callback_data": f"{callback_prefix}{ext}"}
    #     return {"inline_keyboard": [[button]]}
    #
    # # Fallback to direct URL button when callback_data would be too long or ext missing.

    # Always use direct URL button (no click tracking)
    button: Dict[str, Any] = {"text": "Open original post", "url": message_link}
    return {"inline_keyboard": [[button]]}

