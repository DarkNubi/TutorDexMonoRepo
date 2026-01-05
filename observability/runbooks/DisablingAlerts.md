# Disabling or Modifying Alerts

This runbook covers how to properly disable or modify alert rules and ensure the changes take effect.

## How to Disable an Alert

To temporarily disable an alert without deleting it:

1. Edit `observability/prometheus/alert_rules.yml`
2. Change the alert's `expr` to `vector(0)`:
   ```yaml
   - alert: MyAlert
     expr: vector(0)  # This makes the alert never fire
     for: 10m
     labels:
       severity: warning
   ```
3. Add a comment explaining why it's disabled:
   ```yaml
   - alert: MyAlert
     # TEMP DISABLED: reason for disabling
     expr: vector(0)
     for: 10m
   ```

## Applying Alert Rule Changes

After modifying alert rules, you **must** reload Prometheus:

### Method 1: Hot Reload (Recommended)
```bash
curl -X POST http://localhost:9090/-/reload
```

Verify reload succeeded (should return HTTP 200):
```bash
curl -X POST http://localhost:9090/-/reload -w "\nHTTP Status: %{http_code}\n"
```

### Method 2: Restart Container
```bash
docker compose restart prometheus
```

### Method 3: Full Rebuild
```bash
# This rebuilds all containers, not just Prometheus
docker compose up -d --build
```

**Important**: Alert rule files are mounted as volumes, so file changes are visible immediately after reload. You do **not** need to rebuild the container.

## Why Am I Still Getting Alerts After Disabling?

If you still receive notifications after disabling an alert, check these:

### 1. Verify Prometheus Reloaded
Visit http://localhost:9090/rules and search for your alert. The expression should show `vector(0)`.

If it still shows the old expression, Prometheus didn't reload. Try:
```bash
# Reload Prometheus
curl -X POST http://localhost:9090/-/reload

# Check Prometheus logs for errors
docker compose logs prometheus | tail -50
```

### 2. Check Alertmanager State
Alertmanager caches alerts that are already firing. Even if Prometheus stops firing the alert, Alertmanager may continue sending notifications until:
- The `repeat_interval` expires (4-24 hours depending on severity)
- The alert transitions to "resolved" state
- Alertmanager is restarted (clears all cached state)

To check active alerts:
```bash
open http://localhost:9093/#/alerts
```

To force-clear Alertmanager cache:
```bash
docker compose restart alertmanager
```

**Warning**: Restarting Alertmanager clears all alert state, including legitimate active alerts.

### 3. Verify Alert Resolved in Prometheus
Visit http://localhost:9090/alerts and search for your alert. It should show:
- State: "Inactive" (if `expr: vector(0)`)
- No active instances

If it shows "Pending" or "Firing", Prometheus hasn't picked up the change.

### 4. Check Telegram Bot Logs
The `alertmanager-telegram` service is just a webhook receiver. If it's sending messages, Alertmanager is calling it.

```bash
docker compose logs alertmanager-telegram | tail -50
```

## Understanding the Alert Pipeline

```
alert_rules.yml (change here)
       ↓
Prometheus evaluates rules every 15s
       ↓
If expr > 0 for "for" duration → Alert FIRES
       ↓
Alertmanager receives alert
       ↓
Routes to telegram-warning/telegram-critical
       ↓
alertmanager-telegram sends to Telegram
```

To stop alerts from being sent:
1. Change `expr: vector(0)` in alert_rules.yml
2. Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`
3. Wait for Prometheus to re-evaluate (15 seconds)
4. Alert becomes "Resolved" in Alertmanager
5. Optional: Restart Alertmanager to clear cached state

## Common Mistakes

### ❌ Only editing the file without reloading
```bash
# This does NOT apply changes
vim observability/prometheus/alert_rules.yml
# Missing: curl -X POST http://localhost:9090/-/reload
```

### ❌ Running docker compose up without restart
```bash
# This may not restart prometheus if nothing else changed
docker compose up -d
# Use: docker compose up -d --force-recreate prometheus
# Or: curl -X POST http://localhost:9090/-/reload
```

### ❌ Waiting for alerts to "auto-clear"
Alerts have a `repeat_interval` (4-24h). They won't stop immediately even after disabling. You must:
1. Reload Prometheus (stops new firings)
2. Wait for alert to resolve, OR
3. Restart Alertmanager (clears cache immediately)

## Re-enabling Disabled Alerts

To re-enable a disabled alert:

1. Edit `observability/prometheus/alert_rules.yml`
2. Restore the original `expr` (check git history if needed)
3. Remove the "TEMP DISABLED" comment
4. Reload Prometheus: `curl -X POST http://localhost:9090/-/reload`
5. Verify in Prometheus UI: http://localhost:9090/rules

## Verifying Changes End-to-End

Complete verification checklist:

```bash
# 1. Edit alert rules
vim observability/prometheus/alert_rules.yml

# 2. Reload Prometheus
curl -X POST http://localhost:9090/-/reload

# 3. Check Prometheus picked it up (wait 15 seconds for evaluation)
sleep 15
curl -s http://localhost:9090/api/v1/rules | jq '.data.groups[].rules[] | select(.alert=="YourAlert")'

# 4. Check alert state in Prometheus
open http://localhost:9090/alerts

# 5. Check Alertmanager
open http://localhost:9093/#/alerts

# 6. Optional: Clear Alertmanager cache
docker compose restart alertmanager
```

## Additional Resources

- Prometheus reload API: https://prometheus.io/docs/prometheus/latest/management_api/#reload
- Alertmanager silences: http://localhost:9093/#/silences (alternative to disabling)
- Alert rules reference: `observability/prometheus/alert_rules.yml`
