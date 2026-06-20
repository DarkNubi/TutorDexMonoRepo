# TutorDex Testing

<!-- doc_lint:enforce -->
Doc type: How-to

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-20
**Review trigger:** Update when test commands, proof gates, CI gates, docs health, or evidence requirements change.

Proof gates and test entry points for TutorDex. Use this with `OPERATIONS.md` when deciding what a change proves.

## Test Layers

Static and syntax:

```bash
ruff check .
python scripts/check_no_bare_except.py
./check_python.sh
```

Python tests:

```bash
pytest tests/
pytest tests/test_backend_api.py
pytest tests/test_assignment_rating.py
pytest tests/test_academic_requests.py
```

Website:

```bash
cd TutorDexWebsite
npm test
npm run build
npm run build:staging
npm run build:prod
```

Smoke tests:

```bash
scripts/smoke_test_all.sh
scripts/smoke_test_backend.sh
scripts/smoke_test_aggregator.sh
scripts/smoke_test_observability.sh
```

Ops smoke for environment-specific checks:

```bash
./scripts/ops/smoke.sh --env staging
./scripts/ops/smoke.sh --env prod
```

## What Each Gate Proves

- `ruff check .` proves basic Python lint hygiene.
- `python scripts/check_no_bare_except.py` proves bare `except:` is not reintroduced.
- `./check_python.sh` proves Python syntax/import-level compilation for configured paths.
- `pytest tests/` proves unit/integration behavior covered by the repo test suite.
- `npm test` proves frontend tests under `TutorDexWebsite/test`.
- `npm run build*` proves the website bundle builds for the selected mode.
- `scripts/smoke_test_backend.sh` proves backend health and selected API/Supabase behavior depending on env availability.
- `scripts/smoke_test_aggregator.sh` proves worker/collector health endpoints are reachable through the configured backend URL.
- `scripts/smoke_test_observability.sh` proves observability endpoints are reachable.
- `scripts/ops/smoke.sh --env ...` proves the selected compose env from that execution surface, including container-level worker health.

## Surface Rule

Every smoke result is scoped to the surface where it ran. State one of:

- local WSL shell
- BizServer Windows node
- Docker Desktop context
- compose project/env
- in-container command
- public ingress/API URL
- Supabase/PostgREST/RPC surface

Do not report local smoke output as BizServer or public production proof.

## Minimal Gates By Change Type

Docs-only:

```bash
python3 scripts/docs_health.py
python3 scripts/docs_change_guard.py --base HEAD
rg -n "<new doc names or pointers>" AGENTS.md docs/
git diff --check
```

Shell helper:

```bash
bash -n <script>
<script> --help
git diff --check
```

Aggregator extraction or persistence:

```bash
pytest tests/test_academic_requests.py tests/test_compilation_detection.py tests/test_agency_regression_suite.py
pytest tests/
scripts/smoke_test_aggregator.sh
```

Backend/API:

```bash
pytest tests/test_backend_api.py tests/test_backend_auth.py tests/test_backend_admin.py
scripts/smoke_test_backend.sh
```

Website:

```bash
cd TutorDexWebsite
npm test
npm run build
```

Deployment or ops:

```bash
./scripts/tutordex_healthcheck.sh --env staging
./scripts/ops/status.sh --env staging
./scripts/ops/smoke.sh --env staging
```

Prod ops require explicit prod evidence and rollback notes.

## CI Gates

GitHub Actions currently include:

- `.github/workflows/docs-health.yml` (warning-first docs health)
- `.github/workflows/python-lint.yml`
- `.github/workflows/import-lint.yml`
- `.github/workflows/contracts-validate.yml`
- `.github/workflows/taxonomy-validate.yml`
- `.github/workflows/security-scan.yml`
- `.github/workflows/deploy.yml`
- `.github/workflows/firebase-hosting.yml`

CI is useful evidence, but it does not replace environment-specific smoke checks after deployment.

## Proof Matrix

| Change type | Required checks | Expected result | Skip/unknown rule |
| --- | --- | --- | --- |
| Docs routing / canonical docs | `python3 scripts/docs_health.py`; targeted `rg`; `git diff --check` | Docs health PASS and pointers present | Fix before done; do not waive unless tool unavailable |
| Docs guard / inventory scripts | `python3 -m py_compile scripts/docs_health.py scripts/docs_change_guard.py scripts/docs_inventory.py`; script help/run | Exit 0 and non-secret output | Record exact stderr if unavailable |
| Shell ops helper | `bash -n`; `--help`; read-only dry run | Exit 0 or documented unavailable dependency | Dependency failures are unknown, not live outage |
| Aggregator extraction/persistence | Targeted pytest plus docs guard | Tests pass and docs update/skip recorded | If LLM/Supabase unavailable, run local unit slice and record gap |
| BizServer host LLM | `schtasks /Query /TN TutorDexLlamaServer /FO LIST /V`; host `/v1/models`; worker `/v1/models` or `/v1/chat/completions` | SYSTEM startup task and worker route both pass | Startup-safe config is not a real reboot test |
| Backend/API | Backend pytest plus smoke where reachable | Tests pass; smoke surface named | Local smoke is not public proof |
| Website | `npm test`, `npm run build` | Tests/build pass | Record package/tooling blocker |
| Deployment/ops | `scripts/ops/status.sh`, `scripts/ops/smoke.sh`, rollback docs check | Surface-specific pass | Prod checks require explicit prod intent |

## Recording Evidence

For non-trivial work, record:

- command
- expected result
- observed result
- surface checked
- caveat if skipped or unavailable
- rollback path

Never paste secrets, env files, tokens, session strings, cookies, or auth headers.
