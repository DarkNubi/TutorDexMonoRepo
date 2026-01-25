# Homepage.dev Configuration

> **Internal infrastructure dashboard for TutorDex**  
> Organized by the **TutorDex Infrastructure Operating Doctrine** (Homepage-Centric Model)

---

## 🎯 Doctrine Compliance

This homepage follows the **TutorDex Infrastructure Operating Doctrine**, which defines:

### Core Principles

**Homepage Role: Observe**
- "What exists, where is it, is it alive?"
- Read-only navigation layer (links, health, status)
- **NO** restart/trigger/edit/mutation capabilities
- Safe to share with collaborators, auditors, future hires

**System Boundaries:**
- 🧭 **Homepage** → Observe (navigation)
- 📊 **Grafana** → Understand (analysis)
- 🚨 **Alertmanager** → Interrupt (alerts)
- 🤖 **CI/CD** → Mutate (changes)
- 🧠 **Humans** → Decide (judgment)

### Grouping Model

✅ **Correct:** Group by **mental model/intent**
- Core Platform (API, Workers, Aggregators)
- Data & Identity (Supabase, Redis)
- Observability (Grafana, Prometheus, Alertmanager)
- Bots & Automation (Telegram bots, agents)

❌ **Wrong:** Group by technology, ports, or vendors
- Don't group by "Docker containers"
- Don't group by "Port 8000 services"
- Don't group by "Grafana Labs tools"

### Environment Separation

**Top-level grouping by environment:**
1. 🔧 **Dev** (Local development)
2. 🧪 **Staging** (Testing)
3. ⚠️ **PROD** (Production)

Each environment has consistent sections:
- Core Platform
- Data & Identity
- Observability
- (Bots & Automation for Dev only)

**Visual clarity:**
- Dev = 🔧 (wrench emoji)
- Staging = 🧪 (test tube emoji)
- Prod = ⚠️ (warning emoji + "PROD" prefix)

---

## 📍 Current Status

**Implementation:** Doctrine-compliant (as of 2026-01-25)
- ✅ Read-only (no mutation capabilities)
- ✅ Environment-first grouping (Dev → Staging → Prod)
- ✅ Intent-based sections (not tech-based)
- ✅ Clear visual environment indicators
- ✅ Docker service running on port 7575
- ✅ Config volumes mounted read-only (`:ro`)
- ✅ Docker socket read-only (safe container visibility)

**Implementation:** Doctrine-compliant (as of 2026-01-25)
- ✅ Read-only (no mutation capabilities)
- ✅ Environment-first grouping (Dev → Staging → Prod)
- ✅ Intent-based sections (not tech-based)
- ✅ Clear visual environment indicators
- ✅ Docker service running on port 7575
- ✅ Config volumes mounted read-only (`:ro`)
- ✅ Docker socket read-only (safe container visibility)

**Access:**
- Local: `http://localhost:7575`
- Tailscale: `https://homepage.taildbd593.ts.net`

---

## 🏗️ Structure

### Current Layout (Doctrine-Compliant)

```
TutorDex Infrastructure
├── 🔧 Dev — Core Platform
│   ├── Backend API
│   ├── Aggregator Worker
│   └── Collector
├── 🔧 Dev — Data & Identity
│   ├── Supabase
│   └── Redis
├── 🔧 Dev — Observability
│   ├── Grafana
│   ├── Prometheus
│   └── Alertmanager
├── 🔧 Dev — Bots & Automation
│   ├── Telegram Link Bot
│   └── GitHub Repository
│
├── 🧪 Staging — Core Platform
│   └── TutorDex Website
├── 🧪 Staging — Data & Identity
│   ├── Supabase
│   └── Logflare
├── 🧪 Staging — Observability
│   ├── Grafana
│   ├── Prometheus
│   └── Alertmanager
│
└── ⚠️ PROD — Core Platform
    └── TutorDex Website
    ⚠️ PROD — Data & Identity
    ├── Supabase
    └── Logflare
    ⚠️ PROD — Observability
    ├── Grafana
    ├── Prometheus
    └── Alertmanager
```

### Design Decisions

1. **Environment First**: Dev, Staging, Prod are top-level groups
   - Prevents accidental prod actions
   - Clear mental separation

2. **Intent-Based Grouping**: Within each environment
   - Core Platform (what delivers value)
   - Data & Identity (where state lives)
   - Observability (how we see what's happening)
   - Bots & Automation (supporting automation)

3. **Visual Indicators**: Emoji + text prefix
   - 🔧 Dev (safe to experiment)
   - 🧪 Staging (test environment)
   - ⚠️ PROD (production warning)

---

## 📖 Doctrine Reference

For the complete operating doctrine, see the problem statement that guided this implementation:
- Homepage = Read-only observation layer
- Grafana = Understanding layer
- Alertmanager = Interruption layer
- CI/CD = Mutation layer (only place changes happen)
- Humans = Decision layer

**Key Rule:** Homepage must remain read-only forever.

---

## 🎯 Transformation Plan Available

Additional enhancement plans are available in `/docs` (not required for doctrine compliance):

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

**Note:** These plans are for advanced features beyond doctrine requirements (system metrics widgets, etc.)

---

## 📂 Directory Structure

```
homepage/
├── assets/
│   ├── TutorDex-logo-1024.png  # Logo for favicon/branding
│   └── README.txt
├── config/
│   ├── services.yaml            # Service links (doctrine-compliant structure)
│   ├── settings.yaml            # Theme, layout config
│   ├── widgets.yaml             # System metrics (Prometheus)
│   ├── bookmarks.yaml           # Optional bookmarks
│   ├── docker.yaml              # Docker integration (optional)
│   ├── kubernetes.yaml          # K8s integration (not used)
│   └── proxmox.yaml             # Proxmox integration (not used)
└── README.md                    # This file
```

---

## 🔧 Current Configuration

### services.yaml (Doctrine-Compliant)
- **Environment-first grouping**: Dev → Staging → Prod
- **Intent-based sections**: Core Platform, Data & Identity, Observability, Bots
- **Read-only**: All links, no actions/triggers/mutations
- **Visual clarity**: Emoji prefixes for instant environment recognition

### settings.yaml
- Dark theme (slate color scheme)
- Layout configuration matching doctrine structure
- Quick launch enabled for fast navigation

### widgets.yaml
- Prometheus integration for system metrics
- CPU, Memory, Disk usage queries
- Read-only metrics display

### Docker Compose
```yaml
homepage:
  image: ghcr.io/gethomepage/homepage:latest
  ports:
    - "0.0.0.0:${HOMEPAGE_PORT:-7575}:3000"
  volumes:
    - ./homepage/config:/app/config:ro         # Read-only config
    - ./homepage/assets:/app/public/assets:ro  # Read-only assets
    - /var/run/docker.sock:/var/run/docker.sock:ro  # Read-only Docker socket
  environment:
    TZ: Asia/Singapore
    HOMEPAGE_ALLOWED_HOSTS: "localhost:7575,127.0.0.1:7575,[::1]:7575,homepage.taildbd593.ts.net"
```

**Security:** All volumes and Docker socket mounted read-only (`:ro`)

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
