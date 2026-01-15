# QueueStuckProcessing

Meaning: jobs are stuck in `processing` beyond the stale threshold.

Note on notifications:
- A Telegram `RESOLVED` message may still show a large “oldest processing job age” because Alertmanager includes the last observed value before the alert cleared.

What to check:
- Worker logs for crashes mid-job.
- DB/RPC locking issues.

Mitigation:
- The worker periodically requeues stale processing rows; if it’s not happening, restart the worker.
