# Alert System FAQ

## Q: I disabled an alert but I'm still receiving Telegram messages. Why?

**A:** There are three possible reasons:

1. **Prometheus hasn't reloaded the configuration**
   - Alert rules are read from `observability/prometheus/alert_rules.yml`
   - After editing the file, you MUST reload Prometheus
   - Run: `./observability/reload_prometheus.sh` or `curl -X POST http://localhost:9090/-/reload`

2. **Alertmanager has cached the alert**
   - Alertmanager remembers alerts that are already firing
   - It will continue sending notifications based on `repeat_interval` (4-24 hours)
   - To force-clear: `docker compose restart alertmanager`

3. **The alert is being sent from a different source**
   - Verify the Telegram message is actually from Alertmanager
   - Check the message format (should include component, pipeline version, etc.)

## Q: Does `docker compose up -d --build` at root update Prometheus configuration?

**A:** Yes, BUT it's overkill. Here's what happens:

- `--build` rebuilds Docker images (only needed if Dockerfile changed)
- `-d` starts services in detached mode
- Alert rule files are mounted as **volumes** (see `docker-compose.yml` line 172)
- Changes to mounted files are visible immediately - no rebuild needed
- The container will restart if built, which reloads config

**Better approach:**
1. Edit `observability/prometheus/alert_rules.yml`
2. Run `./observability/reload_prometheus.sh` (hot reload, no downtime)
3. Wait 15 seconds for Prometheus to re-evaluate rules
4. If still getting alerts, restart Alertmanager: `docker compose restart alertmanager`

## Q: Which container runs the alert code?

**A:** Alert routing involves multiple containers:

1. **prometheus** - Evaluates alert rules (from `alert_rules.yml`)
2. **alertmanager** - Routes alerts to receivers, handles grouping/deduplication
3. **alertmanager-telegram** - Receives webhooks from Alertmanager and sends to Telegram

To disable an alert:
- Edit `observability/prometheus/alert_rules.yml` (change `expr: vector(0)`)
- Reload **prometheus**: `./observability/reload_prometheus.sh`
- Optionally restart **alertmanager**: `docker compose restart alertmanager`

## Q: How do I verify my alert changes took effect?

**A:** Follow this checklist:

```bash
# 1. Edit alert rules
vim observability/prometheus/alert_rules.yml

# 2. Reload Prometheus
./observability/reload_prometheus.sh

# 3. Check Prometheus picked it up (wait 15 seconds)
sleep 15
open http://localhost:9090/rules
# Find your alert - verify the expression shows vector(0)

# 4. Check alert state
open http://localhost:9090/alerts
# Your alert should show "Inactive"

# 5. Check Alertmanager
open http://localhost:9093/#/alerts
# Verify no active alerts for your disabled rule

# 6. Optional: Clear Alertmanager cache
docker compose restart alertmanager
```

## Q: What if I want to temporarily silence an alert instead of disabling it?

**A:** Use Alertmanager silences instead:

1. Go to http://localhost:9093/#/silences
2. Click "New Silence"
3. Add matchers: `alertname="YourAlert"`
4. Set duration (1h, 1d, 1w, etc.)
5. Add comment explaining why
6. Click "Create"

**Difference between silencing and disabling:**
- **Silence**: Alert still fires in Prometheus, but Alertmanager doesn't send notifications
- **Disable**: Alert never fires (set `expr: vector(0)`)

Silences are better for temporary muting (maintenance windows, known issues).
Disabling is better for permanently turning off an alert.

## Q: How long does Alertmanager cache alerts?

**A:** Depends on the alert's severity (see `observability/alertmanager/alertmanager.yml`):

- **Watchdog**: `repeat_interval: 24h`
- **Critical**: `repeat_interval: 30m`
- **Warning**: `repeat_interval: 6h`

An alert that's already firing will continue sending notifications at this interval until:
- The alert resolves (Prometheus stops firing it)
- You create a silence in Alertmanager
- You restart Alertmanager (clears all state)

## Q: Can I test if my alert works without waiting for it to fire?

**A:** Yes, use Prometheus's expression browser:

1. Go to http://localhost:9090/graph
2. Enter your alert's expression (e.g., `up == 0`)
3. Click "Execute"
4. If the query returns results, the alert would fire

Or force an alert to fire:
```yaml
# Temporary test alert
- alert: TestAlert
  expr: vector(1)  # Always fires
  for: 0m
  labels:
    severity: warning
  annotations:
    summary: "Test alert"
    description: "This is a test"
```

Reload Prometheus and it will fire immediately.

## Additional Resources

- **Disabling Alerts Guide**: [observability/runbooks/DisablingAlerts.md](runbooks/DisablingAlerts.md)
- **Observability README**: [observability/README.md](README.md)
- **Prometheus Reload API**: https://prometheus.io/docs/prometheus/latest/management_api/#reload
- **Alertmanager Configuration**: [observability/alertmanager/alertmanager.yml](alertmanager/alertmanager.yml)
