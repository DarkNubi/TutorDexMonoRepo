# PublicApiDown

## Meaning

The public TutorDex API endpoint is failing blackbox health checks. Firebase Hosting may still load, but assignment loading and user actions that require the backend will fail.

## First Checks

```bash
curl -i --connect-timeout 5 --max-time 15 https://tutordex-api.duckdns.org/health
curl -i --connect-timeout 5 --max-time 15 https://tutordex-api.duckdns.org/health/dependencies
docker compose -p tutordex-prod --env-file .env.prod ps
ss -ltnp '( sport = :8000 )'
```

## Common Causes

- The prod backend container is not running.
- Port `8000` is occupied by another process.
- The Supabase runtime is down or missing, so `/health/dependencies` fails.
- DNS, router, firewall, or TLS proxy routing to the host is broken.

## Recovery

1. Confirm the process bound to port `8000` is the TutorDex prod backend.
2. Confirm the configured Supabase network exists and contains the Supabase Kong/PostgREST/Postgres services.
3. Start or restart only the backend after Supabase is healthy:

```bash
docker compose -p tutordex-prod --env-file .env.prod up -d --build backend
```

4. Re-run public health checks and the repo smoke tests before touching workers or broadcast/DM services.

