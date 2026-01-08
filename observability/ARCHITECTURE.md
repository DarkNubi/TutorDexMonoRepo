# Observability Stack Architecture

This document provides a visual overview of how the TutorDex observability stack is structured.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          TutorDex Services                               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  Collector   │  │    Worker    │  │   Backend    │                  │
│  │  (Port 9001) │  │  (Port 9002) │  │  (Port 8000) │                  │
│  │              │  │              │  │              │                  │
│  │  /metrics    │  │  /metrics    │  │  /metrics    │                  │
│  │  /health     │  │  /health     │  │  /health     │                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         │                 │                 │                           │
│         └─────────────────┴─────────────────┘                           │
│                           │                                              │
│                    JSON Logs (stdout)                                    │
│                           │                                              │
└───────────────────────────┼──────────────────────────────────────────────┘
                            │
                            ▼
      ┌─────────────────────────────────────────────────┐
      │              Observability Stack                 │
      └─────────────────────────────────────────────────┘

┌────────────────────────┐      ┌────────────────────────┐
│     Prometheus         │      │       Promtail         │
│     (Port 9090)        │      │                        │
│                        │      │  ┌──────────────────┐  │
│  Metrics Collection:   │      │  │ Docker Log       │  │
│  • Scrapes /metrics    │      │  │ Collection       │  │
│  • Every 15 seconds    │      │  └────────┬─────────┘  │
│  • 50+ custom metrics  │      │           │            │
│  • Recording rules     │      │    Parse JSON logs     │
│  • Alert evaluation    │      │           │            │
│                        │      │           ▼            │
│  Jobs:                 │      │  ┌──────────────────┐  │
│  • tutordex_collector  │      │  │ Extract labels   │  │
│  • tutordex_worker     │      │  │ & fields         │  │
│  • tutordex_backend    │      │  └────────┬─────────┘  │
│  • cadvisor            │      └───────────┼────────────┘
│  • node_exporter       │                  │
│  • blackbox_http       │                  │
└───────────┬────────────┘                  │
            │                               │
            │ Alert Rules                   │ Structured Logs
            ▼                               ▼
┌────────────────────────┐      ┌────────────────────────┐
│    Alertmanager        │      │         Loki           │
│    (Port 9093)         │      │      (Port 3100)       │
│                        │      │                        │
│  Alert Routing:        │      │  Log Storage:          │
│  • Group by labels     │      │  • Time-series logs    │
│  • Route by severity   │      │  • Label-based index   │
│  • Deduplicate alerts  │      │  • Full-text search    │
│  • Repeat intervals    │      │  • Retention policy    │
│                        │      │                        │
│  Routes:               │      │  Labels:               │
│  • Critical: 30m       │      │  • compose_service     │
│  • Warning: 6h         │      │  • component           │
│  • Watchdog: 24h       │      │  • pipeline_version    │
└───────────┬────────────┘      └────────────────────────┘
            │
            │ Webhook
            ▼
┌────────────────────────┐
│ alertmanager-telegram  │
│    (Port 8080)         │
│                        │
│  Telegram Integration: │
│  • Receives webhooks   │
│  • Formats messages    │
│  • Sends to chat       │
│  • Resolved alerts     │
└────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                         Grafana                              │
│                       (Port 3300)                            │
│                                                              │
│  Datasources:                  Dashboards:                  │
│  ┌──────────────┐              ┌──────────────────────┐     │
│  │ Prometheus   │              │ TutorDex Overview    │     │
│  │ (metrics)    │───────────▶  │ TutorDex Infra       │     │
│  └──────────────┘              │ TutorDex LLM+Supabase│     │
│  ┌──────────────┐              │ TutorDex Quality     │     │
│  │ Loki         │              └──────────────────────┘     │
│  │ (logs)       │───────────▶  Alert Management             │
│  └──────────────┘              Log Exploration              │
│  ┌──────────────┐              Trace Visualization          │
│  │ Tempo        │                                            │
│  │ (traces)     │                                            │
│  └──────────────┘                                            │
└─────────────────────────────────────────────────────────────┘

┌────────────────────────┐      ┌────────────────────────┐
│    OTEL Collector      │      │        Tempo           │
│    (Port 4318/4317)    │      │      (Port 3200)       │
│                        │      │                        │
│  Receives traces:      │      │  Trace Storage:        │
│  • OTLP/HTTP          │──────▶│  • Distributed traces  │
│  • OTLP/gRPC          │      │  • Span storage        │
│  • Batch processing    │      │  • Trace search        │
│                        │      │  • Retention policy    │
│  Status: READY         │      │                        │
│  Enable: OTEL_ENABLED=1│      │  Status: READY         │
└────────────────────────┘      └────────────────────────┘

┌────────────────────────┐      ┌────────────────────────┐
│   Blackbox Exporter    │      │     cAdvisor           │
│    (Port 9115)         │      │    (Port 8080)         │
│                        │      │                        │
│  Health Probes:        │      │  Container Metrics:    │
│  • HTTP checks         │      │  • CPU usage           │
│  • Collector health    │      │  • Memory usage        │
│  • Worker health       │      │  • Network I/O         │
│  • Backend health      │      │  • Disk I/O            │
│  • Dependencies        │      │  • Container stats     │
└────────────────────────┘      └────────────────────────┘

┌────────────────────────┐
│    Node Exporter       │
│    (Port 9100)         │
│                        │
│  Host Metrics:         │
│  • CPU usage           │
│  • Memory usage        │
│  • Disk usage          │
│  • Network traffic     │
│  • System load         │
└────────────────────────┘
```

---

## Data Flow

### Metrics Pipeline
```
Service → /metrics endpoint → Prometheus (scrape) → Recording Rules → 
  → Alert Rules → Alertmanager → Telegram
  → Grafana Dashboards
