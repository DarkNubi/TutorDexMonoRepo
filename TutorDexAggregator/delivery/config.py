# broadcast_assignments config/runtime

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional


from logging_setup import setup_logging
from shared.config import load_aggregator_config

# NOTE: This file lives under `delivery/`, but we want paths relative to `TutorDexAggregator/`.
HERE = Path(__file__).resolve().parents[1]

setup_logging()
logger = logging.getLogger("broadcast_assignments")
_CFG = load_aggregator_config()

# Prefer explicit BOT_API_URL, otherwise build from available tokens.
BOT_API_URL = str(_CFG.bot_api_url or "").strip() or None
# tokens provided in .env: DM_BOT_TOKEN, GROUP_BOT_TOKEN
BOT_TOKEN = str(_CFG.group_bot_token or "").strip() or None
# target channel(s): prefer explicit AGGREGATOR_CHANNEL_IDS (plural, JSON list), fallback to AGGREGATOR_CHANNEL_ID (singular)
_target_chat_single = _CFG.aggregator_channel_id
_target_chat_multi = _CFG.aggregator_channel_ids
TARGET_CHATS: list[Any] = []  # populated below
_default_fallback_file = str(HERE / "outgoing_broadcasts.jsonl")
FALLBACK_FILE = str(_CFG.broadcast_fallback_file or _default_fallback_file)
# Enable broadcast message tracking (for sync/reconciliation)
ENABLE_BROADCAST_TRACKING = bool(_CFG.enable_broadcast_tracking)


def _normalize_target_chat(chat: Optional[Any]) -> Optional[Any]:
    if chat is None:
        return None
    # preserve ints coming from env or upstream
    if isinstance(chat, int):
        return chat

    t = str(chat).strip()
    if not t:
        return None

    # Telegram chat ids (channels/groups) are ints, often starting with -100
    if t.lstrip("-").isdigit():
        try:
            return int(t)
        except ValueError:
            return t

    lower_t = t.lower()
    if lower_t.startswith("https://") or lower_t.startswith("http://"):
        try:
            t = t.rstrip("/").split("/")[-1]
        except Exception:
            pass
    elif lower_t.startswith("t.me/"):
        t = t.split("/")[-1]

    if not t.startswith("@"):
        t = f"@{t}"
    return t


# Parse target chats: support both single and multiple channels
if _target_chat_multi:
    # Try to parse as JSON list
    try:
        parsed = json.loads(_target_chat_multi)
        if isinstance(parsed, list):
            TARGET_CHATS = [_normalize_target_chat(c) for c in parsed if c]
        else:
            TARGET_CHATS = [_normalize_target_chat(parsed)] if parsed else []
    except Exception:
        logger.warning("Failed to parse AGGREGATOR_CHANNEL_IDS as JSON, treating as single value")
        TARGET_CHATS = [_normalize_target_chat(_target_chat_multi)] if _target_chat_multi else []
elif _target_chat_single:
    TARGET_CHATS = [_normalize_target_chat(_target_chat_single)]

# Remove None values
TARGET_CHATS = [c for c in TARGET_CHATS if c is not None]

# Maintain backward compatibility: TARGET_CHAT is the first channel (or None)
TARGET_CHAT = TARGET_CHATS[0] if TARGET_CHATS else None

if not BOT_API_URL and not BOT_TOKEN:
    logger.warning("No BOT_API_URL or BOT_TOKEN set - broadcaster will write to %s instead of sending", FALLBACK_FILE)

if not BOT_API_URL and BOT_TOKEN:
    BOT_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

if TARGET_CHATS:
    logger.info("Broadcast targets configured: %s", TARGET_CHATS)

