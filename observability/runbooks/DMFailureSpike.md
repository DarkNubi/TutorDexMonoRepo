# DMFailureSpike

Meaning: DM sends are failing at elevated rate.

What to check:
- Loki logs `component="dm"`, `dm_send_failed`, and `dm_match_ok`.
- Backend match endpoint health and bot rate limits.

