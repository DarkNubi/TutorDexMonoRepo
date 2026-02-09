import json
import time
import argparse
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import requests

from TutorDexBackend.logging_setup import setup_logging
from shared.config import load_backend_config


HERE = Path(__file__).resolve().parent
_CFG = load_backend_config()

def _offset_file_path() -> Path:
    override = str(_CFG.link_bot_offset_file or "").strip()
    if override.strip():
        return Path(override.strip())
    return HERE / "telegram_link_bot_offset.json"


def _load_offset() -> int:
    try:
        offset_file = _offset_file_path()
        data = json.loads(offset_file.read_text(encoding="utf-8"))
        return int(data.get("offset") or 0)
    except Exception:
        return 0


def _save_offset(offset: int) -> None:
    offset_file = _offset_file_path()
    offset_file.parent.mkdir(parents=True, exist_ok=True)
    offset_file.write_text(json.dumps({"offset": int(offset)}, indent=2), encoding="utf-8")


def _bot_base(token: str) -> str:
    return f"https://api.telegram.org/bot{token}"


def _send_message(token: str, chat_id: str, text: str) -> None:
    url = f"{_bot_base(token)}/sendMessage"
    requests.post(
        url,
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )


def _parse_link_command(text: str) -> Optional[str]:
    if not text:
        return None
    t = str(text).strip()
    # Telegram may send commands as `/link@YourBotUsername <code>` in some contexts.
    parts = t.split()
    if not parts:
        return None

    cmd = parts[0].strip()
    arg = parts[1].strip() if len(parts) >= 2 else ""

    if cmd == "/link" or cmd.startswith("/link@"):
        return arg or None

    # Telegram deep links to bots use: https://t.me/<bot>?start=<payload>
    # which arrives as: `/start <payload>` (or `/start@Bot <payload>`).
    if cmd == "/start" or cmd.startswith("/start@"):
        if not arg:
            return None
        a = arg.strip()
        if a.lower().startswith("link_") and len(a) > 5:
            return a[5:]
        return a

    return None


def _extract_message(update: Dict[str, Any]) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    msg = update.get("message") or update.get("edited_message")
    if not isinstance(msg, dict):
        return None, None, None
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    text = msg.get("text")
    username = (chat.get("username") or "").strip() or None
    return chat_id, text, username


def main() -> None:
    setup_logging(service_name="tutordex_telegram_link_bot")
    logger = logging.getLogger("tutordex_telegram_link_bot")

    p = argparse.ArgumentParser(description="Poll Telegram DM bot updates and link chat_id via /link <code> (or /start link_<code>).")
    p.add_argument("--token", help="Bot token (defaults to DM_BOT_TOKEN env var)")
    p.add_argument("--backend-url", help="Backend base URL (defaults to BACKEND_URL or http://127.0.0.1:8000)")
    p.add_argument("--poll-seconds", type=float, default=2.0, help="Polling interval (default 2s)")
    args = p.parse_args()

    token = (args.token or str(_CFG.dm_bot_token or "")).strip()
    if not token:
        raise SystemExit("Set DM_BOT_TOKEN or pass --token.")

    backend = (args.backend_url or str(_CFG.backend_url or "") or "http://127.0.0.1:8000").strip().rstrip("/")
    claim_url = f"{backend}/telegram/claim"
    api_key = str(_CFG.admin_api_key or "").strip()

    offset = _load_offset()
    logger.info("starting", extra={"offset": offset, "claim_url": claim_url})

    while True:
        try:
            resp = requests.get(
                f"{_bot_base(token)}/getUpdates",
                # NOTE: This bot must receive user DMs (message updates). Some deployments
                # configure the bot to only receive callback queries (e.g., for inline buttons),
                # which would otherwise cause /link and /start messages to never appear here.
                params={
                    "timeout": 0,
                    "offset": offset,
                    "limit": 50,
                    # Telegram expects a JSON-serialized list.
                    "allowed_updates": json.dumps(["message", "edited_message"]),
                },
                timeout=20,
            )
            if resp.status_code == 409:
                # Common when a webhook is set (or another long-poller is running).
                # Avoid leaking the bot token in tracebacks by handling this explicitly.
                try:
                    requests.post(
                        f"{_bot_base(token)}/deleteWebhook",
                        params={"drop_pending_updates": False},
                        timeout=20,
                    )
                    logger.warning("telegram_getupdates_conflict_409_deleted_webhook")
                except Exception as e:
                    logger.warning("telegram_getupdates_conflict_409_delete_webhook_failed error_type=%s", type(e).__name__)
                time.sleep(5)
                continue

            if resp.status_code >= 400:
                logger.error("telegram_getupdates_http_error status_code=%s body=%s", resp.status_code, (resp.text or "")[:200].replace("\n", " "))
                time.sleep(5)
                continue

            data = resp.json()
            if not data.get("ok"):
                logger.error("telegram_getupdates_api_error payload=%s", json.dumps(data)[:500])
                time.sleep(5)
                continue

            updates = data.get("result") or []
            if not isinstance(updates, list):
                updates = []

            for upd in updates:
                upd_id = int(upd.get("update_id") or 0)
                offset = max(offset, upd_id + 1)

                chat_id, text, username = _extract_message(upd)
                if chat_id is None:
                    continue

                code = _parse_link_command(text)
                if not code:
                    continue

                try:
                    headers = {"x-api-key": api_key} if api_key else None
                    claim_resp = requests.post(
                        claim_url,
                        json={"code": code, "chat_id": str(chat_id), "telegram_username": username},
                        headers=headers,
                        timeout=10,
                    )
                    if claim_resp.status_code < 400:
                        _send_message(token, str(chat_id), "Linked. You can now receive TutorDex DMs.")
                    elif claim_resp.status_code in (401, 403):
                        _send_message(token, str(chat_id), "Link failed (unauthorized). Please contact admin to check backend API key.")
                    elif claim_resp.status_code == 404:
                        _send_message(token, str(chat_id), "Invalid/expired code. Please generate a new link code on the website.")
                    else:
                        _send_message(token, str(chat_id), "Link failed due to a server error. Please try again later.")
                    logger.info(
                        "link_attempt chat_id=%s username=%s status_code=%s body=%s",
                        chat_id,
                        username or "-",
                        claim_resp.status_code,
                        (claim_resp.text or "")[:200].replace("\n", " "),
                    )
                except Exception:
                    _send_message(token, str(chat_id), "Link failed due to a server error. Please try again later.")
                    logger.exception("claim_error", extra={"chat_id": chat_id, "username": username})

            _save_offset(offset)
        except Exception:
            logger.exception("poll_error")

        time.sleep(max(0.5, float(args.poll_seconds)))


if __name__ == "__main__":
    main()
