Traefik setup for local development (TutorDex)

Overview
- Traefik is configured in docker-compose to provide hostname-based routing for local services.
- The Traefik dashboard is bound to localhost:8080 for safety.
 - The Traefik dashboard is bound to 0.0.0.0:8080 in compose; secure it before exposing publicly.
- Services are reachable at hostnames like `backend.tutordex.local`, `grafana.tutordex.local`, etc.

Hosts file (Windows)
Add the following lines to `%windir%\System32\drivers\etc\hosts` (requires admin privileges):

127.0.0.1 backend.tutordex.local
127.0.0.1 grafana.tutordex.local
127.0.0.1 prometheus.tutordex.local
127.0.0.1 alertmanager.tutordex.local
127.0.0.1 sentry.tutordex.local
127.0.0.1 cadvisor.tutordex.local
127.0.0.1 traefik.tutordex.local

Notes
- Traefik is configured with `providers.docker.exposedbydefault=false` so only services with Traefik labels will be routed.
- For local development we use plain HTTP. For production or remote access enable HTTPS/ACME and proper authentication.
- You mentioned planning to add Tailscale later; Traefik configuration will still work behind Tailscale because routing happens inside the Docker host.

Usage
1. Start the stack:

```powershell
# from repo root
docker compose up -d
```

2. Open services in your browser using the hostnames in the hosts file above, e.g. `http://grafana.tutordex.local:8082` (note the port).
3. Traefik dashboard: `http://127.0.0.1:8081` (Traefik HTTP is exposed on host port `8082`, dashboard is served on `8081`).

Note: Because Traefik's HTTP listener is mapped to host port `8082` (not 80), include `:8082` when visiting hostnames like `http://backend.tutordex.local:8082` unless you route DNS via Tailscale or a reverse proxy that routes port 80 to Traefik.

Security
- Do not enable the Traefik dashboard publicly. The compose binds it to localhost only.
- Before exposing any UI to the public, add authentication (Traefik middleware for basic auth) or put Traefik behind a VPN (e.g., Tailscale).
