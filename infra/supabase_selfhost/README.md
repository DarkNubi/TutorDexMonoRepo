# Supabase Self-Hosted Migration (TutorDex)

This folder contains an opinionated runbook + helper scripts to migrate TutorDex from Supabase Cloud to self-hosted Supabase on a Windows home server.

TutorDex components that will be affected:
- Aggregator: uses `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (server-side writes)
- Backend: uses `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (server-side writes)
- Website: uses `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` (client-side reads)

Important:
- If your website is public, your Supabase API endpoint will also be public. Lock it down with RLS.
- Never put the service role key in the website. Keep it server-side only.

## Files

- `infra/supabase_selfhost/Caddyfile.example`: reverse proxy template (TLS + domains)
- `infra/supabase_selfhost/docker-compose.override.yml.example`: optional hardening to bind Supabase ports to localhost
- `infra/supabase_selfhost/generate_supabase_keys.ps1`: generates `ANON_KEY` and `SERVICE_ROLE_KEY` for a given `JWT_SECRET`
- `infra/supabase_selfhost/duckdns_update.ps1`: updates DuckDNS domains to your current public IP
- `infra/supabase_selfhost/install_duckdns_task.ps1`: installs a scheduled task to run the updater every N minutes
- `infra/supabase_selfhost/apply_tutordex_schema.ps1`: applies TutorDex schema + migrations into the self-hosted DB
- `infra/supabase_selfhost/migrate_cloud_public_schema.ps1`: dumps Supabase Cloud `public` data and restores into self-hosted DB
- `infra/supabase_selfhost/backup_selfhost_public_schema.ps1`: dumps self-hosted `public` schema for backups

## Step-by-step runbook (exact commands) - DuckDNS (no custom domain)

### 0) Prereqs (public website)

Create DuckDNS domains (recommended):
- `tutordex-api.duckdns.org`: Kong API gateway (what the website uses as `VITE_SUPABASE_URL`)
- Optional (not recommended to expose publicly): `tutordex-studio.duckdns.org` for Studio

DuckDNS setup:
1) Create an account at https://www.duckdns.org/
2) Add the domain(s) you want (e.g. `tutordex-api`, optionally `tutordex-studio`)
3) Copy your DuckDNS **token** (you’ll use it for the updater script below)

Open ports on your home server/router/firewall:
- TCP `80` and `443` (for TLS via your reverse proxy)

Install (on the Windows home server):
- Git
- Docker Desktop (Linux containers, WSL2 enabled)
- Caddy (recommended reverse proxy for easy TLS)

### 0a) Install a DuckDNS updater (keeps the DNS pointed to your home IP)

Create `D:\TutorDex\infra\supabase_selfhost\.env` (do not commit) with:

```text
DUCKDNS_DOMAINS=tutordex-api,tutordex-studio
DUCKDNS_TOKEN=REPLACE_WITH_YOUR_DUCKDNS_TOKEN
```

Run the updater once (from repo root):

```powershell
cd D:\TutorDex
.\infra\supabase_selfhost\duckdns_update.ps1 -EnvFile .\infra\supabase_selfhost\.env
```

Install a Task Scheduler job to update every 5 minutes:

```powershell
cd D:\TutorDex
powershell -ExecutionPolicy Bypass -File .\infra\supabase_selfhost\install_duckdns_task.ps1 -EnvFile .\infra\supabase_selfhost\.env
```

### 1) Set up the Supabase self-host stack (official compose)

Pick a folder for the Supabase stack (example: `C:\supabase-selfhost`):

```powershell
mkdir C:\supabase-selfhost
cd C:\supabase-selfhost
git clone --depth 1 https://github.com/supabase/supabase.git
cd .\supabase\docker
Copy-Item .\.env.example .\.env
```

#### 1a) Generate secrets + keys (required)

Choose a strong JWT secret (32+ chars). Example generator:

```powershell
$JWT_SECRET = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
```

Generate Supabase keys from that secret (run from your TutorDex repo root):

```powershell
cd D:\TutorDex
.\infra\supabase_selfhost\generate_supabase_keys.ps1 -JwtSecret $JWT_SECRET
```

