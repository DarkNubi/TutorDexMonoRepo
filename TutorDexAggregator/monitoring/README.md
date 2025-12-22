# TutorDex Monitoring (log-based + Telegram alerts)

This folder provides a lightweight monitoring/alert loop for the home server setup.

## What it does

`monitor.py` runs continuously and:
- Sends **alerts** to Telegram when:
  - aggregator heartbeat stops updating (process stalled/down)
  - backend health check fails (backend/redis/supabase via `/health/full`)
  - error spikes appear in the aggregator log (Telegram rate limits, LLM failures, Supabase failures, DM/broadcast failures)
- Sends a **daily “pipeline health summary”** (last 24h) to the same Telegram destination.

## Why Telegram threads are a good choice

For the current “home server” phase, Telegram is a great ops channel:
- you already live in Telegram for product distribution
- instant push notifications
- threads keep noise contained (alerts in one topic, discussion in another)

Longer-term (V1.0), you can add:
- Sentry (backend exceptions)
- PostHog/Amplitude (product analytics)
- Grafana/Prometheus (metrics), if you want full observability

Tracked TODOs: `TODO_OBSERVABILITY.md`.

## Setup

1) Ensure `TutorDexAggregator/.env` contains:
- `ALERT_BOT_TOKEN` (recommended: a dedicated ops bot token)
- `ALERT_CHAT_ID` (admin group chat id, often `-100...`)
- optional `ALERT_THREAD_ID` (topic id inside that group)
- `MONITOR_BACKEND_HEALTH_URL` (recommended: `http://127.0.0.1:8000/health/full`)

2) Run it:
- `python monitoring/monitor.py`

Windows loop wrapper:
- `TutorDexAggregator/setup_service/start_monitor_loop.bat`

Docker:
- `docker compose -f TutorDexAggregator/docker-compose.monitor.yml up -d`

## Notes

- The aggregator writes a heartbeat file at `HEARTBEAT_FILE` (default `monitoring/heartbeat.json`) and emits a periodic tick (`HEARTBEAT_TICK_SECONDS`) so “quiet periods” do not trigger false down alerts.
- Monitor state (log offset + alert cooldowns) is stored in `monitoring/monitor_state.json`.
