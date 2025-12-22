from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import os

api_id_raw = os.environ.get('TELEGRAM_API_ID') or os.environ.get('TG_API_ID') or os.environ.get('API_ID')
api_hash = os.environ.get('TELEGRAM_API_HASH') or os.environ.get('TG_API_HASH') or os.environ.get('API_HASH')
if not api_id_raw or not api_hash:
    raise SystemExit('Set TELEGRAM_API_ID and TELEGRAM_API_HASH in your environment before running this script')
api_id = int(api_id_raw)

with TelegramClient(StringSession(), api_id, api_hash) as client:
    print("Your session string:")
    print(client.session.save())
