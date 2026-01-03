# BroadcastFailureSpike

Meaning: Telegram broadcast sends are failing.

What to check:
- Loki logs `component="broadcast"` and `broadcast_send_failed`.
- Telegram bot token permissions, channel id, rate limiting.

