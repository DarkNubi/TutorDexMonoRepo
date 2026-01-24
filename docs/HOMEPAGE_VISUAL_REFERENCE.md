# Homepage.dev Dashboard - Visual Reference

> **ASCII mockup of the target dashboard layout**  
> Use this to visualize the end result before implementation

---

```
╔════════════════════════════════════════════════════════════════════════════╗
║                     TUTORDEX INFRASTRUCTURE DASHBOARD                       ║
║                          [TutorDex Logo] 🔴 3 ALERTS                        ║
╚════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────┐
│ SYSTEM HEALTH                                                   [mdi-server] │
├─────────────┬─────────────┬─────────────┬─────────────┐
│   CPU       │   MEMORY    │    DISK     │   UPTIME    │
│  ┌───────┐  │  ┌───────┐  │  ┌───────┐  │  ┌───────┐  │
│  │ 45.2% │  │  │ 62.1% │  │  │ 73.5% │  │  │ 7d 3h │  │
│  └───────┘  │  └───────┘  │  └───────┘  │  └───────┘  │
│   [green]   │   [amber]   │   [amber]   │             │
└─────────────┴─────────────┴─────────────┴─────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ DOCKER CONTAINERS                                               [docker icon] │
├──────────────────────────────────────────────────────────────────────────┤
│  ✅ 15 Running  ❌ 0 Stopped  ⚠️ 1 Unhealthy  (16 total)                │
│                                                                          │
│  ✅ backend            ✅ collector-tail      ✅ aggregator-worker      │
│  ✅ grafana            ✅ prometheus          ✅ alertmanager           │
│  ✅ redis              ⚠️ telegram-link-bot   ✅ freshness-tiers        │
│  ✅ cadvisor           ✅ node-exporter       ✅ blackbox-exporter      │
│  ✅ tempo              ✅ otel-collector      ✅ homepage               │
│  ✅ tutorcity-fetch    ✅ alertmanager-telegram                         │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ OBSERVABILITY                                             [mdi-chart-line] │
├─────────────────────┬─────────────────────┬─────────────────────┐
│    GRAFANA          │    PROMETHEUS       │   ALERTMANAGER      │
│   [grafana icon]    │  [prometheus icon]  │    [mdi-bell]       │
│                     │                     │                     │
│  📊 Dashboard UI    │  📈 Metrics Store   │  🔔 Alert Routing   │
│  http://...:3300    │  http://...:9090    │  http://...:9093    │
│                     │                     │                     │
│  🟢 Healthy         │  🟢 Healthy         │  🔴 3 Active        │
│  23ms               │  12ms               │     Alerts          │
└─────────────────────┴─────────────────────┴─────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ CORE SERVICES                                          [mdi-application] │
├────────────────────────────────┬────────────────────────────────┐
│       BACKEND API              │           REDIS                │
│      [mdi-api icon]            │    [mdi-database icon]         │
│                                │                                │
│  🔧 FastAPI + Swagger          │  💾 Cache & Sessions           │
│  http://localhost:8000/docs    │  Internal (no direct UI)       │
│                                │                                │
│  🟢 Healthy                    │  🟢 Running                    │
│  45ms (last check)             │  (via Backend health)          │
└────────────────────────────────┴────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ DATA & STORAGE                                            [mdi-database] │
├──────────────────────────────────────────────────────────────────────────┤
│  📊 SUPABASE (PostgreSQL)                                                │
│     https://prod-supabase.taildbd593.ts.net                              │
│     Primary database for assignments, users, analytics                   │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ PIPELINE HEALTH                                            [mdi-pipeline] │
├────────────────────────────────┬────────────────────────────────┐
│   COLLECTOR STALENESS          │    WORKER QUEUE DEPTH          │
│                                │                                │
│  Last message: 47s ago         │  Pending: 23 jobs              │
│  🟢 Healthy (<5m)              │  🟡 Warning (>20 jobs)         │
│                                │                                │
│  Channels: 8 active            │  Processing: 2 jobs            │
│  Rate: 0.8 msg/s               │  Throughput: 1.2 jobs/s        │
└────────────────────────────────┴────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ EXTERNAL / CONTROL PLANE                                      [mdi-web] │
├──────────────────────────────────────────────────────────────────────────┤
│  🌐 TutorDex Website (Public)                                            │
│     https://tutordex.web.app                                             │
│                                                                          │
│  📦 GitHub Repository                                                    │
│     https://github.com/DarkNubi/TutorDexMonoRepo                         │
└──────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────┐
│ ▼ REMOTE ENVIRONMENTS (Click to expand)                     [mdi-cloud] │
└──────────────────────────────────────────────────────────────────────────┘
  (Collapsed by default - contains Staging and Production links)
```

