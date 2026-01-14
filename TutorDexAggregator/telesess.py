from telethon.sync import TelegramClient
from telethon.sessions import StringSession

from shared.config import load_aggregator_config

cfg = load_aggregator_config()
api_id_raw = str(cfg.telegram_api_id or "").strip()
api_hash = str(cfg.telegram_api_hash or "").strip()
if not api_id_raw or not api_hash:
    raise SystemExit('Set TELEGRAM_API_ID and TELEGRAM_API_HASH in your environment before running this script')
api_id = int(api_id_raw)

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("Your session string:")
    print(client.session.save())
