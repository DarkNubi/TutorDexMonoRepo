# Homepage.dev Dashboard - Quick Start Guide

> **For operators who want to get started quickly**  
> Full plan: [HOMEPAGE_DASHBOARD_PLAN.md](HOMEPAGE_DASHBOARD_PLAN.md)

---

## TL;DR: What This Plan Does

Transforms the current Homepage.dev dashboard from a simple link list into a **professional SRE control panel** with:

- ✅ Real-time system health (CPU, RAM, Disk, Uptime)
- ✅ Docker container status
- ✅ Active alert count
- ✅ One-click access to all observability tools
- ✅ Dark, cinematic aesthetic (glassmorphism + high-density)

**Before:** Basic link directory to remote staging/production services  
**After:** Single-pane-of-glass dashboard for immediate health assessment

---

## Quick Implementation (30 Minutes)

### Step 1: Create settings.yaml

```bash
cd /home/runner/work/TutorDexMonoRepo/TutorDexMonoRepo
cat > homepage/config/settings.yaml << 'EOF'
title: TutorDex Infrastructure
favicon: /assets/TutorDex-logo-1024.png
theme: dark
color: slate
headerStyle: boxed
hideVersion: true
language: en
locale: en-SG
timezone: Asia/Singapore

layout:
  "System Health":
    style: row
    columns: 4
  Observability:
    style: row
    columns: 3
  "Core Services":
    style: row
    columns: 2
EOF
```

### Step 2: Enable Docker Widget (Container Visibility)

Update `docker-compose.yml` homepage service to add Docker socket:

```yaml
homepage:
  # ... existing config ...
  volumes:
    - ./homepage/config:/app/config:ro
    - ./homepage/assets:/app/public/assets:ro
    - /var/run/docker.sock:/var/run/docker.sock:ro  # ADD THIS LINE
```

### Step 3: Create Minimal widgets.yaml

```bash
cat > homepage/config/widgets.yaml << 'EOF'
# Docker container health
- docker:
    - Container Overview:
        widget:
          type: docker
          url: unix:///var/run/docker.sock

# System metrics (via Prometheus)
- prometheus:
    href: http://prometheus:9090
    - CPU Usage:
        query: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
        suffix: "%"
    - Memory Usage:
        query: 100 - ((node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100)
        suffix: "%"
    - Disk Usage:
        query: 100 - ((node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100)
        suffix: "%"
EOF
```

### Step 4: Update services.yaml (Add Local Services)

Add this to the **top** of `homepage/config/services.yaml`:

```yaml
---
- System Health:
    - icon: mdi-monitor-dashboard

- Observability:
    - icon: mdi-chart-line
    - Grafana:
        icon: grafana
        href: http://localhost:3300
        description: Metrics visualization and dashboards
        target: _blank
        widget:
          type: ping
          url: http://grafana:3000
    
    - Prometheus:
        icon: prometheus
        href: http://localhost:9090
        description: Metrics collection and alerting
        target: _blank
        widget:
          type: ping
          url: http://prometheus:9090
    
    - Alertmanager:
        icon: mdi-bell
        href: http://localhost:9093
        description: Alert routing and management
        target: _blank
        widget:
          type: ping
          url: http://alertmanager:9093

- Core Services:
    - icon: mdi-application
    - Backend API:
        icon: mdi-api
        href: http://localhost:8000/docs
        description: FastAPI backend (Swagger UI)
        target: _blank
        widget:
          type: ping
          url: http://backend:8000/health/live

# Keep existing staging/production sections below...
```

### Step 5: Restart and Test

```bash
# Restart homepage to apply changes
docker compose up -d homepage

# Check logs
docker compose logs homepage --tail 50

# Open in browser
open http://localhost:7575
# or visit manually: http://localhost:7575
```

---

## What You Should See

After implementation:

1. **Dark theme** with slate color palette
2. **System Health** section with CPU/RAM/Disk metrics
3. **Docker Containers** widget showing running containers
4. **Observability** section with Grafana/Prometheus/Alertmanager + status indicators
5. **Core Services** section with Backend API + health check
6. **Staging/Production** links below (existing services preserved)

---

## Troubleshooting

### Widgets Not Showing Data

**Problem:** Prometheus widgets show "Error" or no data

**Solution:** Verify Prometheus is reachable from homepage container:
```bash
docker compose exec homepage curl http://prometheus:9090/api/v1/query?query=up
```

### Docker Widget Not Working

**Problem:** Container widget shows "Unable to connect"

**Solution:** Verify Docker socket is mounted:
```bash
docker compose exec homepage ls -la /var/run/docker.sock
# Should show: srw-rw-rw- ... /var/run/docker.sock
```

### Theme Not Applied

**Problem:** Still seeing light theme or default colors

**Solution:** Check settings.yaml syntax:
```bash
docker compose exec homepage cat /app/config/settings.yaml
# Should show your settings
```

Restart if needed:
```bash
docker compose restart homepage
```

---

## Next Steps

This quick start gives you a functional dashboard in 30 minutes. For the **complete transformation** with:

- Custom Prometheus widgets (queue depth, pipeline staleness)
- Alert count badges
- Background images and glassmorphism
- Pipeline health section
- Complete aesthetic refinement

Follow the full **[HOMEPAGE_DASHBOARD_PLAN.md](HOMEPAGE_DASHBOARD_PLAN.md)** executor checklist (50+ steps).

---

## Key Files

- `homepage/config/settings.yaml` - Theme, layout, global settings
- `homepage/config/widgets.yaml` - System metrics, Docker, Prometheus widgets
- `homepage/config/services.yaml` - Links to services (local and remote)
- `docker-compose.yml` - Homepage service config (Docker socket mount)

---

## Security Note

**Docker Socket Mount:**
- Mounted as **read-only** (`:ro`)
- Homepage can view container status but cannot start/stop/modify
- Safe for internal dashboard use
- Do NOT expose Homepage port publicly

---

## Full Documentation

For the complete, production-ready implementation:

📄 **[HOMEPAGE_DASHBOARD_PLAN.md](HOMEPAGE_DASHBOARD_PLAN.md)**

Includes:
- Complete service inventory (17 services)
- Visual hierarchy design
- Detailed executor checklist (11 phases)
- Prometheus query examples
- Alternative implementations (Glances vs Prometheus)
- Security considerations
- Future enhancements

---

**Estimated Time:**
- Quick Start: 30 minutes
- Full Implementation: 2-4 hours (with testing and validation)

**Difficulty:** Beginner (config files only, no code changes)
