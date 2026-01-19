import json
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from shared.config import load_aggregator_config

from logging_setup import log_event, setup_logging, timed
from shared.observability.exception_handler import swallow_exception


setup_logging()
logger = logging.getLogger("telegram_chat_id_helper")

HERE = Path(__file__).resolve().parent
OFFSET_FILE = HERE / "dm_bot_offset.json"


def _load_offset() -> int:
    try:
        data = json.loads(OFFSET_FILE.read_text(encoding="utf-8"))
        return int(data.get("offset") or 0)
    except Exception:
        return 0


def _save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(json.dumps({"offset": int(offset)}, indent=2), encoding="utf-8")


def _bot_api_base(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def fetch_updates(token: str, *, offset: int = 0, limit: int = 100) -> Dict[str, Any]:
    url = f"{_bot_api_base(token)}/getUpdates"
    t0 = timed()
    resp = requests.get(url, params={"timeout": 0, "offset": offset, "limit": limit}, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    log_event(logger, logging.DEBUG, "get_updates_ok", offset=offset, limit=limit, elapsed_ms=round((timed() - t0) * 1000.0, 2))
    return data


def _extract_chat(update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    msg = update.get("message") or update.get("edited_message") or update.get("channel_post") or update.get("callback_query", {}).get("message")
    if not isinstance(msg, dict):
        return None
    chat = msg.get("chat")
    if not isinstance(chat, dict):
        return None
    return {
        "chat_id": chat.get("id"),
        "type": chat.get("type"),
        "username": chat.get("username"),
        "title": chat.get("title"),
        "first_name": chat.get("first_name"),
        "last_name": chat.get("last_name"),
        "text": msg.get("text") or msg.get("caption"),
    }


def list_unique_chats(updates: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
    uniq: Dict[str, Dict[str, Any]] = {}
    max_update_id = 0
    for upd in updates:
        try:
            max_update_id = max(max_update_id, int(upd.get("update_id") or 0))
        except Exception:
            pass
        chat = _extract_chat(upd)
        if not chat:
            continue
        cid = chat.get("chat_id")
        if cid is None:
            continue
        key = str(cid)
        if key not in uniq:
            uniq[key] = chat
    return list(uniq.values()), max_update_id


def main() -> None:
    p = argparse.ArgumentParser(description="List Telegram chat_ids seen by the DM bot (via getUpdates).")
    p.add_argument("--token", help="Bot token (defaults to DM_BOT_TOKEN env var)")
    p.add_argument("--limit", type=int, default=100, help="Max updates to fetch (default 100)")
    p.add_argument("--offset", type=int, default=None, help="Override offset (default reads dm_bot_offset.json)")
    p.add_argument("--commit-offset", action="store_true", help="Persist next offset (max_update_id + 1) to dm_bot_offset.json")
    args = p.parse_args()

    cfg = load_aggregator_config()
    token = (args.token or cfg.dm_bot_token or cfg.group_bot_token or "").strip()
    if not token:
        raise SystemExit("Set DM_BOT_TOKEN (preferred) or pass --token.")

    offset = args.offset if args.offset is not None else _load_offset()
    log_event(logger, logging.INFO, "get_updates_start", offset=offset, limit=args.limit)
    data = fetch_updates(token, offset=offset, limit=args.limit)
    if not data.get("ok"):
        log_event(logger, logging.ERROR, "get_updates_error", response=str(data)[:500])
        raise SystemExit(f"Telegram API error: {data}")

    updates = data.get("result") or []
    if not isinstance(updates, list):
        updates = []

    chats, max_update_id = list_unique_chats(updates)
    chats.sort(key=lambda c: str(c.get("chat_id")))

    log_event(logger, logging.INFO, "get_updates_summary", updates=len(updates), unique_chats=len(chats), offset=offset)
    print(f"Fetched {len(updates)} updates (offset={offset}). Unique chats: {len(chats)}")
    for c in chats:
        who = c.get("username") or c.get("title") or " ".join([x for x in [c.get("first_name"), c.get("last_name")] if x]) or "<unknown>"
        print(f"- chat_id={c.get('chat_id')} type={c.get('type')} who={who} text={str(c.get('text') or '')[:80]}")

    if args.commit_offset and max_update_id:
        next_offset = int(max_update_id) + 1
        _save_offset(next_offset)
        log_event(logger, logging.INFO, "offset_committed", next_offset=next_offset, path=str(OFFSET_FILE))
        print(f"Committed offset={next_offset} to {OFFSET_FILE}")


if __name__ == "__main__":
    main()
