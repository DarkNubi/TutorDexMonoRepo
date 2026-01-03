# HostDiskLow

Meaning: host filesystem free space is < 10%.

What to check:
- `docker system df` (images/volumes buildup)
- `du -sh` for `prometheus_data`, `loki_data`, `grafana_data`, `tempo_data` volumes

Mitigation:
- Increase disk or prune old data.
- Reduce retentions (Prometheus `PROMETHEUS_RETENTION`, Loki `retention_period`).