---

## Color Palette (Dark Theme)

```
Background:      #0a0e1a (very dark blue-grey)
Card Background: #1a1f2e (dark blue-grey, slightly lighter)
Card Border:     #2a2f3e (subtle border)
Text Primary:    #f0f0f0 (off-white)
Text Secondary:  #9ca3af (light grey)
Accent:          #60a5fa (blue)

Status Colors:
  🟢 Healthy:    #22c55e (green)
  🟡 Warning:    #fbbf24 (amber)
  🔴 Critical:   #ef4444 (red)
  🔵 Info:       #3b82f6 (blue)
```

---

## Layout Grid

```
┌─────────────────────────────────────────────┐
│ Header (Full Width)                          │
│ - Logo + Title + Alert Badge                 │
└─────────────────────────────────────────────┘

┌──────┬──────┬──────┬──────┐
│ CPU  │ RAM  │ Disk │Uptime│  ← 4 columns (equal width)
└──────┴──────┴──────┴──────┘

┌────────────────────────────────────────────┐
│ Docker Containers (Full Width Card)        │  ← Single wide card
│ - Auto-height based on container count     │
└────────────────────────────────────────────┘

┌──────────┬──────────┬──────────┐
│ Grafana  │Prometheus│Alertmgr  │  ← 3 columns (equal width)
└──────────┴──────────┴──────────┘

┌──────────────────┬──────────────────┐
│ Backend API      │ Redis            │  ← 2 columns (equal width)
└──────────────────┴──────────────────┘

┌────────────────────────────────────────────┐
│ Supabase (Full Width Link)                 │  ← Single wide card
└────────────────────────────────────────────┘

┌──────────────────┬──────────────────┐
│ Collector        │ Worker Queue     │  ← 2 columns (equal width)
└──────────────────┴──────────────────┘

┌────────────────────────────────────────────┐
│ External Links (Full Width)                │  ← Single wide section
│ - Website + GitHub                          │
└────────────────────────────────────────────┘

┌────────────────────────────────────────────┐
│ ▼ Remote Environments (Collapsed)          │  ← Accordion/Collapsible
└────────────────────────────────────────────┘
```

---

## Responsive Behavior

**Desktop (>1280px):**
- 4-column grid for System Health
- 3-column grid for Observability
- 2-column grid for Core Services
- Full-width for Docker/Data/Pipeline

**Tablet (768px - 1280px):**
- 2-column grid for most sections
- Stack vertically for narrow sections

**Mobile (<768px):**
- Single column (all cards stack)
- Collapsible sections by default

---

## Widget Behavior Examples

### Metric Widget (CPU Usage)
```
┌─────────────┐
│   CPU       │
│  ┌───────┐  │
│  │ 45.2% │  │  ← Large number (2rem font)
│  └───────┘  │
│   [████░]   │  ← Progress bar (green/amber/red)
│  Healthy    │  ← Status text (small)
└─────────────┘
```

### Service Link + Status Widget
```
┌─────────────────┐
│   GRAFANA       │
│  [grafana icon] │
│                 │
│  Dashboard UI   │  ← Description
│  localhost:3300 │  ← URL (clickable)
│                 │
│  🟢 Healthy     │  ← Status (from ping widget)
│  23ms           │  ← Response time
└─────────────────┘
```

### Docker Container List Widget
```
┌──────────────────────────────────────┐
│ DOCKER CONTAINERS                    │
├──────────────────────────────────────┤
│  ✅ 15 Running  ❌ 0 Stopped  ⚠️ 1 Unhealthy │
│                                      │
│  ✅ backend         (healthy)        │  ← Status icon + name + state
│  ✅ collector-tail  (healthy)        │
│  ⚠️ telegram-link-bot (degraded)    │  ← Unhealthy highlighted
│  ...                                 │
└──────────────────────────────────────┘
```

### Prometheus Custom Metric Widget
```
┌─────────────────┐
│ QUEUE DEPTH     │
│                 │
│    23 jobs      │  ← Value from Prometheus query
│  🟡 Warning     │  ← Threshold-based status
│                 │
│  Target: <20    │  ← Context
└─────────────────┘
```

