from __future__ import annotations

import os
from typing import Any, Tuple

from telethon import TelegramClient

from collection.utils import truthy


class MissingTelegramCredentials(RuntimeError):
    pass


try:
    from telethon.sessions import StringSession
except Exception:
    StringSession = None  # type: ignore


def enqueue_enabled(cfg: Any) -> bool:
    v = getattr(cfg, "extraction_queue_enabled", None)
    if v is not None:
        return bool(v)
    return truthy(os.getenv("EXTRACTION_QUEUE_ENABLED"))


def pipeline_version(cfg: Any) -> str:
    v = str(getattr(cfg, "extraction_pipeline_version", "") or "").strip()
    return v or "unknown"


def get_telegram_config(cfg: Any) -> Tuple[int, str, str, str]:
    api_id = int(getattr(cfg, "telegram_api_id", 0) or 0)
    api_hash = str(getattr(cfg, "telegram_api_hash", "") or "").strip()
    session_string = str(getattr(cfg, "session_string", "") or "").strip()
    device_model = str(getattr(cfg, "telegram_device_model", "TutorDexCollector") or "TutorDexCollector")
    if not (api_id and api_hash and session_string):
        raise MissingTelegramCredentials(
            "Missing Telegram credentials. Set TELEGRAM_API_ID, TELEGRAM_API_HASH and SESSION_STRING (or TELEGRAM_SESSION_STRING)."
        )
    return api_id, api_hash, session_string, device_model


def build_client(cfg: Any) -> TelegramClient:
    api_id, api_hash, session_string, device_model = get_telegram_config(cfg)
    if StringSession is None:
        raise SystemExit("Telethon StringSession unavailable; check Telethon install.")
    return TelegramClient(StringSession(session_string), api_id, api_hash, device_model=device_model)
