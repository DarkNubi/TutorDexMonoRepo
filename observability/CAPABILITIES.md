# TutorDex Observability Stack: Current Capabilities & Future Enhancements

This document provides a comprehensive overview of what your observability stack currently does and what additional capabilities are available or can be enabled.

---

## What Your Observability Stack Currently Does

### 1. **Metrics Collection & Storage (Prometheus)**

Your stack collects **50+ custom metrics** from three main components:

#### Collector Metrics
- **Message ingestion tracking**: Messages seen, upserted, errors by channel
- **Pipeline health**: Last message timestamp per channel (detects stalls)
- **Version tracking**: Pipeline and schema versions

#### Worker/Extraction Metrics
- **Queue health**: Pending, processing, failed, and completed job counts
- **Queue age**: Oldest pending/processing job age (detects stuck jobs)
- **Job processing**: Total jobs processed, success/failure rates
- **Job latency**: End-to-end and per-stage latency histograms
- **LLM performance**: Request counts, failure rates, latency (by model)
- **Database performance**: Supabase operation counts, failure rates, latency (by operation)
- **Parse quality**: Success/failure rates by reason, missing field tracking
- **Assignment quality**: Missing subjects, inconsistencies

#### Backend Metrics
- **HTTP performance**: Request counts, latency by method/path/status
- **API health**: Response times and error rates

#### Infrastructure Metrics
- **Container health**: cAdvisor metrics for all Docker containers
- **Host metrics**: Node Exporter metrics (CPU, memory, disk, network)
- **Service availability**: Blackbox probes for health endpoints

### 2. **Pre-Computed Metrics (Recording Rules)**

Your stack computes **9 aggregated metrics** every 30 seconds for fast querying:

- `tutordex:collector:seconds_since_last_message` - Quick staleness check
- `tutordex:worker:throughput_jobs_per_s` - Worker throughput
- `tutordex:worker:llm_fail_rate_per_s` - LLM failure rate
- `tutordex:worker:supabase_fail_rate_per_s` - Database failure rate
- `tutordex:worker:parse_failure_rate_per_s` - Parse failure rate by reason
- `tutordex:worker:parse_success_rate_per_s` - Parse success rate
- `tutordex:worker:parse_error_fraction` - Parse error percentage
- `tutordex:quality:missing_field_rate_per_s` - Quality issues by field
- `tutordex:quality:inconsistency_rate_per_s` - Quality issues by kind

### 3. **Automated Alerting (17 Active Alerts)**

Your stack monitors critical conditions and sends **Telegram notifications** via Alertmanager:

#### Infrastructure Alerts (4)
- **PrometheusTargetDown**: Any scrape target is down for 5+ minutes
- **BlackboxProbeFailed**: Health probe fails for 2+ minutes
- **HostDiskLow**: Disk usage > 90% for 15+ minutes
- **ContainerRestarted**: Any key service restarts (immediate)

#### Deadman Alert (1)
- **Watchdog**: Always-firing test alert (validates alerting pipeline every 24h)

#### Pipeline Alerts (9)
- **CollectorStalled**: No messages for 10+ minutes (currently disabled)
- **QueueBacklogGrowingNoThroughput**: Queue growing with zero worker throughput (critical)
- **QueueOldestPendingTooOld**: Jobs waiting 30+ minutes (warning)
- **QueueStuckProcessing**: Jobs processing for 15+ minutes (critical)
- **LLMFailureSpike**: LLM failure rate > 0.2/s for 5+ minutes
- **SupabaseFailureSpike**: Database failure rate > 0.2/s for 5+ minutes
- **BroadcastFailureSpike**: Broadcast failure rate > 0.2/s for 5+ minutes
- **DMFailureSpike**: DM failure rate > 0.2/s for 5+ minutes
- **DMRateLimited**: Telegram rate limits detected for 2+ minutes

#### Quality Alerts (3)
- **ParseFailureSpike**: Parse failures > 0.5/s for 5+ minutes
- **ParseErrorFractionHigh**: Parse error rate > 20% for 10+ minutes
- **MissingSubjectsHigh**: Missing subjects > 0.2/s for 15+ minutes

