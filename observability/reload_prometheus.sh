#!/bin/bash
# Helper script to reload Prometheus configuration after editing alert rules

set -e

PROMETHEUS_URL="${PROMETHEUS_URL:-http://localhost:9090}"

echo "Reloading Prometheus configuration..."

# Capture HTTP code, handling curl failures
if ! http_code=$(curl -sf -o /dev/null -w "%{http_code}" -X POST "$PROMETHEUS_URL/-/reload" 2>/dev/null); then
    echo "✗ Failed to connect to Prometheus at $PROMETHEUS_URL"
    echo ""
    echo "Possible causes:"
    echo "  - Prometheus is not running: docker compose ps prometheus"
    echo "  - Wrong URL (override with PROMETHEUS_URL env var)"
    echo "  - Network issue or firewall blocking connection"
    echo ""
    echo "Check Prometheus logs: docker compose logs prometheus | tail -50"
    exit 1
fi

if [ "$http_code" = "200" ]; then
    echo "✓ Prometheus configuration reloaded successfully"
    echo ""
    echo "Next steps:"
    echo "  1. Wait 15 seconds for Prometheus to re-evaluate rules"
    echo "  2. Check Prometheus rules: $PROMETHEUS_URL/rules"
    echo "  3. Check active alerts: $PROMETHEUS_URL/alerts"
    echo "  4. Check Alertmanager: ${ALERTMANAGER_URL:-http://localhost:9093}/#/alerts"
    echo ""
    echo "If you disabled an alert but still see notifications:"
    echo "  - Alertmanager may have cached the alert (repeat_interval: 4-24h)"
    echo "  - To force-clear: docker compose restart alertmanager"
    echo "  - See: observability/runbooks/DisablingAlerts.md"
    exit 0
else
    echo "✗ Failed to reload Prometheus (HTTP ${http_code:-unknown})"
    echo ""
    echo "Check Prometheus logs: docker compose logs prometheus | tail -50"
    exit 1
fi
