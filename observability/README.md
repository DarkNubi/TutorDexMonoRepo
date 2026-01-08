# Observability (Prometheus + Grafana + Loki + Alertmanager + Sentry)

This repo runs observability **fully in Docker** via the root `docker-compose.yml`.

---

## 📖 Documentation

- **[QUICK_START.md](QUICK_START.md)** - 🚀 New here? Start with this quick guide
- **[CAPABILITIES.md](CAPABILITIES.md)** - Complete guide: What the observability stack currently does and what else it can do
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System architecture and data flow diagrams
- **[FAQ.md](FAQ.md)** - Answers to common questions about alerts, reloading configuration, and troubleshooting
- **[CARDINALITY.md](CARDINALITY.md)** - Metrics and log cardinality rules for performance
- **[runbooks/](runbooks/)** - Alert-specific troubleshooting guides
- **[sentry/README.md](sentry/README.md)** - Sentry self-hosted setup guide

## Start everything

- `docker compose up -d --build`

## URLs (defaults)

- Grafana: `http://localhost:3300`
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Loki: `http://localhost:3100`
- Tempo (traces backend): `http://localhost:3200`
- **Sentry**: `http://localhost:9000` (requires initialization - see `sentry/README.md`)

## Grafana login

- User: `admin` (override with `GRAFANA_ADMIN_USER`)
- Password: `admin` (override with `GRAFANA_ADMIN_PASSWORD`)

## Sentry login (after initialization)

- Email: `admin@tutordex.local` (or your configured email)
- Password: `admin` (or your configured password)
- **Change credentials after first login!**

## What's wired

- Metrics: services expose `/metrics` internally; Prometheus scrapes them.
- Logs: services emit structured JSON logs to stdout; Promtail ships them to Loki; Grafana queries Loki.
- Alerts: Prometheus evaluates rules; Alertmanager routes alerts to Telegram via `alertmanager-telegram`.
- Traces (optional): Tempo + OTEL collector are running; app tracing is enabled only if you install OTEL SDKs and set `OTEL_ENABLED=1`.
- **Error tracking**: Sentry self-hosted for exception capture, performance monitoring, and profiling. Enable by setting `SENTRY_DSN` after initialization (see `sentry/README.md`).

## Quick sanity check

- `./observability/doctor.sh`

---

## Reloading Alert Rules

After modifying `observability/prometheus/alert_rules.yml`, you need to reload Prometheus configuration:

### Option 1: Use the helper script (recommended)
```bash
./observability/reload_prometheus.sh
```

### Option 2: Manual hot reload (no downtime)
```bash
curl -X POST http://localhost:9090/-/reload
```

### Option 3: Restart Prometheus container
```bash
docker compose restart prometheus
```

### Option 4: Full rebuild (if you changed Dockerfile or want to update all services)
```bash
docker compose up -d --build
```

**Note**: The alert rules file is mounted as a read-only volume, so changes to the file on disk are immediately visible to Prometheus after reload. No rebuild is necessary.

## Troubleshooting Alerts

### Still receiving alerts after disabling them?

If you've disabled an alert (e.g., by setting `expr: vector(0)`) but still receive notifications:

1. **Reload Prometheus configuration** (see above)
2. **Check if Prometheus picked up the change**:
   ```bash
   # Visit Prometheus UI
   open http://localhost:9090/rules
   # Look for your alert and verify the expression shows vector(0)
   ```
3. **Clear cached alerts in Alertmanager**:
   - Alertmanager has a `repeat_interval` (default 4-24h depending on severity)
   - Already-firing alerts may continue sending notifications until they resolve
   - To force-clear: restart Alertmanager (loses alert state):
     ```bash
     docker compose restart alertmanager
     ```
4. **Verify the alert has resolved**:
   ```bash
   # Visit Alertmanager UI
   open http://localhost:9093/#/alerts
   # Check if the alert still shows as "active"
   ```

### Alert configuration precedence

1. `observability/prometheus/alert_rules.yml` - Alert definitions
2. `observability/prometheus/prometheus.yml` - Scrape configs and rule file references
3. `observability/alertmanager/alertmanager.yml` - Routing and notification settings

Changes to alert definitions require Prometheus reload. Changes to alerting routing require Alertmanager reload.

