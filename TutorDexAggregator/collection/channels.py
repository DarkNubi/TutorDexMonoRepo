from __future__ import annotations

import json
from typing import Any, List, Optional


def parse_channels_from_env(cfg: Any) -> List[str]:
    raw = str(getattr(cfg, "channel_list", "") or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip().strip('"').strip("'") for x in items if str(x).strip()]
        except Exception:
            inner = raw[1:-1]
            return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    return [x.strip() for x in raw.split(",") if x.strip()]


def normalize_channel_ref(ch: str) -> str:
    s = str(ch or "").strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://"):
        s = s.rstrip("/")
        if "t.me/" in s:
            return "t.me/" + s.split("t.me/")[-1]
        return s
    if s.startswith("t.me/"):
        return s.rstrip("/")
    if s.startswith("@"):
        return "t.me/" + s[1:]
    return "t.me/" + s


def parse_channels_arg(channels_arg: Optional[str]) -> List[str]:
    if not channels_arg:
        return []
    s = str(channels_arg).strip()
    if not s:
        return []
    if s.startswith("[") and s.endswith("]"):
        try:
            arr = json.loads(s)
            if isinstance(arr, list):
                return [normalize_channel_ref(str(x)) for x in arr if str(x).strip()]
        except Exception:
            inner = s[1:-1]
            return [normalize_channel_ref(x.strip().strip('"').strip("'")) for x in inner.split(",") if x.strip()]
    return [normalize_channel_ref(x.strip()) for x in s.split(",") if x.strip()]


def channel_link_from_entity(entity: Any, fallback: str) -> str:
    if entity is None:
        return normalize_channel_ref(fallback)
    username = getattr(entity, "username", None)
    if username:
        return normalize_channel_ref(f"t.me/{username}")
    # Telethon channels may not have a username; keep the provided ref if it's already normalized.
    return normalize_channel_ref(fallback)

