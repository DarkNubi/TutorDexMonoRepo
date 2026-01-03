# DMRateLimited

Meaning: Telegram 429s are occurring during DM sends.

Mitigation:
- Reduce DM fanout (`DM_MAX_RECIPIENTS`) or add per-chat throttling.
- Consider batching and longer sleeps.

