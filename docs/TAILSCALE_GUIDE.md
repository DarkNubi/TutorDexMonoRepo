# Tailscale Guide — Complete Setup & Service Exposure

This document contains everything needed for Tailscale installation, first-time setup, service exposure (via `tailscale serve`) and systemd service examples for the TutorDex deployment. Use this as the single source for all Tailscale-related operations in this repo.

## Quick reference — Public Tailscale links

These are the tailnet-accessible URLs used by the project (staging and prod):

- Staging:
	- https://staging-grafana.taildbd593.ts.net
	- https://staging-prometheus.taildbd593.ts.net
	- https://staging-alertmanager.taildbd593.ts.net
	- https://staging-supabase.taildbd593.ts.net
	- https://staging-logflare.taildbd593.ts.net

- Production:
	- https://prod-grafana.taildbd593.ts.net
	- https://prod-prometheus.taildbd593.ts.net
	- https://prod-alertmanager.taildbd593.ts.net
	- https://prod-supabase.taildbd593.ts.net
	- https://prod-logflare.taildbd593.ts.net

> Note: `logflare` in this stack is part of the Supabase observability pipeline. The `tailscale serve` commands below expose the local Logflare HTTP endpoint into the tailscale-managed domain.

---

## Table of contents

- Prerequisites
- Install Tailscale (Linux / Debian & Ubuntu / RedHat / macOS / Windows)
- Start the daemon and authenticate (interactive and headless)
- Verify connectivity
- Using `tailscale serve` to expose services
- Example: expose TutorDex services (staging & prod)
- Running `tailscale serve` under systemd (recommended)
- Useful admin / troubleshooting commands
- Security & notes

---

## Prerequisites

- A Tailscale account and tailnet (admin access to the Tailscale Admin Console).
 - A machine (VM / host) with the service(s) running locally. Use the host-exposed ports (not internal container ports):
	 - Grafana: prod 3300, staging 3301
	 - Prometheus: prod 9090, staging 9091
	 - Alertmanager: prod 9093, staging 9094
	 - Supabase (Kong / HTTP): prod 54321, staging 54322
	 - Backend API: prod 8000, staging 8001
	 - Logflare: prod 4000, staging 4001
- If you need unattended auth (CI, headless), create an auth key in the Tailscale Admin Console: `https://login.tailscale.com/admin/authkeys` and copy a key with the required expiry and capabilities.

---

## Install Tailscale

Linux (Debian/Ubuntu & other distributions):

```
curl -fsSL https://tailscale.com/install.sh | sh
```

RedHat / CentOS (using the same install script above) or follow distro docs.

macOS (Homebrew):

```
brew install --cask tailscale
```

Windows (PowerShell / Winget):

```
# (PowerShell): download from tailscale.com and run the installer
# or
winget install Tailscale.Tailscale
```

Docker: See the official Tailscale documentation for containerized deployments. For most TutorDex hosts we install the native package.

---

## Start daemon and authenticate

After installing, enable and start the Tailscale daemon (Linux/systemd):

```
sudo systemctl enable --now tailscaled
```

Interactive auth (desktop / headless with browser):

```
sudo tailscale up
```

This will produce a URL you must open once in a browser to finish login, or it will automatically open a browser on desktop installs.

Headless / non-interactive (CI, servers) using an auth key you created in the admin console:

```
sudo tailscale up --authkey tskey-XXX-XXXXX --accept-routes
```

Tip: Add `--advertise-exit-node` if you want this machine to act as an exit node for other tailnet clients.

---

## Verify connectivity & node status

```
tailscale status
tailscale ip -4    # get machine tailscale IPs
tailscale netcheck
```

Open the Admin Console (`https://login.tailscale.com/admin/machines`) to verify the node is present and named correctly.

---

## Using `tailscale serve` to expose local HTTP(S) services

`tailscale serve` exposes local HTTP services to the Tailscale-managed domain(s). Basic usage:

```
tailscale serve --service=svc:<service-name> <local-address:port>
```

- `<service-name>` becomes the service label used by the Tailscale routing/serve infrastructure.
- `<local-address:port>` is the local listening address (often `127.0.0.1:<port>`).

Examples for the TutorDex Logflare mappings used in this repo (actual ports from repo/config):

```
tailscale serve --service=svc:staging-logflare 127.0.0.1:4001
tailscale serve --service=svc:prod-logflare 127.0.0.1:4000
```

