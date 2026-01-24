# Homepage.dev Configuration

> **Internal infrastructure dashboard for TutorDex**  
> Single-pane-of-glass operational control panel

---

## 📍 Current Status

**Setup:** Basic (minimal configuration)
- ✅ Docker service running on port 7575
- ✅ `services.yaml` present (external Tailscale links)
- ❌ `settings.yaml` missing (using defaults)
- ❌ `widgets.yaml` missing (no system metrics)
- ❌ Docker socket not mounted (no container visibility)

**Access:**
- Local: `http://localhost:7575`
- Tailscale: `https://homepage.taildbd593.ts.net`

---

## 🎯 Transformation Plan Available

A complete plan to transform this into a professional SRE control panel is available:

📄 **[`docs/HOMEPAGE_DASHBOARD_PLAN.md`](../docs/HOMEPAGE_DASHBOARD_PLAN.md)**
- Complete service inventory (17 services)
- Dashboard blueprint (8 sections)
- 50+ step executor checklist
- Aesthetic strategy (dark theme, glassmorphism)
- 1,041 lines, fully detailed

🚀 **[`docs/HOMEPAGE_QUICK_START.md`](../docs/HOMEPAGE_QUICK_START.md)**
- 30-minute quick implementation
- Copy-paste commands
- Minimal viable dashboard setup

🎨 **[`docs/HOMEPAGE_VISUAL_REFERENCE.md`](../docs/HOMEPAGE_VISUAL_REFERENCE.md)**
- ASCII mockup of target layout
- Before/after comparison
- Color palette and styling guide

📊 **[`docs/HOMEPAGE_PROJECT_SUMMARY.md`](../docs/HOMEPAGE_PROJECT_SUMMARY.md)**
- Executive summary
- Implementation paths
- Success metrics

---

## 📂 Directory Structure

```
homepage/
├── assets/
│   ├── TutorDex-logo-1024.png  # Logo for favicon/branding
│   └── README.txt
├── config/
│   └── services.yaml           # Current: external links only
│   # Missing: settings.yaml, widgets.yaml, bookmarks.yaml
└── README.md                   # This file
```

---

## 🔧 Current Configuration

### services.yaml
- **Staging:** Links to staging Grafana, Prometheus, Alertmanager, Supabase
- **Production:** Links to production Grafana, Prometheus, Alertmanager, Supabase
- **Resources:** TutorDex website, GitHub repository

**All links are external HTTPS (Tailscale Serve endpoints)**

### Docker Compose (from root docker-compose.yml)
```yaml
homepage:
  image: ghcr.io/gethomepage/homepage:latest
  ports:
    - "0.0.0.0:${HOMEPAGE_PORT:-7575}:3000"
  volumes:
    - ./homepage/config:/app/config:ro
    - ./homepage/assets:/app/public/assets:ro
  environment:
    TZ: Asia/Singapore
    HOMEPAGE_ALLOWED_HOSTS: "localhost:7575,127.0.0.1:7575,[::1]:7575,homepage.taildbd593.ts.net"
```

---

## 🚀 Quick Start (Basic Setup)

### View Current Dashboard
```bash
# Open in browser
open http://localhost:7575
# or visit manually
```

### Restart After Config Changes
```bash
# From repo root
docker compose restart homepage

# Check logs
docker compose logs homepage --tail 50
```

---

## 🎯 Implementing the Transformation

To transform this into a professional control panel:

### Option 1: Quick Start (30 minutes)
Follow [`docs/HOMEPAGE_QUICK_START.md`](../docs/HOMEPAGE_QUICK_START.md)

**Creates:**
- `config/settings.yaml` (dark theme)
- `config/widgets.yaml` (system metrics)
- Enhanced `config/services.yaml` (local services)
- Docker socket mount (container visibility)

**Result:** Functional dashboard with metrics and dark theme

---

### Option 2: Full Implementation (2-4 hours)
Follow [`docs/HOMEPAGE_DASHBOARD_PLAN.md`](../docs/HOMEPAGE_DASHBOARD_PLAN.md)

**Creates:**
- Complete 8-section dashboard
- All system health widgets
- Pipeline health metrics
- Alert integration
- Cinema-quality aesthetic

**Result:** Production-ready SRE control panel

---

## 🎨 Target Aesthetic

**Theme:** Dark, cinematic, high-density
**Colors:** Slate palette with glassmorphism
**Layout:** Information-rich but calm

**Inspiration:**
- Professional homelab control panels
- SRE operational dashboards
- Futuristic UI aesthetics

See [`docs/HOMEPAGE_VISUAL_REFERENCE.md`](../docs/HOMEPAGE_VISUAL_REFERENCE.md) for visual mockup.

---

## 🔒 Security Notes

**Internal Access Only:**
- Homepage is for operators, not public
- Access via localhost or Tailscale only
- Do NOT expose port 7575 publicly

