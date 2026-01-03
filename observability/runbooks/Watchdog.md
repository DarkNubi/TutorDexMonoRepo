# Watchdog

Purpose: validate Alertmanager → Telegram delivery.

If you stop receiving this for >24h:
- Check `alertmanager` is up and reachable by Prometheus.
- Check `alertmanager-telegram` logs and Telegram env vars.

