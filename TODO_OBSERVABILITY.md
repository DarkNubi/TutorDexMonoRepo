# TutorDex Observability TODOs (Post-Beta)

Keep the current Telegram-based monitor for small scale. When usage grows, move toward standard observability tooling:

## Sentry (error tracking)
- Add Sentry SDK to `TutorDexBackend` (FastAPI) for exception + performance monitoring.
- Configure environments (`dev`/`staging`/`prod`) and release versioning.
- Add alert routing (email/Telegram/Slack) for high error rate / regressions.

## Prometheus + Grafana (metrics + dashboards)
- Expose metrics endpoints:
  - Backend: request count/latency/error rate, Redis ops latency/errors, Supabase ops latency/errors.
  - Aggregator: messages processed, skipped by reason, LLM latency, Supabase latency, Telegram send latency, DM send latency, rate-limit counts.
- Deploy Prometheus to scrape metrics and define alert rules.
- Deploy Grafana dashboards (SLO-style views + ops debugging).

## Loki (logs)
- Ship logs to Loki (Grafana Agent / Promtail).
- Add log panels and log-to-metrics correlations (e.g., `llm_extract_failed` spikes).

## Tracing (optional)
- Add OpenTelemetry tracing to correlate website/back-end requests and background jobs.

