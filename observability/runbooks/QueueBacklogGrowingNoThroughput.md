# QueueBacklogGrowingNoThroughput

Meaning: `queue_pending` is increasing but worker throughput is zero.

What to check:
- `queue_oldest_pending_age_seconds`
- Worker logs (`compose_service="aggregator-worker"`) for crashes or persistent failures.

Mitigation:
- Restart worker.
- Check LLM availability and Supabase connectivity.

