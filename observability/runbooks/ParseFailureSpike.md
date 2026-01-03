# ParseFailureSpike

Meaning: jobs are failing to parse or validate at elevated rate.

What to check:
- `TutorDex Quality` → failures by `reason`.
- Worker logs around `llm_invalid_json`, `schema_validation_failed`, and `supabase_persist_failed`.

Mitigation:
- If `llm_invalid_json`: adjust prompt / model / json-repair availability.
- If `schema_validation_failed`: schema drift or model output regression.