**Alert Routing**:
- **Critical alerts**: Repeat every 30 minutes
- **Warning alerts**: Repeat every 6 hours
- **Watchdog**: Repeats every 24 hours

### 4. **Log Aggregation & Search (Loki + Promtail)**

Your stack collects **structured JSON logs** from all services:

- **Automatic collection**: Promtail scrapes Docker container logs
- **Structured parsing**: Extracts JSON fields (timestamp, level, message, context)
- **Label-based filtering**: Query by `compose_service`, `component`, `channel`, `pipeline_version`
- **Low-cardinality design**: High-cardinality IDs (assignment_id, message_id) stored as queryable fields, not labels
- **Time-series correlation**: Link logs to metrics via Grafana

### 5. **Visual Dashboards (4 Grafana Dashboards)**

Your stack provides **pre-built operational dashboards**:

1. **TutorDex Overview** (`tutordex_overview.json`)
   - High-level system health
   - Message ingestion rates
   - Queue status and throughput
   - Component uptime

2. **TutorDex Infra** (`tutordex_infra.json`)
   - Container resource usage
   - Host metrics (CPU, memory, disk)
   - Network traffic
   - Service availability

3. **TutorDex LLM + Supabase** (`tutordex_llm_supabase.json`)
   - LLM request rates and latencies
   - LLM failure rates
   - Supabase operation metrics
   - Database latency distribution

4. **TutorDex Quality** (`tutordex_quality.json`)
   - Parse success/failure rates
   - Parse failure reasons
   - Missing field tracking
   - Assignment quality issues

**Dashboard Features**:
- Time-range selection
- Variable filters (pipeline_version, channel)
- Log panel integration
- Metric drill-down

### 6. **Distributed Tracing (Tempo + OpenTelemetry)**

Your stack has **optional tracing infrastructure** ready to use:

- **Tempo**: Trace storage backend running
- **OTEL Collector**: Receives traces via OTLP (gRPC/HTTP)
- **Application hooks**: `otel.py` modules in Aggregator and Backend
- **Currently disabled by default**: Enable with `OTEL_ENABLED=1`

### 7. **Service Health Endpoints**

Your services expose **health check endpoints**:

- Collector: `http://collector-tail:9001/health/collector`
- Worker: `http://aggregator-worker:9002/health/worker`
- Backend: `http://backend:8000/health/backend`
- Backend dependencies: `http://backend:8000/health/dependencies`

These are probed every 15 seconds by Blackbox Exporter.

### 8. **Operational Runbooks (20 Documents)**

Your stack includes **comprehensive troubleshooting guides**:

- Alert-specific runbooks (referenced in alert annotations)
- General triage procedures
- Alert management guide (DisablingAlerts.md)
- FAQ for common questions

### 9. **Configuration Management**

Your stack provides **easy configuration updates**:

- **Hot reload**: `./observability/reload_prometheus.sh` reloads config without downtime
- **Volume-mounted configs**: Changes take effect immediately
- **Health checker**: `./observability/doctor.sh` validates stack health

---

## What Else Your Observability Stack Can Do

### 1. **Enable Distributed Tracing (Currently Available)**

**What it does**: Track requests across multiple services, visualize call chains, identify bottlenecks.

**How to enable**:
```bash
# In TutorDexAggregator/.env and TutorDexBackend/.env
OTEL_ENABLED=1
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4318
```

**What you get**:
- End-to-end request tracing (website → backend → worker → LLM → Supabase)
- Latency breakdown by service and operation
- Error attribution (which service/call failed)
- Trace visualization in Grafana (Tempo datasource)

**Use cases**:
- Debug slow assignment processing
- Find bottlenecks in extraction pipeline
- Correlate errors across services
- Performance optimization

### 2. **Custom Dashboards**

**What you can add**:
- **User engagement metrics**: Tutor signup rates, preference updates, notification click-through
- **Business metrics**: Assignments per day, tutors matched per assignment, fill rates
- **Cost tracking**: LLM API usage, token consumption, Telegram API calls
- **SLO dashboards**: Service Level Objectives (e.g., 99% uptime, p95 latency < 2s)

