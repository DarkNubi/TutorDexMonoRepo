import logging
import os
from typing import Any, Dict, Optional

import requests

from supabase_persist import SupabaseConfig, SupabaseRestClient, _derive_external_id, load_config_from_env  # type: ignore


logger = logging.getLogger("click_tracking_store")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _enabled(cfg: SupabaseConfig) -> bool:
    return bool(cfg.enabled and cfg.url and cfg.key)


def upsert_broadcast_message(*, payload: Dict[str, Any], sent_chat_id: int, sent_message_id: int, message_html: str) -> bool:
    cfg = load_config_from_env()
    if not _enabled(cfg):
        return False

    original_url = str(payload.get("message_link") or "").strip()
    if not original_url:
        return False

    external_id = _derive_external_id(payload)
    if not external_id:
        return False

    client = SupabaseRestClient(cfg)

    # Ensure assignment_clicks exists (best-effort). The backend RPC also upserts, but this preserves original_url early.
    try:
        client.post(
            "assignment_clicks?on_conflict=external_id",
            [{"external_id": external_id, "original_url": original_url}],
            timeout=20,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    except Exception:
        pass

    row = {
        "external_id": external_id,
        "original_url": original_url,
        "sent_chat_id": int(sent_chat_id),
        "sent_message_id": int(sent_message_id),
        "message_html": str(message_html),
    }

    try:
        resp = client.post(
            "broadcast_messages?on_conflict=external_id",
            [row],
            timeout=20,
            prefer="resolution=merge-duplicates,return=minimal",
        )
        if resp.status_code >= 400:
            logger.debug("broadcast_messages_upsert_failed status=%s body=%s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception as e:
        logger.debug("broadcast_messages_upsert_error error=%s", e)
        return False