When these `serve` commands run on the host that is part of the same tailnet, the corresponding `*.taildbd593.ts.net` domains will resolve to the served endpoints (per your tailnet DNS/serve configuration).

You can also expose multiple different backends or path-based routing in a single `tailscale serve` invocation — see official Tailscale serve documentation for advanced routing and TLS termination options.

---

## Example: Systemd wrapper to run `tailscale serve` persistently

The `tailscale serve` command runs in foreground. Create a simple systemd service to run each exposed service as a unit.

1) Example unit template for a service named `tailscale-serve@.service`:

Create `/etc/systemd/system/tailscale-serve@.service` with the following content (requires root):

```
[Unit]
Description=Tailscale serve for %i
After=tailscaled.service

[Service]
Type=simple
ExecStart=/usr/bin/tailscale serve --service=svc:%i 127.0.0.1:%i_PORT
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

Replace `%i_PORT` with the numeric port when instantiating the unit (systemd templating can't do string substitutions like this directly). Simpler approach: use a small wrapper script per service.

2) Wrapper script approach (recommended):

Create `/usr/local/bin/run-tailscale-serve.sh` (root-owned):

```
#!/bin/sh
SERVICE_NAME="$1"
BACKEND_ADDR="$2"
exec /usr/bin/tailscale serve --service=svc:${SERVICE_NAME} ${BACKEND_ADDR}
```

Make it executable:

```
sudo chmod +x /usr/local/bin/run-tailscale-serve.sh
```

3) Example systemd unit for staging Logflare (`/etc/systemd/system/tailscale-serve-staging-logflare.service`):

```
[Unit]
Description=Tailscale serve - staging-logflare
After=tailscaled.service

[Service]
Type=simple
ExecStart=/usr/local/bin/run-tailscale-serve.sh staging-logflare 127.0.0.1:4001
Restart=on-failure
User=root

[Install]
WantedBy=multi-user.target
```

Then enable and start:

```
sudo systemctl daemon-reload
sudo systemctl enable --now tailscale-serve-staging-logflare.service
sudo systemctl status tailscale-serve-staging-logflare.service
```

Repeat for `prod-logflare` with `127.0.0.1:4000`.

---

## Example `tailscale serve` commands for TutorDex (full list)

Run these on the host(s) that run the actual service backends. If you prefer to run via systemd, wrap them with the wrapper script and units above.

Staging (host-exposed ports):

```
tailscale serve --service=svc:staging-grafana 127.0.0.1:3301
tailscale serve --service=svc:staging-prometheus 127.0.0.1:9091
tailscale serve --service=svc:staging-alertmanager 127.0.0.1:9094
tailscale serve --service=svc:staging-supabase 127.0.0.1:54322
tailscale serve --service=svc:staging-logflare 127.0.0.1:4001
```

Production (host-exposed ports):

```
tailscale serve --service=svc:prod-grafana 127.0.0.1:3300
tailscale serve --service=svc:prod-prometheus 127.0.0.1:9090
tailscale serve --service=svc:prod-alertmanager 127.0.0.1:9093
tailscale serve --service=svc:prod-supabase 127.0.0.1:54321
tailscale serve --service=svc:prod-logflare 127.0.0.1:4000
```

Adapt ports to match where each service actually listens on the host (these examples follow the repository's staging/prod host-exposed port mappings).

---

## Useful admin & troubleshooting commands

```
sudo journalctl -u tailscaled -f          # tailscaled daemon logs
sudo journalctl -u tailscale-serve-* -f   # wrapper/service logs if using systemd units
tailscale status                          # list nodes and services
tailscale cert <hostname>                 # if using Tailscale certs (when applicable)
tailscale logout                          # remove local login
tailscale down                            # bring interface down
```

If a served domain doesn't resolve correctly, check the Admin Console for the serve registrations and ensure the host running `tailscale serve` is online and authenticated.

---

## Security & operational notes

- Only run `tailscale serve` for services you intend to expose to the tailnet.
- Use Tailscale ACLs (in the Admin Console) and auth keys with minimal scope for unattended hosts.
- Monitor resource usage and logs (via `journalctl` and the Tailscale Admin Console).
- For production, run `tailscale serve` under systemd with restart policies, and ensure host-level firewalling only allows the intended local bindings.

---

If you want, I can:

- Add ready-to-use systemd unit files for each TutorDex service (I can create them under `observability/` or in `docs/` for copy-paste).
- Create example scripts to generate auth keys via the Tailscale API (requires an API key).

End of guide.
