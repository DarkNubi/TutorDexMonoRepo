# TutorDex Runbooks

These runbooks are referenced from Prometheus alert annotations.

General triage flow:
1) Check Grafana `TutorDex Overview` for stalled components / queue health.
2) Check `TutorDex Quality` for parse failures and missing-field spikes.
3) Use the Logs panel (Loki) filtered by `compose_service` + `channel` + `pipeline_version`.

