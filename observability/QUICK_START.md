# Observability Quick Start Guide

**New to TutorDex observability?** Start here for a quick tour.

---

## 🚀 Start the Stack (30 seconds)

```bash
# From the repository root
docker compose up -d --build

# Check everything is healthy
./observability/doctor.sh
```

---

## 🎯 Access Points (Local Development)

| Service | URL | Login | Purpose |
|---------|-----|-------|---------|
| **Grafana** | http://localhost:3300 | admin/admin | Dashboards, alerts, logs |
| **Prometheus** | http://localhost:9090 | None | Metrics and alert rules |
| **Alertmanager** | http://localhost:9093 | None | Alert management |
| **Sentry** | http://localhost:9000 | See setup | Error tracking, performance monitoring |

**Note**: Sentry requires initialization on first start. See `observability/sentry/README.md` for setup.

---

## 📊 What to Look At First

### 1. **Grafana Dashboards** (http://localhost:3300)

Navigate to **Dashboards** → **Browse** to find:

#### Operational Dashboards
- **TutorDex Overview** - Start here! High-level system health
- **TutorDex Infra** - Container resources, host metrics
- **TutorDex LLM + Supabase** - AI and database performance
- **TutorDex Quality** - Parse errors, data quality issues

#### Business Metrics Dashboards ✨ **NEW**
- **TutorDex Business Metrics** - Assignment creation, delivery stats, conversion rates
- **TutorDex Matching & Notifications** - Tutor matching efficiency, DM delivery
- **TutorDex Data Quality & Completeness** - Field completeness, quality trends
- **TutorDex Channel Performance** - Channel comparison, top performers

### 2. **Live Logs** (Grafana → Explore → Loki)

```
# Example queries
{compose_service="collector-tail"}
{compose_service="aggregator-worker", level="error"}
{compose_service="backend"} |= "health"
```

### 3. **Prometheus Alerts** (http://localhost:9090/alerts)

Check which alerts are currently firing (if any).

### 4. **Alertmanager** (http://localhost:9093/#/alerts)

See active alerts and create silences during maintenance.

---

## 🔍 Common Scenarios

### "Is everything running?"

1. Open Grafana → TutorDex Overview dashboard
2. Check the "Service Health" panel at the top
3. Green = good, Red = investigate

### "Why did I get an alert?"

1. Check the Telegram message for the `runbook` link
2. Follow the troubleshooting steps in the runbook
3. Check logs in Grafana filtered by service and time

### "I want to see what the collector is doing"

1. Grafana → Explore → Loki
2. Query: `{compose_service="collector-tail"}`
3. Time range: Last 1 hour
4. Look for `messages_seen`, `messages_upserted` events

### "I want to see LLM performance"

1. Grafana → TutorDex LLM + Supabase dashboard
2. Check "LLM Request Rate" and "LLM Latency" panels
3. Check "LLM Failure Rate" for errors

### "I need to disable an alert temporarily"

**Option A: Silence it** (preferred for temporary muting)
1. Go to http://localhost:9093/#/silences
2. Click "New Silence"
3. Add matcher: `alertname="YourAlert"`
4. Set duration (1h, 1d, 1w)
5. Add comment and click "Create"

**Option B: Disable it permanently**
1. Edit `observability/prometheus/alert_rules.yml`
2. Change `expr:` to `expr: vector(0)`
3. Run `./observability/reload_prometheus.sh`

See [FAQ.md](FAQ.md) for more details.

### "I changed alert rules, why is it still firing?"

Run these two commands:
```bash
# Reload Prometheus configuration
./observability/reload_prometheus.sh

# Clear Alertmanager cache (if still getting notifications)
docker compose restart alertmanager
```

See [FAQ.md](FAQ.md) for detailed explanation.

---

## 📈 Key Metrics to Monitor

### System Health
- `up` - Service availability (1 = up, 0 = down)
- `container_cpu_usage_seconds_total` - Container CPU usage
- `node_filesystem_avail_bytes` - Disk space

### Pipeline Health
- `collector_messages_seen_total` - Messages ingested per channel
- `queue_pending` - Jobs waiting to be processed
- `queue_oldest_pending_age_seconds` - How long jobs are waiting
- `worker_jobs_processed_total` - Jobs completed (by status)

### Performance
- `worker_job_latency_seconds` - End-to-end job processing time
- `worker_llm_call_latency_seconds` - LLM API response time
- `worker_supabase_latency_seconds` - Database query time

### Quality
- `worker_parse_success_total` - Successful extractions
- `worker_parse_failure_total` - Failed extractions (by reason)
- `assignment_quality_missing_field_total` - Missing data issues

---

## 📚 Learn More

- **[CAPABILITIES.md](CAPABILITIES.md)** - Complete capabilities guide (what it does + what it can do)
- **[FAQ.md](FAQ.md)** - Common questions and troubleshooting
- **[CARDINALITY.md](CARDINALITY.md)** - Metrics best practices
- **[runbooks/](runbooks/)** - Alert-specific troubleshooting guides
- **[TODO_OBSERVABILITY.md](../TODO_OBSERVABILITY.md)** - Future enhancements

---

## 🆘 Getting Help

### Something not working?

1. **Check service health**: `./observability/doctor.sh`
2. **Check logs**: `docker compose logs <service-name>`
3. **Check FAQ**: [FAQ.md](FAQ.md)
4. **Check runbooks**: [runbooks/](runbooks/)

### Common Issues

**"Can't access Grafana"**
- Check: `docker compose ps grafana`
- Fix: `docker compose restart grafana`

**"No metrics in dashboards"**
- Check: `docker compose ps prometheus`
- Check: http://localhost:9090/targets (all should be UP)
- Fix: `docker compose restart prometheus`

**"No logs in Loki"**
- Check: `docker compose ps promtail`
- Check: `docker compose logs promtail | tail -20`
- Fix: `docker compose restart promtail`

**"Alerts not sending to Telegram"**
- Check: `docker compose ps alertmanager alertmanager-telegram`
- Check: `docker compose logs alertmanager-telegram | tail -20`
- Verify: Telegram bot token and chat ID are correct in `.env`

**"Sentry not accessible"**
- Check: `docker compose ps sentry sentry-postgres sentry-redis`
- Initialize: See `observability/sentry/README.md` for first-time setup
- Fix: `docker compose restart sentry`

---

## 🎓 Next Steps

1. **Set up Sentry**: See `observability/sentry/README.md` for initialization ✨ **NEW**
2. **Enable tracing**: Set `OTEL_ENABLED=1` in `.env` files for distributed tracing
3. **Customize dashboards**: Edit JSON files or use Grafana UI
4. **Add custom alerts**: Edit `observability/prometheus/alert_rules.yml`
5. **Implement analytics**: See [TODO_OBSERVABILITY.md](../TODO_OBSERVABILITY.md) section "Supabase product analytics"

---

**Ready to dive deeper?** Read [CAPABILITIES.md](CAPABILITIES.md) for the complete guide.
