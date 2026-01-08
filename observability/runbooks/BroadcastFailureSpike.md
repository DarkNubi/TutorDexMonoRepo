# BroadcastFailureSpike

Meaning: Telegram broadcast sends are failing.

What to check:
- Loki logs `component="broadcast"` and `broadcast_send_failed`.
 - Logs: use `docker compose logs <service>` and search for `component="broadcast"` and `broadcast_send_failed`, or reintroduce Loki/Promtail if you need centralized log search.
- Telegram bot token permissions, channel id, rate limiting.