Copy the printed `ANON_KEY=...` and `SERVICE_ROLE_KEY=...` into `C:\supabase-selfhost\supabase\docker\.env`.

Now edit `C:\supabase-selfhost\supabase\docker\.env` and set at least:
- `POSTGRES_PASSWORD` (strong)
- `JWT_SECRET` (the `$JWT_SECRET` you generated)
- `ANON_KEY` (generated)
- `SERVICE_ROLE_KEY` (generated)
- `DASHBOARD_PASSWORD` (strong; Studio login)
- `SITE_URL` = your website URL (Firebase Hosting URL or your existing public site URL)
- `API_EXTERNAL_URL` = `https://tutordex-api.duckdns.org`
- `SUPABASE_PUBLIC_URL` = `https://tutordex-api.duckdns.org`

Port note (common conflict):
- Supabase publishes Kong on `KONG_HTTP_PORT` (defaults to `8000`).
- TutorDexBackend commonly uses port `8000` too.
- If `8000` is already taken, change in `C:\supabase-selfhost\supabase\docker\.env`:
  - `KONG_HTTP_PORT=8001`
  - `KONG_HTTPS_PORT=8444`
  - Then proxy Caddy to `127.0.0.1:8001` (see `infra/supabase_selfhost/Caddyfile.example`).

#### 1b) Optional hardening: bind ports to localhost

This keeps Studio private (localhost-only):

```powershell
cd C:\supabase-selfhost\supabase\docker
Copy-Item D:\TutorDex\infra\supabase_selfhost\docker-compose.override.yml.example .\docker-compose.override.yml
```

Important:
- This override only binds Studio to `127.0.0.1:3000`.
- Do not try to bind Kong (Supabase API) to localhost via compose override on Windows; Docker Compose merges port lists and you can get duplicate bindings and `address already in use`.
- To keep Kong “effectively private”, expose only `80/443` (reverse proxy) and block `KONG_HTTP_PORT`/`KONG_HTTPS_PORT` inbound in Windows Firewall.

#### 1c) Start Supabase

```powershell
cd C:\supabase-selfhost\supabase\docker
docker compose pull
docker compose up -d
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

### 2) Put a TLS reverse proxy in front (Caddy)

Install Caddy (Chocolatey):

```powershell
choco install caddy -y
```

Create a Caddyfile:

```powershell
notepad C:\caddy\Caddyfile
```

Use `infra/supabase_selfhost/Caddyfile.example` as the starting point. If you didn’t create the Studio DuckDNS domain, remove the Studio block.

Run Caddy (test mode):

```powershell
caddy run --config C:\caddy\Caddyfile
```

Verify from another machine:
- `https://tutordex-api.duckdns.org/rest/v1/` returns `404`/`401` (either is fine; it proves routing works)

### 3) Apply TutorDex schema + migrations into the self-host DB

From the TutorDex repo root on the server:

```powershell
cd D:\TutorDex
.\infra\supabase_selfhost\apply_tutordex_schema.ps1
```

Then apply RLS policy templates (recommended for a public website):

```powershell
Get-Content -Raw .\TutorDexAggregator\supabase_rls_policies.sql | docker exec -i supabase-db psql -U postgres -d postgres -v ON_ERROR_STOP=1
```

### 4) Migrate ALL TutorDex data from Supabase Cloud (including raw history)

1) Stop writers first (Aggregator + Backend) so you don’t miss rows during the dump.

2) Set the Supabase Cloud DB URL in an env var (PowerShell):

```powershell
$env:TDX_CLOUD_DATABASE_URL = "postgresql://postgres:<PASSWORD>@db.<project-ref>.supabase.co:5432/postgres?sslmode=require"
```

3) Run the migration script (dumps cloud `public` data-only, then restores into self-host):

```powershell
cd D:\TutorDex
.\infra\supabase_selfhost\migrate_cloud_public_schema.ps1 -Jobs 4
```

