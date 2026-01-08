# CollectorStalled

**Status**: This alert is currently **DISABLED** (see `observability/prometheus/alert_rules.yml` line 66: `expr: vector(0)`).

If you're still receiving notifications for this alert after disabling it, see the troubleshooting guide in [DisablingAlerts.md](DisablingAlerts.md).

---

Meaning: no messages were observed for a channel for too long.

What to check:
- `TutorDex Overview` → "Collector: seconds since last message" (which channels).
- Logs: use `docker compose logs collector-tail` and search for events related to the channel, or reintroduce Loki/Promtail for centralized log search.
- Telethon session/auth issues, channel access removed, Telegram rate limits.

Mitigation:
- Restart `collector-tail`.
- Re-auth session if needed (`telesess.py`).