```

### Logs Pipeline
```
Service → stdout (JSON logs) → Docker → Promtail (collect) → 
  → Loki (index & store) → Grafana (query & visualize)
```

### Traces Pipeline (Optional)
```
Service → OpenTelemetry SDK → OTEL Collector (OTLP) → 
  → Tempo (store) → Grafana (query & visualize)
```

### Alerts Pipeline
```
Prometheus (evaluate rules) → Alertmanager (route & group) → 
  → alertmanager-telegram (format) → Telegram API → Your phone
```

---

## Alert Flow Example

```
1. Prometheus detects: queue_pending increasing + throughput = 0

2. Alert fires: QueueBacklogGrowingNoThroughput
   ├─ Severity: critical
   ├─ For: 10 minutes
   └─ Labels: component=queue, pipeline_version=X

3. Alertmanager receives alert
   ├─ Groups by: alertname, component, pipeline_version
   ├─ Routes to: telegram-critical receiver
   └─ Waits: 5 seconds (group_wait)

4. alertmanager-telegram formats message
   ├─ Summary: "Queue backlog growing with zero throughput"
   ├─ Description: "pending increased over 15m and worker throughput is 0"
   ├─ Runbook: observability/runbooks/QueueBacklogGrowingNoThroughput.md
   └─ Labels: component, pipeline_version, schema_version

5. Telegram API delivers notification
   └─ Your phone receives alert

6. You investigate using runbook
   ├─ Check Grafana: TutorDex Overview dashboard
   ├─ Check logs: Loki query {compose_service="aggregator-worker"}
   └─ Fix issue (restart worker, check LLM, etc.)

7. Prometheus detects: throughput > 0

8. Alert resolves
   └─ Alertmanager sends resolved notification to Telegram
```

---

## Recording Rules Flow

```
Raw Metrics (every 15s):
  worker_parse_failure_total{reason="invalid_json"}
  worker_parse_failure_total{reason="missing_field"}
  worker_parse_success_total

        ↓ Prometheus evaluates every 30s

Pre-computed Aggregates:
  tutordex:worker:parse_failure_rate_per_s
  tutordex:worker:parse_success_rate_per_s
  tutordex:worker:parse_error_fraction

        ↓ Used in dashboards & alerts

Fast queries without re-aggregating!
```

---

## Key Design Decisions

### 1. **Low-Cardinality Labels**
- ✅ Use: `component`, `channel`, `pipeline_version`, `operation`, `reason`
- ❌ Never: `assignment_id`, `message_id`, `raw_id`, `user_id`, URLs
- Why: Prometheus performance, efficient indexing

### 2. **Structured JSON Logs**
- Format: `{"timestamp": "...", "level": "...", "message": "...", "context": {...}}`
- Why: Easy parsing, queryable fields, log-to-metrics correlation

### 3. **Volume-Mounted Configs**
- Alert rules: `./observability/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro`
- Why: Hot reload without rebuild, version control

### 4. **Severity-Based Routing**
- Critical: 30min repeat, immediate notification
- Warning: 6h repeat, grouped notifications
- Why: Noise reduction, alert fatigue prevention

### 5. **Recording Rules for Common Queries**
- Pre-compute aggregates every 30s
- Why: Fast dashboard loading, consistent calculations

### 6. **Health Probes + Scrapes**
- Blackbox: HTTP health checks every 15s
- Prometheus: Metric scrapes every 15s
- Why: Early failure detection, service availability monitoring

---

## Technology Choices

| Component | Technology | Why |
|-----------|-----------|-----|
| Metrics | Prometheus | Industry standard, pull-based, efficient |
| Logs | Loki | Prometheus-style labels, cost-effective |
| Traces | Tempo | Native Grafana integration, optional |
| Dashboards | Grafana | Unified UI for all signals |
| Alerts | Alertmanager | Grouping, routing, deduplication |
| Container Metrics | cAdvisor | Docker-native, comprehensive |
| Host Metrics | Node Exporter | Standard Linux metrics |
| Health Checks | Blackbox Exporter | Flexible probe configurations |
| Notifications | Telegram | Simple, reliable, mobile-first |

---

## Scalability Considerations

### Current Setup (Good for: 1-10k assignments/day)
- Single Prometheus instance
- Local disk storage (15 day retention)
- Single Loki instance
- All-in-one Grafana

### When to Scale (Beyond 10k assignments/day)
- **Metrics**: Add Thanos/Cortex for long-term storage & HA
- **Logs**: Add Loki read/write separation, object storage
- **Traces**: Increase sampling rate, add Tempo compactor
- **Alerts**: Add Alertmanager clustering for HA

See [CAPABILITIES.md](CAPABILITIES.md) section "Long-Term Metrics Storage" for details.

---

## Quick Reference

| What | Where |
|------|-------|
| Add metrics | Edit `TutorDexAggregator/observability_metrics.py` or `TutorDexBackend/metrics.py` |
| Add alerts | Edit `observability/prometheus/alert_rules.yml` |
| Add recording rules | Edit `observability/prometheus/recording_rules.yml` |
| Add dashboards | Edit `observability/grafana/dashboards/*.json` |
| Configure scrapes | Edit `observability/prometheus/prometheus.yml` |
| Configure alerting | Edit `observability/alertmanager/alertmanager.yml` |
| Reload Prometheus | Run `./observability/reload_prometheus.sh` |
| Check health | Run `./observability/doctor.sh` |

---

**See also:**
- [CAPABILITIES.md](CAPABILITIES.md) - What the stack does + what it can do
- [QUICK_START.md](QUICK_START.md) - Getting started guide
- [FAQ.md](FAQ.md) - Common questions
