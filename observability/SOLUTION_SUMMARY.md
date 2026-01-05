# Solution Summary: CollectorStalled Alert Issue

## Your Original Question

> CollectorStalled alert is disabled, but why am I still receiving telegram messages for it? Is it because I didn't update the docker container that runs the code? Which one is it? Does `docker compose up -d --build` at root update it?

## The Answer

**TL;DR**: You need to **reload Prometheus** after editing alert rules. Alertmanager also caches active alerts.

### Quick Fix

```bash
# Step 1: Reload Prometheus (picks up the disabled alert)
./observability/reload_prometheus.sh
# OR: curl -X POST http://localhost:9090/-/reload

# Step 2: Clear Alertmanager cache (stops continued notifications)
docker compose restart alertmanager
```

### Detailed Explanation

#### 1. Does `docker compose up -d --build` update it?

**Yes, but it's unnecessary.** Here's why:

- Alert rules are mounted as a **volume** (see `docker-compose.yml` line 172):
  ```yaml
  - ./observability/prometheus/alert_rules.yml:/etc/prometheus/alert_rules.yml:ro
  ```
- File changes on disk are visible immediately to the container
- You only need to tell Prometheus to **reload its configuration**
- `--build` rebuilds the Docker image (only needed if Dockerfile changed)

#### 2. Which container runs the alert code?

There are **three containers** involved:

1. **prometheus** - Evaluates alert rules every 15 seconds
   - Reads `alert_rules.yml` 
   - Needs reload when rules change
   - Your change: `expr: vector(0)` makes it never fire

2. **alertmanager** - Routes alerts to receivers
   - Caches alerts that are already firing
   - Continues sending based on `repeat_interval` (6 hours for warnings)
   - Needs restart to clear cache

3. **alertmanager-telegram** - Sends to Telegram
   - Just a webhook receiver (passive)
   - Doesn't control which alerts fire

#### 3. Why are you still getting messages?

Two reasons:

**A. Prometheus hasn't reloaded**
- You edited the file, but Prometheus still has the old rules in memory
- Solution: `curl -X POST http://localhost:9090/-/reload`

**B. Alertmanager has cached the alert**
- The alert was already firing before you disabled it
- Alertmanager will continue sending for up to 6 hours (warning repeat_interval)
- Solution: `docker compose restart alertmanager`

## What We Added

### 1. Documentation

**FAQ** (`observability/FAQ.md`)
- Answers your exact questions
- Explains docker compose behavior
- Shows which containers do what

**Troubleshooting Guide** (`observability/runbooks/DisablingAlerts.md`)
- Step-by-step instructions
- Common mistakes to avoid
- Verification checklist

**Updated README** (`observability/README.md`)
- Reload instructions
- Link to FAQ and troubleshooting

### 2. Helper Script

**`observability/reload_prometheus.sh`**
```bash
#!/bin/bash
# Reloads Prometheus and shows next steps
./observability/reload_prometheus.sh
```

Output:
```
✓ Prometheus configuration reloaded successfully

Next steps:
  1. Wait 15 seconds for Prometheus to re-evaluate rules
  2. Check Prometheus rules: http://localhost:9090/rules
  3. Check active alerts: http://localhost:9090/alerts
  4. Check Alertmanager: http://localhost:9093/#/alerts

If you disabled an alert but still see notifications:
  - Alertmanager may have cached the alert (repeat_interval: 4-24h)
  - To force-clear: docker compose restart alertmanager
```

### 3. Updated Runbooks

**CollectorStalled.md**
- Now notes the alert is disabled
- Links to troubleshooting guide

**Added DisablingAlerts.md**
- Complete reference for managing alerts
- Covers silencing vs disabling
- Testing and verification

## How to Verify the Fix

```bash
# 1. Check Prometheus picked up the change
curl -s http://localhost:9090/api/v1/rules | \
  jq '.data.groups[].rules[] | select(.alert=="CollectorStalled")'
# Should show: "expr": "vector(0)"

# 2. Check alert is inactive
open http://localhost:9090/alerts
# CollectorStalled should be "Inactive"

# 3. Check Alertmanager
open http://localhost:9093/#/alerts
# CollectorStalled should not appear

# 4. Wait a few minutes and check Telegram
# No new CollectorStalled messages should arrive
```

## Key Takeaways

1. **Volume-mounted files** don't need container rebuild - just reload
2. **Prometheus reload** is separate from container restart
3. **Alertmanager caches** can cause alerts to continue temporarily
4. **Use the helper script** for easy reload: `./observability/reload_prometheus.sh`
5. **Check the FAQ** next time: `observability/FAQ.md`

## Related Documentation

- **FAQ**: `observability/FAQ.md`
- **Troubleshooting**: `observability/runbooks/DisablingAlerts.md`
- **Main README**: `observability/README.md`

## Still Having Issues?

If you're still getting CollectorStalled alerts after:
1. Running `./observability/reload_prometheus.sh`
2. Restarting Alertmanager: `docker compose restart alertmanager`
3. Waiting 5 minutes

Then check:
- Prometheus logs: `docker compose logs prometheus | tail -100`
- Alertmanager logs: `docker compose logs alertmanager | tail -100`
- alertmanager-telegram logs: `docker compose logs alertmanager-telegram | tail -100`

The issue might be elsewhere (e.g., multiple Prometheus instances running).
