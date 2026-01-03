# QueueOldestPendingTooOld

Meaning: pending jobs are not being drained fast enough.

What to check:
- Worker throughput panel.
- Any spikes in parse failures or Supabase failures.

Mitigation:
- Increase worker resources or run more workers (future scaling).
- Fix upstream failures causing requeues.