**How to add**:
- Edit JSON dashboards in `observability/grafana/dashboards/`
- Use Grafana UI to create, then export JSON
- Dashboards auto-load on Grafana startup

### 3. **Advanced Alerting**

**What you can add**:

#### Custom Alerts
Add to `observability/prometheus/alert_rules.yml`:
```yaml
- alert: LowTutorMatchRate
  expr: sum(rate(tutors_matched_total[1h])) / sum(rate(assignments_created_total[1h])) < 0.5
  for: 30m
  labels:
    severity: warning
  annotations:
    summary: "Low match rate: <50% of assignments finding tutors"
```

#### Alert Silences
- Temporary muting during maintenance
- Scheduled silences for known issues
- Managed via Alertmanager UI: `http://localhost:9093/#/silences`

#### Multiple Alert Channels
Add to `observability/alertmanager/alertmanager.yml`:
```yaml
receivers:
  - name: email-ops
    email_configs:
      - to: ops@tutordex.com
  - name: pagerduty-critical
    pagerduty_configs:
      - service_key: YOUR_KEY
```

### 4. **Log-Based Alerts**

**What it does**: Alert on log patterns (not currently configured).

**How to add**: Use Grafana Loki ruler or Promtail + Prometheus exporter:
- Alert on specific error messages
- Alert on error rate spikes
- Alert on anomalous log patterns

**Example use cases**:
- Alert when "FATAL" appears in logs
- Alert when error log volume spikes 5x
- Alert on specific exception types

### 5. **Anomaly Detection**

**What you can add**:
- **Prometheus recording rules** for historical baselines
- **Grafana ML**: Detect anomalies in metrics (requires Grafana Enterprise or Cloud)
- **Custom algorithms**: Export metrics, analyze externally, post results back

**Use cases**:
- Detect unusual assignment volume
- Identify abnormal LLM latency
- Spot unexpected parser behavior changes

### 6. **Long-Term Metrics Storage**

**Current limitation**: Prometheus retention (default 15 days).

**How to extend**:
- **Thanos**: Multi-cluster Prometheus with object storage (S3, GCS)
- **Cortex**: Long-term storage and multi-tenancy
- **VictoriaMetrics**: High-performance replacement with better retention

**Benefits**:
- Historical analysis (months/years of data)
- Capacity planning
- Trend analysis

### 7. **Synthetic Monitoring**

**Current capability**: Basic HTTP health checks via Blackbox Exporter.

**What you can add**:
- **Complex probes**: Multi-step flows, authenticated requests
- **User journey simulation**: Full assignment browsing flow
- **Geographic probes**: Test from multiple locations
- **SSL certificate monitoring**: Alert before expiration

**How to add**:
Add to `observability/blackbox/blackbox.yml`:
```yaml
modules:
  http_auth:
    prober: http
    http:
      method: POST
      headers:
        Authorization: Bearer TOKEN
      fail_if_not_matches_regexp:
        - "success"
```

### 8. **Error Tracking (Mentioned in TODO_OBSERVABILITY.md)**

**Not currently integrated**: Sentry for exception tracking.

**What it provides**:
- Automatic exception capture
- Stack traces with context
- Error grouping and deduplication
- Release tracking and regression detection
- User impact analysis
- Performance monitoring

**How to add**:
```python
# In TutorDexBackend/app.py
import sentry_sdk
sentry_sdk.init(
    dsn="YOUR_DSN",
    environment="production",
    traces_sample_rate=0.1,
)
```

### 9. **User Analytics (Mentioned in TODO_OBSERVABILITY.md)**

**Partially implemented**: `analytics_events` table exists but event emission is minimal.

**What you can track**:
- User journey events (login, preferences_update, assignment_view)
- Assignment interactions (save, hide, apply_click)
- Conversion funnels (view → apply → hired)
- Engagement metrics (WAU, retention, feature usage)

