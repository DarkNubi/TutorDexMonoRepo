# HostDiskLow

Meaning: host filesystem free space is < 10%.

What to check:
- `docker system df` (images/volumes buildup)
- `du -sh` for `prometheus_data`, `grafana_data`, `tempo_data` volumes (remove `loki_data` if Loki is not present)

Mitigation:
- Increase disk or prune old data.
- Reduce retentions (Prometheus `PROMETHEUS_RETENTION`). If using Loki, also reduce `retention_period`.

