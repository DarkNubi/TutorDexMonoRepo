# Alert Silencing Guide

This guide provides procedures and templates for silencing Prometheus alerts via Alertmanager during maintenance windows or known issues.

## Table of Contents
- [Quick Start](#quick-start)
- [When to Silence Alerts](#when-to-silence-alerts)
- [Silence Duration Guidelines](#silence-duration-guidelines)
- [Silence Templates](#silence-templates)
- [Creating Silences](#creating-silences)
- [Managing Active Silences](#managing-active-silences)
- [Automation](#automation)
- [Best Practices](#best-practices)

---

## Quick Start

**Access Alertmanager UI**: http://localhost:9093

**Create a silence**:
1. Go to http://localhost:9093/#/silences
2. Click "New Silence"
3. Fill in matchers, duration, and comment
4. Click "Create"

**View active silences**: http://localhost:9093/#/silences

---

## When to Silence Alerts

Silence alerts during:

### ✅ Planned Maintenance
- Database migrations
- Service upgrades or restarts
- Infrastructure changes
- Network maintenance

### ✅ Known Issues
- Investigating ongoing incidents (to reduce noise)
- Waiting for external service recovery
- Temporary performance degradation during high load

### ✅ Testing and Development
- Load testing that triggers threshold alerts
- Integration testing with external services
- Deployment verification in staging

### ❌ Do NOT Silence For
- Alerts you don't understand (investigate first)
- "Noisy" alerts (fix the threshold or alert instead)
- Long-term known issues (fix the issue or adjust SLO)

---

## Silence Duration Guidelines

| Scenario | Recommended Duration | Max Duration |
|----------|---------------------|--------------|
| Service restart | 5-10 minutes | 15 minutes |
| Database migration | 30-60 minutes | 2 hours |
| Planned maintenance window | Actual window + 30min | 4 hours |
| Known issue investigation | 1-2 hours | 4 hours |
| External service outage | 2-4 hours | 8 hours |

**Always set the shortest reasonable duration**. You can extend if needed.

---

## Silence Templates

### Template 1: Planned Maintenance (Service Restart)

**Use case**: Restarting a specific service

**Matchers**:
```
job="tutordex_worker"
alertname=~"QueueBacklog.*|WorkerDown"
```

**Duration**: 10 minutes

**Comment**: 
```
Planned restart of worker service for deployment.
Contact: @ops-team
Ticket: MAINT-123
```

---

### Template 2: Database Migration

**Use case**: Running database migrations that may slow queries

**Matchers**:
```
component="worker"
alertname=~"Supabase.*|DBLatency.*"
```

**Duration**: 1 hour

**Comment**:
```
Database migration in progress.
Expected completion: [TIME]
Contact: @db-team
Ticket: MAINT-456
```

---

### Template 3: Collector Maintenance

**Use case**: Restarting collector or fixing Telegram issues

**Matchers**:
```
component="collector"
alertname=~"Collector.*"
```

**Duration**: 15 minutes

**Comment**:
```
Collector service maintenance.
Contact: @ops-team
Ticket: MAINT-789
```

---

### Template 4: Infrastructure Alerts During Load Test

**Use case**: Suppressing infrastructure alerts during planned load test

**Matchers**:
```
severity="warning"
component="infra"
```

**Duration**: 2 hours

**Comment**:
```
Load testing in progress.
Expected end: [TIME]
Contact: @performance-team
Ticket: TEST-101
```

---

### Template 5: Specific Alert (Any Component)

**Use case**: Silencing a single specific alert

**Matchers**:
```
alertname="QueueBacklogGrowingNoThroughput"
```

**Duration**: 30 minutes

**Comment**:
```
Investigating queue backlog issue.
Root cause: [DESCRIPTION]
Contact: @oncall
Ticket: INC-202
```

---

### Template 6: Channel-Specific Issues

**Use case**: Silencing alerts for a problematic channel

**Matchers**:
```
channel="problematic_channel_name"
```

**Duration**: 4 hours

**Comment**:
```
Channel [NAME] experiencing upstream issues.
Waiting for channel owner to resolve.
Contact: @channel-support
Ticket: SUP-303
```

---

## Creating Silences

### Method 1: Alertmanager UI (Recommended)

1. **Open Alertmanager**: http://localhost:9093
2. **Navigate to Silences**: Click "Silences" in top nav or go to `/#/silences`
3. **Click "New Silence"**
4. **Add Matchers**:
   - Click "+ Add Matcher"
   - Enter: Name (e.g., `alertname`), Value (e.g., `QueueBacklogGrowing`)
   - Use `=~` for regex matching (e.g., `alertname =~ "Queue.*"`)
   - Add multiple matchers for more specific silencing
5. **Set Duration**:
   - Start: Usually "Now"
   - Duration: e.g., "1h", "30m", "2h"
   - Or set specific End time
6. **Add Comment**: Include:
   - Reason for silence
   - Expected duration
   - Contact person
   - Ticket/incident number
7. **Set Creator**: Your name/username
8. **Click "Create"**

### Method 2: amtool CLI

```bash
# Install amtool (if not already installed)
# On Ubuntu/Debian: apt-get install prometheus-alertmanager
# On macOS: brew install alertmanager

# Create a silence
amtool silence add \
  alertname="QueueBacklogGrowingNoThroughput" \
  --duration=1h \
  --comment="Planned maintenance - Worker restart" \
  --author="ops-team" \
  --alertmanager.url=http://localhost:9093

# Create silence with multiple matchers
amtool silence add \
  job="tutordex_worker" \
  severity="warning" \
  --duration=30m \
  --comment="Investigating high latency" \
  --author="oncall-engineer" \
  --alertmanager.url=http://localhost:9093
```

### Method 3: HTTP API

```bash
# Create silence via API
curl -X POST http://localhost:9093/api/v2/silences \
  -H "Content-Type: application/json" \
  -d '{
    "matchers": [
      {
        "name": "alertname",
        "value": "QueueBacklogGrowingNoThroughput",
        "isRegex": false,
        "isEqual": true
      }
    ],
    "startsAt": "2026-01-10T10:00:00Z",
    "endsAt": "2026-01-10T11:00:00Z",
    "createdBy": "ops-team",
    "comment": "Planned maintenance"
  }'
```

---

## Managing Active Silences

### View All Silences

**UI**: http://localhost:9093/#/silences

**CLI**:
```bash
amtool silence query --alertmanager.url=http://localhost:9093
```

### Extend a Silence

**UI**:
1. Go to Silences page
2. Find the silence
3. Click "Edit"
4. Adjust end time
5. Click "Update"

**CLI**:
```bash
# Get silence ID first
amtool silence query --alertmanager.url=http://localhost:9093

# Update silence (extend by 1 hour)
amtool silence update <SILENCE_ID> \
  --duration=1h \
  --alertmanager.url=http://localhost:9093
```

### Delete a Silence

**UI**:
1. Go to Silences page
2. Find the silence
3. Click "Expire" button

**CLI**:
```bash
amtool silence expire <SILENCE_ID> \
  --alertmanager.url=http://localhost:9093
```

**API**:
```bash
curl -X DELETE http://localhost:9093/api/v2/silence/<SILENCE_ID>
```

---

## Automation

### Scheduled Maintenance Windows

For recurring maintenance, consider scripting silence creation:

```bash
#!/bin/bash
# File: create_maintenance_silence.sh

ALERTMANAGER_URL="http://localhost:9093"
DURATION="2h"
COMMENT="Scheduled weekly maintenance window"
AUTHOR="automation"

# Create silence for all warning alerts during maintenance
amtool silence add \
  severity="warning" \
  --duration="$DURATION" \
  --comment="$COMMENT" \
  --author="$AUTHOR" \
  --alertmanager.url="$ALERTMANAGER_URL"

echo "Maintenance silence created for $DURATION"
```

### Pre-Deployment Silence

Create silences automatically before deployments:

```bash
#!/bin/bash
# File: pre_deploy_silence.sh

SERVICE="$1"  # e.g., "worker", "backend", "collector"
DURATION="${2:-15m}"  # default 15 minutes

case "$SERVICE" in
  worker)
    MATCHERS='job="tutordex_worker"'
    ;;
  backend)
    MATCHERS='job="tutordex_backend"'
    ;;
  collector)
    MATCHERS='job="tutordex_collector"'
    ;;
  *)
    echo "Unknown service: $SERVICE"
    exit 1
    ;;
esac

amtool silence add \
  $MATCHERS \
  --duration="$DURATION" \
  --comment="Automated deployment silence for $SERVICE" \
  --author="ci-cd-pipeline" \
  --alertmanager.url="http://localhost:9093"

echo "Deployment silence created for $SERVICE ($DURATION)"
```

Usage:
```bash
./pre_deploy_silence.sh worker 10m
```

### Integration with CI/CD

Add to your deployment pipeline:

```yaml
# .github/workflows/deploy.yml
- name: Create Alert Silence
  run: |
    curl -X POST http://alertmanager:9093/api/v2/silences \
      -H "Content-Type: application/json" \
      -d '{
        "matchers": [{"name": "job", "value": "tutordex_worker", "isEqual": true}],
        "startsAt": "'$(date -u +%Y-%m-%dT%H:%M:%SZ)'",
        "endsAt": "'$(date -u -d '+15 minutes' +%Y-%m-%dT%H:%M:%SZ)'",
        "createdBy": "github-actions",
        "comment": "Deployment: ${{ github.sha }}"
      }'

- name: Deploy Service
  run: docker compose up -d --force-recreate worker
```

---

## Best Practices

### ✅ Do

- **Always add a descriptive comment** with reason, contact, and ticket number
- **Use specific matchers** (don't silence everything)
- **Set shortest reasonable duration** and extend if needed
- **Document in runbook** if this is a recurring silence need
- **Review active silences regularly** and clean up expired ones
- **Use severity-based silences** during maintenance (silence warnings, keep criticals)
- **Test your matchers** before creating long silences

### ❌ Don't

- **Don't silence critical alerts** unless absolutely necessary
- **Don't create silences longer than 8 hours** without approval
- **Don't silence alerts you don't understand** (investigate first)
- **Don't forget to remove silences** when issue is resolved
- **Don't silence based on instance** if the issue affects all instances
- **Don't use catch-all matchers** like `alertname=".*"` without good reason

---

## Silence Matcher Reference

### Common Alert Labels

Use these labels in your matchers:

| Label | Example Values | Description |
|-------|----------------|-------------|
| `alertname` | `QueueBacklogGrowing`, `LLMFailureSpike` | Specific alert name |
| `severity` | `warning`, `critical` | Alert severity |
| `component` | `worker`, `collector`, `backend`, `infra` | System component |
| `job` | `tutordex_worker`, `tutordex_backend` | Prometheus job name |
| `channel` | `channel_name` | Telegram channel (for channel-specific alerts) |
| `operation` | `persist`, `fetch`, `update` | DB operation type |
| `pipeline_version` | `v1`, `v2` | Extraction pipeline version |
| `schema_version` | `1`, `2` | Schema version |

### Matcher Operators

- `=`: Exact match (e.g., `alertname="QueueBacklogGrowing"`)
- `!=`: Not equal (e.g., `severity!="critical"`)
- `=~`: Regex match (e.g., `alertname=~"Queue.*"`)
- `!~`: Negative regex (e.g., `alertname!~"Watchdog"`)

### Example Matcher Combinations

```bash
# Silence all queue-related warnings
alertname=~"Queue.*"
severity="warning"

# Silence specific service, keep criticals
job="tutordex_worker"
severity!="critical"

# Silence specific channel issues
channel="problematic_channel"

# Silence all warnings during maintenance
severity="warning"
component=~"worker|collector"
```

---

## Troubleshooting

### Silence Not Working

**Check**:
1. **Matchers are correct**: Verify label names and values match the alert
2. **Silence is active**: Check start/end times
3. **Alert is still firing**: Silences don't stop alerts from firing, just notifications
4. **Alertmanager is running**: `docker compose ps alertmanager`

**Debug**:
```bash
# View alert labels
curl http://localhost:9093/api/v2/alerts | jq '.[] | select(.labels.alertname=="QueueBacklogGrowing")'

# View active silences
curl http://localhost:9093/api/v2/silences?active=true | jq '.'
```

### Accidentally Silenced Too Much

**Immediately**:
1. Go to http://localhost:9093/#/silences
2. Find the silence
3. Click "Expire" to remove it immediately

**Or via CLI**:
```bash
amtool silence expire <SILENCE_ID> --alertmanager.url=http://localhost:9093
```

### Silence Expired But Alerts Still Quiet

**Cause**: Alert may need time to re-evaluate (up to 1 minute)

**Wait**: Give it 1-2 minutes for alerts to start firing again

**Check**:
```bash
# Verify alert is actually firing in Prometheus
curl http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.name=="QueueBacklogGrowing")'
```

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────┐
│                   ALERT SILENCING CHEAT SHEET               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Alertmanager UI: http://localhost:9093                    │
│                                                             │
│  Create Silence:                                            │
│    1. Go to /#/silences                                     │
│    2. Click "New Silence"                                   │
│    3. Add matchers (e.g., alertname="QueueBacklogGrowing") │
│    4. Set duration (e.g., 1h)                               │
│    5. Add comment with reason + contact + ticket           │
│    6. Click "Create"                                        │
│                                                             │
│  Expire Silence:                                            │
│    1. Go to /#/silences                                     │
│    2. Find silence                                          │
│    3. Click "Expire"                                        │
│                                                             │
│  Common Durations:                                          │
│    - Service restart: 10m                                   │
│    - DB migration: 1h                                       │
│    - Maintenance window: 2-4h                               │
│    - Known issue: 1-2h                                      │
│                                                             │
│  Always Include in Comment:                                 │
│    - Reason for silence                                     │
│    - Contact person                                         │
│    - Ticket/incident number                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Additional Resources

- **Alertmanager Documentation**: https://prometheus.io/docs/alerting/latest/alertmanager/
- **Silence API Docs**: https://prometheus.io/docs/alerting/latest/clients/
- **amtool Documentation**: https://github.com/prometheus/alertmanager#amtool
- **TutorDex Runbooks**: `observability/runbooks/`
- **TutorDex Alert Rules**: `observability/prometheus/alert_rules.yml`

---

## Feedback

If you find this guide unclear or need additional templates, please:
1. Create a ticket: `DOCS-XXX`
2. Update this guide with your improvements
3. Share common silence patterns with the team

**Document Version**: 1.0  
**Last Updated**: 2026-01-10  
**Owner**: Operations Team