**Docker Socket:**
- When mounted, use read-only (`:ro`)
- Homepage can view containers, not modify
- Safe for internal dashboard use

**Secrets:**
- No secrets in config files
- Prometheus/Grafana URLs are internal
- External links use Tailscale auth

---

## 📖 Homepage.dev Documentation

**Official Docs:** https://gethomepage.dev

**Key Pages:**
- [Services](https://gethomepage.dev/latest/configs/services/) - Link configuration
- [Widgets](https://gethomepage.dev/latest/widgets/) - System metrics, Docker, etc.
- [Settings](https://gethomepage.dev/latest/configs/settings/) - Theme, layout, global config
- [Docker Integration](https://gethomepage.dev/latest/widgets/services/docker/) - Container visibility

---

## 🛠️ Development

### Testing Config Changes Locally
1. Edit files in `homepage/config/`
2. Restart: `docker compose restart homepage`
3. Check logs: `docker compose logs homepage`
4. Verify: Open `http://localhost:7575`

### Backup Before Changes
```bash
cp -r homepage/config homepage/config.backup
```

### Rollback
```bash
cp -r homepage/config.backup homepage/config
docker compose restart homepage
```

---

## 📊 Available Services (for widgets)

**Local Services:**
- Grafana: `http://grafana:3000` (external: `localhost:3300`)
- Prometheus: `http://prometheus:9090` (external: `localhost:9090`)
- Alertmanager: `http://alertmanager:9093` (external: `localhost:9093`)
- Backend: `http://backend:8000` (external: `localhost:8000`)
- Redis: `redis:6379` (no direct UI)

**Metrics Exporters:**
- cAdvisor: `http://cadvisor:8080` (Docker metrics)
- Node Exporter: `http://node-exporter:9100` (Host metrics)
- Blackbox: `http://blackbox-exporter:9115` (HTTP probes)

**External:**
- Supabase: `https://prod-supabase.taildbd593.ts.net`
- Website: `https://tutordex.web.app`

---

## 🧩 Widget Types Available

**System Metrics:**
- Glances widget (requires Glances server on host)
- Prometheus widget (custom PromQL queries)

**Service Health:**
- Ping widget (HTTP health checks)
- Docker widget (container status)

**Custom:**
- Custom API widget (JSON endpoints)
- Prometheus widget (metrics queries)

See [`docs/HOMEPAGE_DASHBOARD_PLAN.md`](../docs/HOMEPAGE_DASHBOARD_PLAN.md) Appendix A for widget reference.

---

## 🎯 Recommended Prometheus Queries

For use in Prometheus widgets:

```promql
# CPU Usage
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Memory Usage
100 - ((node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100)

# Disk Usage
100 - ((node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100)

# Collector Staleness
tutordex:collector:seconds_since_last_message

# Worker Queue Depth
tutordex_worker_queue_pending_jobs

# Active Alerts
sum(ALERTS{alertstate="firing"})
```

See [`docs/HOMEPAGE_DASHBOARD_PLAN.md`](../docs/HOMEPAGE_DASHBOARD_PLAN.md) Appendix B for more queries.

---

## 🚨 Troubleshooting

### Widgets Not Showing Data
**Problem:** Prometheus widgets show "Error"

**Solution:** Verify Prometheus connectivity
```bash
docker compose exec homepage curl http://prometheus:9090/api/v1/query?query=up
```

### Docker Widget Not Working
**Problem:** "Unable to connect to Docker"

**Solution:** Check Docker socket mount
```bash
docker compose exec homepage ls -la /var/run/docker.sock
```

### Theme Not Applied
**Problem:** Still seeing light theme

**Solution:** Check settings.yaml syntax and restart
```bash
docker compose exec homepage cat /app/config/settings.yaml
docker compose restart homepage
```

### Container Won't Start
**Problem:** Homepage container exits immediately

**Solution:** Check logs for config errors
```bash
docker compose logs homepage --tail 100
```

---

## 📝 Next Steps

1. **Read the plan:** [`docs/HOMEPAGE_DASHBOARD_PLAN.md`](../docs/HOMEPAGE_DASHBOARD_PLAN.md)
2. **Choose implementation path:**
   - Quick (30 min): Follow quick start guide
   - Full (2-4 hours): Follow executor checklist
3. **Test locally** before deploying
4. **Take screenshots** for documentation

---

## 🔗 Related Documentation

- [Observability Stack](../observability/README.md) - Prometheus, Grafana, Alertmanager
- [System Architecture](../docs/SYSTEM_INTERNAL.md) - How TutorDex works
- [Docker Compose](../docker-compose.yml) - Service definitions

---

**For implementation guidance, see:** [`docs/HOMEPAGE_PROJECT_SUMMARY.md`](../docs/HOMEPAGE_PROJECT_SUMMARY.md)
