# TutorDex Runbooks

These runbooks are referenced from Prometheus alert annotations.

General triage flow:
1) Check Grafana `TutorDex Overview` for stalled components / queue health.
2) Check `TutorDex Quality` for parse failures and missing-field spikes.
3) Logs: central log aggregation via Loki/Promtail is not included in the default stack. Use `docker compose logs <service>` to inspect container logs, or reintroduce Loki/Promtail for centralized search.

## Operational Runbooks

- **[DisablingAlerts.md](DisablingAlerts.md)** - How to disable/modify alerts and troubleshoot when changes don't take effect