---

## Interaction Design

### On Page Load
1. System Health widgets load first (fastest)
2. Docker widget loads second (local socket)
3. Service status widgets load asynchronously
4. Prometheus widgets load last (query execution)

### Auto-Refresh Intervals
- **System Health:** 5 seconds
- **Docker Containers:** 10 seconds
- **Service Status (Ping):** 30 seconds
- **Prometheus Metrics:** 30 seconds
- **Alert Count:** 30 seconds

### Click Behavior
- **Service cards:** Click anywhere to open service URL (new tab)
- **Container names:** Click to view container logs (if supported)
- **Metric cards:** Click to open Prometheus query (if applicable)
- **Alert badge:** Click to open Alertmanager

### Collapsed Sections
- **Remote Environments:** Collapsed by default
- **Click header** to expand/collapse
- **State persists** in localStorage

---

## Accessibility Notes

- **High contrast:** Dark theme with sufficient contrast ratios
- **Color + Icon:** Status indicated by both color AND icon (not color alone)
- **Keyboard navigation:** All links and buttons keyboard-accessible
- **Screen reader friendly:** Proper semantic HTML and ARIA labels
- **Focus indicators:** Visible focus states on all interactive elements

---

## Performance Expectations

**Page Load:**
- Initial render: <1s
- All widgets populated: <3s

**Widget Refresh:**
- System metrics: <100ms
- Docker status: <200ms
- Prometheus queries: <500ms

**Resource Usage (Homepage Container):**
- CPU: <5% idle, <15% during refresh
- Memory: <100MB
- Network: <1KB/s average

---

## Comparison: Before vs After

### Before (Current State)
```
┌─────────────────────────────────────┐
│ STAGING                              │
│  > Grafana (Staging) [link]         │
│  > Prometheus (Staging) [link]      │
│  > Alertmanager (Staging) [link]    │
│  > Supabase (Staging) [link]        │
│                                      │
│ PRODUCTION                           │
│  > Grafana (Production) [link]      │
│  > Prometheus (Production) [link]   │
│  > Alertmanager (Production) [link] │
│  > Supabase (Production) [link]     │
│                                      │
│ RESOURCES                            │
│  > TutorDex Website [link]          │
│  > GitHub Repository [link]         │
└─────────────────────────────────────┘
```

**Characteristics:**
- Links only, no widgets
- Remote services only
- No local visibility
- No health indicators
- Light/default theme

### After (Target State)
```
┌─────────────────────────────────────────────┐
│ [LOGO] TUTORDEX INFRASTRUCTURE  🔴 3 ALERTS │
│                                              │
│ [CPU] [RAM] [DISK] [UPTIME]                 │
│ 45%   62%   73%    7d 3h                    │
│                                              │
│ DOCKER: ✅ 15 Running ⚠️ 1 Unhealthy        │
│                                              │
│ [GRAFANA🟢] [PROMETHEUS🟢] [ALERTMANAGER🔴] │
│                                              │
│ [BACKEND🟢] [REDIS🟢]                       │
│                                              │
│ SUPABASE [link]                             │
│                                              │
│ PIPELINE: Collector 47s | Queue 23 jobs     │
│                                              │
│ EXTERNAL: Website | GitHub                  │
│                                              │
│ ▼ Remote Environments (collapsed)           │
└─────────────────────────────────────────────┘
```

**Characteristics:**
- Rich widgets with live data
- Local services prominent
- Container visibility
- Health at-a-glance
- Dark cinematic theme
- Alert awareness

---

## Implementation Notes

This visual reference is **descriptive, not prescriptive**. Homepage.dev will handle:
- Actual card rendering
- Responsive breakpoints
- Animation/transitions
- Widget data fetching

Your job as executor:
- Configure `settings.yaml` for theme/layout
- Configure `widgets.yaml` for widget data sources
- Configure `services.yaml` for links and groupings
- Mount Docker socket for container visibility

The visual above shows the **goal state** after following the executor checklist in `HOMEPAGE_DASHBOARD_PLAN.md`.

---

**For implementation, see:** [HOMEPAGE_DASHBOARD_PLAN.md](HOMEPAGE_DASHBOARD_PLAN.md)  
**For quick start, see:** [HOMEPAGE_QUICK_START.md](HOMEPAGE_QUICK_START.md)
