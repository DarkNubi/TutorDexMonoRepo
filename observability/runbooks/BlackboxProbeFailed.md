# BlackboxProbeFailed

Meaning: the HTTP health endpoint probe is failing.

What to check:
- Confirm the service container is running.
- `curl` the failing target URL from inside the network (or use Grafana Explore → Prometheus → `probe_*` metrics).
- If it’s `/health/dependencies`, check Supabase/Redis/LLM reachability.

