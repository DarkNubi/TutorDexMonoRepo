# PublicApiDown

## Meaning

The public TutorDex API endpoint is failing blackbox health checks. Firebase Hosting may still load, but assignment loading and user actions that require the backend will fail.

Current prod alerting uses the LAN-SNI probe route: blackbox probes `https://192.168.1.42/...` with Host/SNI `tutordex-api.duckdns.org`, and Prometheus relabels the instance as the public DuckDNS URL. This avoids false alerts from router hairpin/NAT loopback failures inside the LAN.

## First Checks

```bash
docker exec tutordex-prod-prometheus-1 wget -q -O- 'http://127.0.0.1:9090/api/v1/query?query=probe_success%7Bjob%3D%22blackbox_http_public%22%2Cprobe_route%3D%22lan_sni%22%7D'
docker exec tutordex-prod-blackbox-exporter-1 wget -q -O- 'http://127.0.0.1:9115/probe?debug=true&module=http_2xx_tutordex_lan_sni&target=https%3A%2F%2F192.168.1.42%2Fhealth'
docker compose -p tutordex-prod --env-file .env.prod ps
ss -ltnp '( sport = :8000 )'
```

For true outside-WAN proof, run these from mobile data, a remote VM, GitHub Actions, or any network outside the LAN:

```bash
curl -i --connect-timeout 5 --max-time 15 https://tutordex-api.duckdns.org/health
curl -i --connect-timeout 5 --max-time 15 https://tutordex-api.duckdns.org/health/dependencies
```

## Common Causes

- The prod backend container is not running.
- Port `8000` is occupied by another process.
- The Supabase runtime is down or missing, so `/health/dependencies` fails.
- DNS, router, firewall, or TLS proxy routing to the host is broken.
- The LAN-SNI probe config, Caddy upstream, or Prometheus relabeling is stale after a config change.

## Recovery

1. Confirm Caddy can reach the backend service alias:

```bash
docker exec tutordex-prod-api-ingress-1 wget -S -O- -T 5 http://backend:8000/health
```

2. Confirm the process bound to port `8000` is the TutorDex prod backend.
3. Confirm the configured Supabase network exists and contains the Supabase Kong/PostgREST/Postgres services.
4. Start or restart only the backend after Supabase is healthy:

```bash
docker compose -p tutordex-prod --env-file .env.prod up -d --build backend
```

5. Re-run LAN-SNI blackbox checks and outside-WAN checks separately before touching workers or broadcast/DM services.
