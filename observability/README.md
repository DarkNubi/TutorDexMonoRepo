# Observability (Prometheus + Grafana + Loki + Alertmanager)

This repo runs observability **fully in Docker** via the root `docker-compose.yml`.

## Start everything

- `docker compose up -d --build`

## URLs (defaults)

- Grafana: `http://localhost:3300`
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Loki: `http://localhost:3100`
- Tempo (traces backend): `http://localhost:3200`

## Grafana login

- User: `admin` (override with `GRAFANA_ADMIN_USER`)
- Password: `admin` (override with `GRAFANA_ADMIN_PASSWORD`)

## What’s wired

- Metrics: services expose `/metrics` internally; Prometheus scrapes them.
- Logs: services emit structured JSON logs to stdout; Promtail ships them to Loki; Grafana queries Loki.
- Alerts: Prometheus evaluates rules; Alertmanager routes alerts to Telegram via `alertmanager-telegram`.
- Traces (optional): Tempo + OTEL collector are running; app tracing is enabled only if you install OTEL SDKs and set `OTEL_ENABLED=1`.

## Quick sanity check

- `./observability/doctor.sh`

## Cardinality rules

See `observability/CARDINALITY.md`.

