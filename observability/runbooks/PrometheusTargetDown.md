# PrometheusTargetDown

Meaning: Prometheus cannot scrape a target (`up == 0`).

What to check:
- `docker compose ps` for the failing service.
- Prometheus UI → Status → Targets for the error message.
- Logs: use `docker compose logs <container>` to inspect the target container's logs, or reintroduce Loki/Promtail for centralized log search.

