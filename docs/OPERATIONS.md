# TutorDex Operations Runbook

<!-- doc_lint:enforce -->
Doc type: How-to

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-18
**Review trigger:** Update when operational commands, runtime proof requirements, health checks, incident starts, or rollback paths change.

Current operator entrypoint for agents and humans running TutorDex checks from Strawberry HQ.

## Proof Rule

Before making any TutorDex health or outage claim, name the execution surface:

- local WSL shell
- BizServer Windows node
- Docker Desktop context
- compose project and env (`tutordex-staging` or `tutordex-prod`)
- in-container command
- public ingress/API URL
- Supabase/PostgREST/RPC surface

Keep these separate. A green local Docker stack is not BizServer production proof.

## Fast Orientation

From the repo root:

```bash
python3 scripts/docs_health.py
./scripts/tutordex_healthcheck.sh
```

With compose status for a known environment:

```bash
./scripts/tutordex_healthcheck.sh --env staging
./scripts/tutordex_healthcheck.sh --env prod
```

With a public API health endpoint:

```bash
./scripts/tutordex_healthcheck.sh --public-url https://example.tutordex.invalid
```

The helper is read-only. It does not source or print env files itself. When `--env staging|prod` is used, Docker Compose may read the selected env file for interpolation.

For prod `tutordex-api.duckdns.org`, distinguish three ingress surfaces:

- Backend-in-container: `http://backend:8000/health`
- LAN-SNI ingress monitor: blackbox probes `https://192.168.1.42/health` with Host/SNI `tutordex-api.duckdns.org` and relabels the result as the public URL
- True outside-WAN public availability: an external network probe to `https://tutordex-api.duckdns.org/health`

WSL/LAN curls to DuckDNS can fail on router hairpin/NAT even when Caddy and backend are healthy. Use mobile data, an external VM/CI runner, or another network for real public-WAN proof.

## Canonical Ops Commands

Use `scripts/ops/*` before ad-hoc Docker commands:

```bash
./scripts/ops/status.sh --env staging
./scripts/ops/status.sh --env prod
./scripts/ops/logs.sh --env prod aggregator-worker --since=30m
./scripts/ops/smoke.sh --env staging
./scripts/ops/smoke.sh --env prod
```

Prod-changing commands require explicit confirmation:

```bash
./scripts/ops/restart.sh --env prod --service aggregator-worker --yes
./scripts/ops/deploy.sh --env prod --yes
./scripts/ops/rollback.sh --env prod --to <git-ref> --yes
```

Do not run prod-changing commands unless the task explicitly calls for it and rollback/verification are understood.

## Health Checklist

Minimum healthy evidence for live TutorDex:

1. Correct surface identified: BizServer/public path, not stale local Docker.
2. Compose services are up for the intended env.
3. Backend `/health` responds on the intended ingress path.
4. Collector is current enough for the expected Telegram traffic window.
5. Extraction queue is not stuck with old `processing` or growing `pending` jobs.
6. Worker health endpoints or logs show active successful processing.
7. Public website/API path is checked separately when the user-facing surface matters.

If one of these cannot be checked from the current shell, write `unknown` and explain the missing surface.

## Runtime Proof Matrix

| Work type | Minimum proof | Surface label | Evidence caveat |
| --- | --- | --- | --- |
| Docs-only | `python3 scripts/docs_health.py`, `python3 scripts/docs_change_guard.py --changed-file docs/<file>` | Local WSL shell | No runtime health claimed |
| Local helper/script | `bash -n <script>`, helper `--help`, `git diff --check` | Local WSL shell | Does not prove BizServer |
| Staging status | `./scripts/ops/status.sh --env staging` | Docker/Desktop or BizServer, whichever actually ran | Name host/context |
| Staging smoke | `./scripts/ops/smoke.sh --env staging` | Selected compose env | Does not prove prod |
| Prod status | `./scripts/ops/status.sh --env prod` | BizServer/selected compose env | Requires explicit prod intent |
| Public API | `./scripts/tutordex_healthcheck.sh --public-url <url>` | Public ingress/API URL | Does not prove queue |
| LAN-SNI API monitor | Prometheus query for `probe_success{job="blackbox_http_public",probe_route="lan_sni"}` | Prod Prometheus in-container API | Not outside-WAN proof |
| Queue/Supabase | `scripts/ops/supabase_queue_health.sh --env <env>` | Supabase/PostgREST/RPC | Redact credentials |

## Collector And Catchup

Current pipeline:

1. `collector.py live` tails Telegram and runs bounded recovery catchup.
2. Raw Telegram messages are written to `public.telegram_messages_raw`.
3. Extraction jobs are queued in `public.telegram_extractions`.
4. `workers/extract_worker.py` claims jobs, extracts/canonicalizes, and persists assignments.

Canonical docs:

- `TutorDexAggregator/AGENTS.md`
- `docs/recovery_catchup.md`
- `docs/SYSTEM_INTERNAL.md`

Important rule: recovery catchup state alone is not full proof. Pair it with newest raw message time, queue depth, and worker/API health.

Suggested catchup closure for T2-2061/T2-2060 overlap: keep collector catchup as its own verification item. To close it, capture newest `telegram_messages_raw` timestamp, recovery cursor/state, pending/processing extraction counts, worker logs, and backend assignment freshness. If those agree, mark catchup healthy; if not, leave it as a separate backlog/catchup task instead of mixing it into ingress availability.

## Incident Starting Points

Collector stale:

- Check the actual production surface first.
- Inspect collector logs for Telethon/session collision, FloodWait, auth, or channel errors.
- Check newest `telegram_messages_raw` timestamp before assuming Telegram is quiet.
- Check `docs/recovery_catchup.md` before forcing manual backfills.

Queue backlog:

- Check `telegram_extractions` pending/processing counts.
- Inspect `aggregator-worker` logs.
- Confirm the worker `EXTRACTION_PIPELINE_VERSION` matches queued jobs.
- Disable side effects for manual reprocessing unless intentionally broadcasting/DMing.

API or website unhealthy:

- Check backend `/health` on the intended ingress path.
- Check compose service state separately.
- Check Firebase/website deployment flow in `docs/DEPLOYMENT_RELEASE_FLOW.md` before claiming production website deploy behavior.

Observability noisy:

- Start with `observability/README.md` and `observability/runbooks/`.
- Keep Grafana/Prometheus/Alertmanager evidence separate from application API evidence.

## Secrets And Logs

Never paste:

- `.env` contents
- Telegram API credentials or session strings
- Supabase service role keys
- Firebase service account JSON
- bot tokens
- cookies or auth headers

When logs may include secrets, summarize and redact.

## Verification Record Template

For non-trivial ops/coding work, final notes should include:

```text
Task: <id or none>
Surface checked: <WSL/BizServer/Docker/public/Supabase>
Files changed: <paths>
Invariant at risk: <what could break>
Proving check: <command or inspection>
Result: pass/fail/unknown
Evidence path: <workspace/state_saves/... or none>
Rollback: <git revert / restore files / service rollback>
```

Do not say "done" for live ops until the task state, docs, and verification evidence agree.