Notes:
- The dump is saved to `infra/supabase_selfhost/backups/tutordex_public_data.dump` by default, so you don’t need to re-dump if restore fails.
- Split dump/restore:
  - Dump only: `.\infra\supabase_selfhost\migrate_cloud_public_schema.ps1 -DumpOnly`
  - Restore only (reuses existing dump): `.\infra\supabase_selfhost\migrate_cloud_public_schema.ps1 -RestoreOnly`
- If you already attempted a restore, rerun with `-TruncatePublicFirst` to clear partially imported rows.

Troubleshooting:
- If `pg_dump` fails with a version mismatch (e.g. `server version: 17.x; pg_dump version: 16.x`), update the script to use `postgres:17` (this repo’s script already does).
- If `pg_restore` fails with `unsupported version (1.16) in file header`, it’s because the restore is running with an older Postgres client. This repo’s script restores using `postgres:17` tools over the docker network, and reads `POSTGRES_PASSWORD` from `C:\supabase-selfhost\supabase\docker\.env`.
- If `pg_dump` resolves an IPv6 address and fails with `Network is unreachable`, rerun with:
  - Best: use Supabase Cloud pooler (IPv4): `.\infra\supabase_selfhost\migrate_cloud_public_schema.ps1 -Jobs 4 -DnsServer 1.1.1.1 -UsePooler -PoolerRegion ap-south-1`
    - If you still get `Tenant or user not found`, try `-PoolerAwsIndex 1` (some projects use `aws-1-...pooler.supabase.com`).
  - Alternative (only if the DB host has an A record): `.\infra\supabase_selfhost\migrate_cloud_public_schema.ps1 -Jobs 4 -DnsServer 1.1.1.1 -ForceIPv4`
- If `supabase-pooler` (Supavisor) keeps restarting with a `SyntaxError ... carriage return (U+000D)`, your `volumes/pooler/pooler.exs` file has Windows CRLF line endings. Convert it to LF and restart the container:
  - `$p="C:\supabase-selfhost\supabase\docker\volumes\pooler\pooler.exs"; $t=Get-Content -Raw $p; [IO.File]::WriteAllText($p, ($t -replace \"`r`n\",\"`n\"), (New-Object System.Text.UTF8Encoding($false)))`
  - `cd C:\supabase-selfhost\supabase\docker; docker restart supabase-pooler`

### 5) Cut over the app configs to the self-hosted instance

Update these files (do not commit secrets):

- `TutorDexAggregator/.env`
  - `SUPABASE_URL=https://supabase-api.<your-domain>`
  - `SUPABASE_SERVICE_ROLE_KEY=<SERVICE_ROLE_KEY>`
  - `SUPABASE_ENABLED=true`
  - `SUPABASE_RAW_ENABLED=true` (since you’re migrating raw into DB)

- `TutorDexBackend/.env`
  - `SUPABASE_URL=https://supabase-api.<your-domain>`
  - `SUPABASE_SERVICE_ROLE_KEY=<SERVICE_ROLE_KEY>`
  - `SUPABASE_ENABLED=true`

- `TutorDexWebsite/.env` (build-time)
  - `VITE_SUPABASE_URL=https://tutordex-api.duckdns.org`
  - `VITE_SUPABASE_ANON_KEY=<ANON_KEY>`

Rebuild + redeploy the website (Firebase Hosting):

```powershell
cd D:\TutorDex\TutorDexWebsite
npm ci
npm run build
firebase deploy --only hosting
```

Restart your backend/aggregator services (Task Scheduler / docker compose / whatever you use).

### 6) Sanity checks

From any machine:

```powershell
curl "https://supabase-api.<your-domain>/rest/v1/assignments?select=id&limit=1" -H "apikey: <ANON_KEY>" -H "authorization: Bearer <ANON_KEY>"
```

Confirm:
- Website loads assignments.
- Aggregator can upsert.
- Backend `/health/full` shows supabase ok (or skipped if you keep it optional).

### 7) Backups (strongly recommended)

Quick manual backup of the self-host `public` schema (writes to `infra/supabase_selfhost/backups/`):

```powershell
cd D:\TutorDex
.\infra\supabase_selfhost\backup_selfhost_public_schema.ps1
```
