# PrometheusTargetDown

Meaning: Prometheus cannot scrape a target (`up == 0`).

What to check:
- `docker compose ps` for the failing service.
- Prometheus UI → Status → Targets for the error message.
- Logs: use `docker compose logs <container>` to inspect the target container's logs, or reintroduce Loki/Promtail for centralized log search.
- If the failing target is an app metrics scrape, confirm Prometheus is using the stable compose service DNS name (`backend`, `collector-tail`, `aggregator-worker`) instead of a generated container name (`tutordex-prod-...-1`). Container names can become stale after recreate or scale operations.
