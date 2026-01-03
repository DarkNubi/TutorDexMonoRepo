# QueueStuckProcessing

Meaning: jobs are stuck in `processing` beyond the stale threshold.

What to check:
- Worker logs for crashes mid-job.
- DB/RPC locking issues.

Mitigation:
- The worker periodically requeues stale processing rows; if it’s not happening, restart the worker.

