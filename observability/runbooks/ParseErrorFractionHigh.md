# ParseErrorFractionHigh

Meaning: a large fraction of attempts are failing over the last window.

What to check:
- Is this isolated to one channel? Look at `worker_parse_failure_total` grouped by `channel`.
- Compare to recent prompt/schema/pipeline changes.

