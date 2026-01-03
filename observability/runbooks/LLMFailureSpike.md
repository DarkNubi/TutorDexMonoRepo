# LLMFailureSpike

Meaning: LLM calls are failing at elevated rate.

What to check:
- `TutorDex LLM + Supabase` dashboard (LLM latency + request rate).
- Worker logs for `llm_extract_failed` and network errors.

Mitigation:
- Ensure LLM endpoint is reachable from Docker (LM Studio binding / firewall).
- Reduce concurrency / increase timeout if needed.

