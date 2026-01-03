# CollectorStalled

Meaning: no messages were observed for a channel for too long.

What to check:
- `TutorDex Overview` → “Collector: seconds since last message” (which channels).
- Loki logs for `compose_service="collector-tail"` and that `channel`.
- Telethon session/auth issues, channel access removed, Telegram rate limits.

Mitigation:
- Restart `collector-tail`.
- Re-auth session if needed (`telesess.py`).

