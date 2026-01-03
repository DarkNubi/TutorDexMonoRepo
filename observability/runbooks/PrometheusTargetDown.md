# PrometheusTargetDown

Meaning: Prometheus cannot scrape a target (`up == 0`).

What to check:
- `docker compose ps` for the failing service.
- Prometheus UI → Status → Targets for the error message.
- Loki logs for the target container.