**Current status**:
- Schema defined in TODO_OBSERVABILITY.md
- Table exists in Supabase
- Event emission not yet implemented in website/backend

**What it enables**:
- Product analytics dashboards
- A/B testing analysis
- User behavior insights
- Churn prediction

### 10. **Performance Profiling**

**What you can add**:
- **Continuous profiling**: Pyroscope for CPU/memory profiles
- **Request tracing**: Already available via OpenTelemetry (just enable it)
- **Database query analysis**: Supabase query performance logs

**Use cases**:
- Find memory leaks
- Identify hot code paths
- Optimize slow queries
- Reduce resource usage

### 11. **Capacity Planning**

**What you can add**:
- **Resource forecasting**: Predict when to scale based on trends
- **Load testing metrics**: Track performance under synthetic load
- **Cost projections**: Estimate infrastructure costs based on growth

**How to implement**:
- Export Prometheus data to analysis tools (Jupyter, pandas)
- Create Grafana dashboards with growth trend lines
- Set alerts for capacity thresholds (e.g., 80% CPU sustained)

### 12. **Compliance & Audit Logging**

**What you can add**:
- **Audit trail**: Log all administrative actions
- **Access logs**: Track who accessed what data
- **Retention policies**: Automated log archival and deletion
- **Compliance reports**: PII access, data modifications

---

## Recommended Next Steps

Based on your current setup and TODO_OBSERVABILITY.md:

### High Priority (Do Soon)
1. **Enable distributed tracing** (`OTEL_ENABLED=1`) for better debugging
2. **Implement user analytics events** in the website (assignment_view, apply_click)
3. **Add Sentry** for better exception tracking and release monitoring
4. **Create business metric dashboards** (assignments/day, match rates, tutor engagement)

### Medium Priority (Do This Quarter)
5. **Add custom alerts** for business metrics (low match rate, high no-reply rate)
6. **Extend Blackbox monitoring** to include multi-step user journeys
7. **Set up alert silences** for planned maintenance windows
8. **Add long-term storage** (Thanos or VictoriaMetrics) for historical analysis

### Low Priority (Future)
9. **Add anomaly detection** for unusual patterns
10. **Implement continuous profiling** for performance optimization
11. **Add geographic probes** for multi-region monitoring
12. **Create capacity planning dashboards** for infrastructure scaling

---

## Quick Reference: Accessing Services

| Service | URL | Purpose |
|---------|-----|---------|
| Grafana | http://localhost:3300 | Dashboards and visualization |
| Prometheus | http://localhost:9090 | Metrics storage and querying |
| Alertmanager | http://localhost:9093 | Alert management and silencing |
| Loki | http://localhost:3100 | Log aggregation (backend API) |
| Tempo | http://localhost:3200 | Trace storage (backend API) |

**Grafana login**: admin/admin (change in production!)

---

## Questions?

- **FAQ**: See `observability/FAQ.md`
- **Troubleshooting**: See `observability/runbooks/`
- **Health check**: Run `./observability/doctor.sh`
- **Reload config**: Run `./observability/reload_prometheus.sh`

---

## Summary

**Your observability stack is production-ready and comprehensive:**
- ✅ Full metrics collection (50+ metrics)
- ✅ Automated alerting (17 alerts with Telegram notifications)
- ✅ Log aggregation (structured JSON logs)
- ✅ Visual dashboards (4 pre-built dashboards)
- ✅ Health monitoring (service probes)
- ✅ Operational runbooks (20 documents)

**Ready to enable (just flip a switch):**
- 🎯 Distributed tracing (set OTEL_ENABLED=1)
- 🎯 Custom dashboards (edit JSON or use UI)
- 🎯 Additional alert channels (email, PagerDuty, Slack)

**Recommended additions (requires integration work):**
- 📈 User analytics event tracking
- 🐛 Sentry error tracking
- 📊 Business metric dashboards
- 🔮 Anomaly detection
- 💾 Long-term metrics storage

Your current stack provides **excellent visibility** into system health, performance, and quality. The infrastructure is solid and extensible—you can add new capabilities incrementally as needs arise.
