# DMFailureSpike

Meaning: DM sends are failing at elevated rate.

What to check:
- Logs: use `docker compose logs <service>` and search for `component="dm"`, `dm_send_failed`, or `dm_match_ok`, or reintroduce Loki/Promtail for centralized log search.
- Backend match endpoint health and bot rate limits.

