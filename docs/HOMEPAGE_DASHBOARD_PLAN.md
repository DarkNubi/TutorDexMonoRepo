# Homepage.dev Infrastructure Dashboard — Transformation Plan

**Document Type:** Planning Blueprint (Execution-Ready)  
**Target:** Transform plain Homepage.dev into high-signal, cinematic SRE control panel  
**Date:** 2026-01-24  
**Status:** Ready for Execution

---

## Executive Summary

This document provides a complete, execution-ready plan to transform the TutorDex Homepage.dev dashboard from a basic link directory into a professional, single-pane-of-glass operational control panel. The plan is designed to be followed mechanically by an execution agent without requiring additional design decisions.

**Current State:** Homepage.dev is functional but minimal — only `services.yaml` with external Tailscale links to staging and production environments. No widgets, no system metrics, no visual polish.

**End State:** A dark, cinematic, high-density dashboard that immediately communicates system health and provides fast navigation to relevant observability tools.

---

## Table of Contents

1. [Current State Report](#1-current-state-report)
2. [Surface Area Mapping](#2-surface-area-mapping)
3. [Recommended Signal Map](#3-recommended-signal-map)
4. [Dashboard Blueprint](#4-dashboard-blueprint)
5. [Aesthetic Implementation Plan](#5-aesthetic-implementation-plan)
6. [Executor Checklist](#6-executor-checklist)

---

## 1. Current State Report

### 1.1 Homepage.dev Setup

**Docker Configuration:**
- Service: `homepage` in root `docker-compose.yml` (lines 335-349)
- Image: `ghcr.io/gethomepage/homepage:latest`
- Port: `0.0.0.0:${HOMEPAGE_PORT:-7575}:3000`
- Access: `http://localhost:7575` or `https://homepage.taildbd593.ts.net`

**Mounted Volumes:**
```yaml
- ./homepage/config:/app/config:ro
- ./homepage/assets:/app/public/assets:ro
```

**Configuration Files Present:**
- ✅ `homepage/config/services.yaml` (3.3KB, 93 lines)
- ❌ `settings.yaml` (missing — using Homepage.dev defaults)
- ❌ `widgets.yaml` (missing — no system/Docker widgets enabled)
- ❌ `bookmarks.yaml` (missing)
- ❌ Custom CSS/JS (not present)

**Assets:**
- `homepage/assets/TutorDex-logo-1024.png` (175KB logo)
- `homepage/assets/README.txt`

**Docker Label Auto-Discovery:**
- Not enabled (no evidence in docker-compose.yml of homepage labels)

### 1.2 Current Dashboard Inventory

**Services Shown:**
```
Staging
├── Observability
│   ├── Grafana (Staging) → https://staging-grafana.taildbd593.ts.net
│   ├── Prometheus (Staging) → https://staging-prometheus.taildbd593.ts.net
│   └── Alertmanager (Staging) → https://staging-alertmanager.taildbd593.ts.net
└── Data & Storage
    ├── Supabase (Staging) → https://staging-supabase.taildbd593.ts.net
    └── Logflare (Staging) → https://staging-logflare.taildbd593.ts.net

Production
├── Observability
│   ├── Grafana (Production) → https://prod-grafana.taildbd593.ts.net
│   ├── Prometheus (Production) → https://prod-prometheus.taildbd593.ts.net
│   └── Alertmanager (Production) → https://prod-alertmanager.taildbd593.ts.net
└── Data & Storage
    ├── Supabase (Production) → https://prod-supabase.taildbd593.ts.net
    └── Logflare (Production) → https://prod-logflare.taildbd593.ts.net

Resources
├── TutorDex Website → https://tutordex.web.app
└── GitHub Repository → https://github.com/DarkNubi/TutorDexMonoRepo
```

**Characteristics:**
- All links are external HTTPS (Tailscale Serve endpoints)
- Environment segregation (Staging vs Production)
- Minimal descriptions (icon + emoji + short text)
- No widgets or metrics
- No local Docker container visibility

**Missing Capabilities:**
- ❌ System health at-a-glance
- ❌ Docker container status/health
- ❌ Host metrics (CPU, RAM, disk, uptime)
- ❌ Alert summary (current firing alerts)
- ❌ Service status indicators
- ❌ Quick navigation to local services
- ❌ Visual polish (dark theme, glassmorphism)

---

## 2. Surface Area Mapping

### 2.1 Complete Service Inventory

From `docker-compose.yml`, the TutorDex stack consists of 17 services:

#### **Infrastructure / Observability** (7 services)
| Service | Port | Importance | Operator Relevance | Notes |
|---------|------|------------|-------------------|-------|
| `prometheus` | 9090 | **CRITICAL** | High | Primary metrics store; must be healthy |
| `grafana` | 3300 | **CRITICAL** | High | Primary dashboard UI; most-accessed tool |
| `alertmanager` | 9093 | **CRITICAL** | High | Alert routing; shows firing alerts |
| `alertmanager-telegram` | - | CRITICAL | Medium | Alert delivery; failure is invisible but critical |
| `tempo` | 3200, 4317, 4318 | Supporting | Medium | Tracing backend (optional in local) |
| `otel-collector` | - | Supporting | Low | Telemetry pipeline; errors appear in service logs |
| `blackbox-exporter` | - | Supporting | Low | HTTP probing; used by Prometheus |

#### **Data / Persistence** (2 services)
| Service | Port | Importance | Operator Relevance | Notes |
|---------|------|------------|-------------------|-------|
| `redis` | - | **CRITICAL** | Medium | Tutor preferences, link codes, cooldown cache |
| External: Supabase | - | **CRITICAL** | High | PostgreSQL; all persistent data; accessed via Tailscale |

#### **Application / Workers** (5 services)
| Service | Port | Importance | Operator Relevance | Notes |
|---------|------|------------|-------------------|-------|
| `collector-tail` | - | **CRITICAL** | High | Telegram message ingestion; staleness = pipeline down |
| `aggregator-worker` | - | **CRITICAL** | High | LLM extraction worker; queue health critical |
| `backend` | 8000 | **CRITICAL** | High | FastAPI; serves website + DM bot |
| `telegram-link-bot` | - | CRITICAL | Medium | DM linking bot; users notice if down |
| `freshness-tiers` | - | Supporting | Low | Hourly assignment lifecycle; failure is low-impact |
| `tutorcity-fetch` | - | Supporting | Low | External API polling (5min interval) |

#### **Host / Container Monitoring** (2 services)
| Service | Port | Importance | Operator Relevance | Notes |
|---------|------|------------|-------------------|-------|
| `cadvisor` | - | Supporting | Medium | Docker container metrics; scraped by Prometheus |
| `node-exporter` | - | Supporting | Medium | Host metrics (CPU, RAM, disk); scraped by Prometheus |

#### **Dashboard** (1 service)
| Service | Port | Importance | Operator Relevance | Notes |
|---------|------|------------|-------------------|-------|
| `homepage` | 7575 | Supporting | **SELF** | This service; must always work |

### 2.2 Categorization & Visibility Strategy

**Always Visible (Top Priority):**
- System health summary (CPU, RAM, disk, uptime)
- Docker container health (running/stopped/unhealthy)
- Active alerts count (Alertmanager)
- Grafana (most-used tool)
- Backend health (serves website)

**Secondary Visibility (Important but not top-of-mind):**
- Prometheus, Alertmanager (observability tools)
- Supabase (critical but accessed less frequently)
- Collector, Worker (pipeline health via metrics, not direct access)
- Redis (critical but invisible; health via backend metrics)

**Should Remain Hidden (Low Operator Value):**
- `otel-collector`, `tempo` (tracing; optional, low-traffic)
- `cadvisor`, `node-exporter` (scraped by Prometheus; no direct UI)
- `blackbox-exporter` (probe backend; no UI)
- `alertmanager-telegram` (no UI; health via alert delivery)
- `freshness-tiers`, `tutorcity-fetch` (background jobs; errors appear in logs/metrics)

---

## 3. Recommended Signal Map

This table defines what information should be visible and from where:

| Signal | Source | Visibility | Widget Type | Rationale |
|--------|--------|-----------|-------------|-----------|
| **Host CPU Usage** | node-exporter → Prometheus | Always | Gauge + Graph | First indicator of system overload |
| **Host Memory Usage** | node-exporter → Prometheus | Always | Gauge + Graph | Critical for Docker stability |
| **Host Disk Usage** | node-exporter → Prometheus | Always | Gauge | Disk full = catastrophic failure |
| **System Uptime** | node-exporter → Prometheus | Always | Text | Context for incident timing |
| **Container Health** | Docker Socket | Always | List | Instant visibility of failed containers |
| **Active Alerts** | Alertmanager API | Always | Badge/Count | Immediate attention required |
| **Grafana Status** | Docker health + HTTP probe | Always | Link + Badge | Most-accessed tool |
| **Backend API Health** | HTTP probe | Always | Link + Badge | Serves website; high-priority |
| **Prometheus Status** | Docker health | Secondary | Link + Badge | Observability foundation |
| **Alertmanager Status** | Docker health | Secondary | Link + Badge | Alert routing |
| **Supabase Status** | External link | Secondary | Link | Accessed less frequently |
| **Collector Pipeline** | Prometheus metrics | Secondary | Metric | Ingestion health |
| **Worker Queue Health** | Prometheus metrics | Secondary | Metric | Extraction pipeline |
| **Redis Status** | Docker health | Hidden (inferred) | None | Monitored via backend health |

### Signal Priority Tiers

**Tier 1 — Always Visible (System Health):**
- Host metrics (CPU, RAM, Disk, Uptime)
- Container health (Docker)
- Active alerts (Alertmanager)

**Tier 2 — Primary Services:**
- Grafana (link + widget)
- Backend (link + widget)
- Prometheus (link + widget)
- Alertmanager (link + widget)

**Tier 3 — Data & External:**
- Supabase (link)
- TutorDex Website (link)
- GitHub (link)

**Tier 4 — Staging/Prod Remote:**
- Keep existing staging/prod links (accordion/collapse)

---

## 4. Dashboard Blueprint

### 4.1 Section Order (Top → Bottom)

```
┌─────────────────────────────────────────────────────┐
│ [Header: TutorDex Infrastructure Dashboard]        │
│ [Logo + System-wide Alert Badge]                   │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 1: System Health                           │
│ • Host CPU Widget                                  │
│ • Host Memory Widget                               │
│ • Host Disk Widget                                 │
│ • System Uptime Widget                             │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 2: Docker Containers                       │
│ • Container Status Widget (auto-discovery)         │
│ • Shows: running/stopped/unhealthy counts          │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 3: Observability                           │
│ • Grafana (link + status widget)                   │
│ • Prometheus (link + status widget)                │
│ • Alertmanager (link + alert count widget)         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 4: Core Services                           │
│ • Backend API (link + health widget)               │
│ • Redis (link + status widget)                     │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 5: Data & Storage                          │
│ • Supabase (link)                                  │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 6: Pipeline Health                         │
│ • Collector Staleness (Prometheus custom widget)   │
│ • Worker Queue Depth (Prometheus custom widget)    │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 7: External / Control Plane                │
│ • TutorDex Website (public)                        │
│ • GitHub Repository                                │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│ SECTION 8: Remote Environments (Collapsed)         │
│ • Staging (Grafana, Prometheus, Alertmanager, etc) │
│ • Production (Grafana, Prometheus, etc)            │
└─────────────────────────────────────────────────────┘
```

### 4.2 Section Rationale

**Section 1 (System Health):**
- **Why top:** If the host is unhealthy, everything else is irrelevant
- **What to show:** CPU/RAM/Disk/Uptime — minimal, high-density widgets
- **Bad state visibility:** Red/amber thresholds; visual alarm

**Section 2 (Docker Containers):**
- **Why second:** Container crashes are the most common failure mode
- **What to show:** Auto-discovered container list with health status
- **Bad state visibility:** Red for stopped/unhealthy; green for healthy

**Section 3 (Observability):**
- **Why third:** After confirming system/container health, operator goes here
- **What to show:** Grafana (most-used), Prometheus (data source), Alertmanager (active alerts)
- **Bad state visibility:** Alert count badge; container health icon

**Section 4 (Core Services):**
- **Why fourth:** Application-layer health checks
- **What to show:** Backend (serves website), Redis (cache/state)
- **Bad state visibility:** Health endpoint status + response time

**Section 5 (Data & Storage):**
- **Why fifth:** Database accessed less frequently; mostly via application
- **What to show:** Link to Supabase dashboard
- **Bad state visibility:** None (external; monitored via Prometheus blackbox probe)

**Section 6 (Pipeline Health):**
- **Why sixth:** Specialized metrics for operators debugging pipeline issues
- **What to show:** Custom Prometheus queries (collector staleness, queue depth)
- **Bad state visibility:** Threshold-based color coding

**Section 7 (External / Control Plane):**
- **Why seventh:** Public website and source code
- **What to show:** TutorDex website (public), GitHub repo
- **Bad state visibility:** None (external)

**Section 8 (Remote Environments):**
- **Why last (collapsed):** Different environments; not relevant to local ops
- **What to show:** Keep existing staging/production links
- **Bad state visibility:** None (external)

---

## 5. Aesthetic Implementation Plan

### 5.1 settings.yaml Changes

**File:** `homepage/config/settings.yaml`

**Required Settings:**

```yaml
# Theme & Visual
title: TutorDex Infrastructure
favicon: /assets/TutorDex-logo-1024.png
theme: dark
color: slate
background:
  image: /assets/background.jpg  # Optional: dark, subtle grid/topology pattern
  blur: sm  # Subtle background blur
  opacity: 30  # Dim background to emphasize cards

# Layout
layout:
  Observability:
    style: row
    columns: 3
  "Core Services":
    style: row
    columns: 2
  "System Health":
    style: row
    columns: 4

# Density & Spacing
cardBlur: sm  # Subtle glassmorphism effect
hideVersion: true  # Cleaner footer
quicklaunch:
  searchDescriptions: true
  hideInternetSearch: true

# Localization
language: en
locale: en-SG
timezone: Asia/Singapore

# Feature Flags
headerStyle: boxed
hideErrors: false  # Show errors for debugging
showStats: true  # Enable stats for widgets

# Custom CSS (if needed)
# customCss: |
#   Additional overrides for card spacing, font sizes, etc.
```

### 5.2 Background & Theme Strategy

**Goal:** Match reference image's dark, cinematic, high-density aesthetic

**Background Options:**
1. **Option A (Recommended):** Subtle dark grid/topology pattern
   - Source: Generate or use a dark SVG/PNG with faint lines
   - Color: Dark blue-grey (#0a0e1a to #1a1f2e)
   - Pattern: Faint hexagonal grid or network topology
   - File: `homepage/assets/background.jpg` or `.png`

2. **Option B (Fallback):** Solid dark gradient
   - Pure CSS gradient via customCss
   - No external image needed

3. **Option C (Minimal):** Solid dark color
   - Use Homepage.dev's default dark theme background
   - Simplest option; no custom assets

**Recommendation:** Start with **Option C** (solid dark), then optionally add **Option A** if desired.

**Theme Settings:**
- **Theme:** `dark` (Homepage.dev built-in dark mode)
- **Color:** `slate` (grey-blue palette; matches cinematic aesthetic)
- **Card Blur:** `sm` (subtle glassmorphism; not heavy)
- **Background Opacity:** `30` (dim background, emphasize cards)

### 5.3 Card & Widget Styling Philosophy

**Visual Principles:**
1. **Consistent Card Heights:** Widgets in the same row should align
2. **Icon Prominence:** Use recognizable icons (mdi, fontawesome, brand icons)
3. **Metric > Labels:** Show numbers prominently; labels secondary
4. **Visual Rhythm:** Even spacing, aligned columns, predictable grid

**Specific Rules:**
- **System Health Widgets (Section 1):** Small, compact, 4-column grid
- **Observability Links (Section 3):** 3-column grid, with status widgets
- **Remote Environments (Section 8):** Initially collapsed accordion

**Widget Type Selection:**
- **Glances Widget:** For host metrics (CPU, RAM, Disk, Uptime) via node-exporter
- **Docker Widget:** For container health (auto-discovers running containers)
- **Prometheus Widget:** For custom metrics (collector staleness, queue depth)
- **Ping Widget:** For HTTP health checks (Backend, Grafana, Prometheus)

### 5.4 Visual Hierarchy

**What the eye should hit first:**
1. **Alert Badge (if any):** Bright red/amber indicator at top
2. **System Health Metrics:** CPU/RAM/Disk gauges (color-coded: green/amber/red)
3. **Container Health:** Count of unhealthy containers (red if > 0)
4. **Grafana Link:** Most-used tool; prominent position

**What fades into the background:**
- Section headers (subtle, not bold)
- Descriptions (small grey text)
- Remote environment links (collapsed accordion)

**How to prevent clutter despite density:**
- Use collapsible sections for less-accessed content
- Limit descriptions to <10 words
- Use icons instead of text where possible
- Consistent spacing between sections (rely on Homepage.dev's grid)

### 5.5 Custom CSS / JS (If Needed)

**When Homepage.dev defaults are sufficient:**
- Theme, layout, and widget configuration can achieve 90% of the goal
- Custom CSS only needed for fine-tuning (font sizes, card spacing tweaks)

**When Custom CSS is required:**
- Adjust card padding/margins for tighter density
- Modify font sizes for better hierarchy
- Override default colors for specific states (e.g., red alerts)
- Add subtle shadow effects for depth

**Scope of Custom CSS (if implemented):**
```yaml
# In settings.yaml:
customCss: |
  /* Tighter card spacing */
  .service-card {
    padding: 0.75rem !important;
  }
  
  /* Metric prominence */
  .widget-value {
    font-size: 2rem !important;
    font-weight: 700 !important;
  }
  
  /* Alert badge emphasis */
  .alert-count {
    color: #ef4444 !important;
  }
```

**Recommendation:** Start without custom CSS; add only if defaults feel off.

---

## 6. Executor Checklist

This is a dependency-ordered, mechanical implementation checklist. Follow each step sequentially.

### Phase 1: Preparation & Baseline

- [ ] **1.1** Backup current homepage config
  ```bash
  cp -r homepage/config homepage/config.backup
  ```

- [ ] **1.2** Verify Homepage.dev container is running
  ```bash
  docker compose ps homepage
  docker compose logs homepage --tail 50
  ```

- [ ] **1.3** Test current homepage access
  - Open `http://localhost:7575` in browser
  - Verify staging/production links work
  - Take screenshot for comparison

### Phase 2: Create settings.yaml

- [ ] **2.1** Create `homepage/config/settings.yaml` with base structure
  ```yaml
  title: TutorDex Infrastructure
  favicon: /assets/TutorDex-logo-1024.png
  theme: dark
  color: slate
  headerStyle: boxed
  hideVersion: true
  language: en
  locale: en-SG
  timezone: Asia/Singapore
  ```

- [ ] **2.2** Add layout configuration for sections
  ```yaml
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
  ```

- [ ] **2.3** Test settings.yaml loads correctly
  ```bash
  docker compose restart homepage
  docker compose logs homepage --tail 20
  # Check browser for theme changes
  ```

### Phase 3: Create widgets.yaml (System Health)

- [ ] **3.1** Create `homepage/config/widgets.yaml` with Glances widget
  ```yaml
  - resources:
      backend: http://host.docker.internal:61208
      expanded: true
      cpu: true
      memory: true
      disk:
        - /
      uptime: true
  ```
  **Note:** Requires Glances running on host. If not available, use node-exporter Prometheus queries instead.

- [ ] **3.2** Alternative: Add Prometheus widgets for system metrics
  ```yaml
  - prometheus:
      href: http://prometheus:9090
      metrics:
        - label: CPU Usage
          query: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
          suffix: "%"
        - label: Memory Usage
          query: 100 - ((node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100)
          suffix: "%"
        - label: Disk Usage
          query: 100 - ((node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100)
          suffix: "%"
  ```

- [ ] **3.3** Test widgets appear
  ```bash
  docker compose restart homepage
  # Check browser for system metrics
  ```

### Phase 4: Enhance services.yaml (Reorder + Add Widgets)

- [ ] **4.1** Add "System Health" section at top of services.yaml
  ```yaml
  - System Health:
      - icon: mdi-server
      - Host Metrics:
          # Widget reference (actual widget in widgets.yaml)
  ```

- [ ] **4.2** Add "Docker Containers" section with Docker widget
  ```yaml
  - Docker Containers:
      - icon: docker
      - Containers:
          widget:
            type: docker
            url: unix:///var/run/docker.sock  # Requires socket mount
  ```
  **Note:** Requires adding Docker socket mount to docker-compose.yml:
  ```yaml
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock:ro
  ```

- [ ] **4.3** Reorder existing sections:
  - Keep "Observability" section (rename from "Staging > Observability")
  - Update Grafana link to local: `http://localhost:3300`
  - Update Prometheus link to local: `http://localhost:9090`
  - Update Alertmanager link to local: `http://localhost:9093`

- [ ] **4.4** Add status widgets to Observability services
  ```yaml
  - Grafana:
      icon: grafana
      href: http://localhost:3300
      description: Metrics visualization and dashboards
      target: _blank
      widget:
        type: ping
        url: http://grafana:3000
  ```

- [ ] **4.5** Add "Core Services" section
  ```yaml
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
      - Redis:
          icon: mdi-database-outline
          description: Cache and session store
          widget:
            type: docker
            container: redis
  ```

- [ ] **4.6** Add "Data & Storage" section
  ```yaml
  - Data & Storage:
      - icon: mdi-database
      - Supabase:
          icon: mdi-database
          href: https://prod-supabase.taildbd593.ts.net
          description: PostgreSQL database and admin
          target: _blank
  ```

- [ ] **4.7** Add "Pipeline Health" section with Prometheus widgets
  ```yaml
  - Pipeline Health:
      - icon: mdi-pipeline
      - Collector Staleness:
          widget:
            type: prometheus
            href: http://prometheus:9090
            query: tutordex:collector:seconds_since_last_message
            suffix: "s ago"
      - Worker Queue Depth:
          widget:
            type: prometheus
            href: http://prometheus:9090
            query: tutordex_worker_queue_pending_jobs
            suffix: " jobs"
  ```

- [ ] **4.8** Add "External / Control Plane" section
  ```yaml
  - External:
      - icon: mdi-web
      - TutorDex Website:
          icon: mdi-home
          href: https://tutordex.web.app
          description: Public tutor assignment portal
          target: _blank
      - GitHub Repository:
          icon: mdi-github
          href: https://github.com/DarkNubi/TutorDexMonoRepo
          description: Source code and documentation
          target: _blank
  ```

- [ ] **4.9** Move staging/production to collapsed accordion at bottom
  ```yaml
  - Remote Environments:
      - icon: mdi-cloud
      - Staging:
          # Keep existing staging links
      - Production:
          # Keep existing production links
  ```

### Phase 5: Docker Socket Access (for Container Widget)

- [ ] **5.1** Update docker-compose.yml homepage service to mount Docker socket
  ```yaml
  homepage:
    # ... existing config ...
    volumes:
      - ./homepage/config:/app/config:ro
      - ./homepage/assets:/app/public/assets:ro
      - /var/run/docker.sock:/var/run/docker.sock:ro  # ADD THIS LINE
  ```

- [ ] **5.2** Restart homepage with new volume mount
  ```bash
  docker compose up -d homepage
  ```

- [ ] **5.3** Verify Docker widget shows containers
  - Check browser for container list
  - Verify running/stopped status indicators

### Phase 6: Optional Glances Setup (for System Metrics)

**If using Glances widget (recommended):**

- [ ] **6.1** Install Glances on host
  ```bash
  # Ubuntu/Debian:
  sudo apt install glances
  # macOS:
  brew install glances
  # Python:
  pip install glances
  ```

- [ ] **6.2** Start Glances in server mode
  ```bash
  glances -w  # Web server mode on port 61208
  # OR
  glances -w --port 61208 &  # Background
  ```

- [ ] **6.3** Update widgets.yaml Glances backend URL
  ```yaml
  - resources:
      backend: http://host.docker.internal:61208
      # ... rest of config ...
  ```

- [ ] **6.4** Test Glances widget shows metrics

**If NOT using Glances:**
- Skip to using Prometheus widgets for system metrics (already covered in 3.2)

### Phase 7: Background Image (Optional)

**If adding custom background:**

- [ ] **7.1** Create or download dark background image
  - Recommended: Dark grid/topology pattern
  - Size: 1920x1080 or larger
  - Format: PNG or JPEG
  - File: `homepage/assets/background.jpg`

- [ ] **7.2** Update settings.yaml with background config
  ```yaml
  background:
    image: /assets/background.jpg
    blur: sm
    opacity: 30
  ```

- [ ] **7.3** Restart and verify background appears
  ```bash
  docker compose restart homepage
  ```

**If skipping background:**
- Solid dark theme is sufficient; no action needed

### Phase 8: Testing & Validation

- [ ] **8.1** Full homepage restart to apply all changes
  ```bash
  docker compose restart homepage
  docker compose logs homepage --tail 50
  ```

- [ ] **8.2** Browser testing checklist:
  - [ ] Dark theme applied correctly
  - [ ] System health widgets show live data
  - [ ] Docker container widget shows running containers
  - [ ] All links open correctly
  - [ ] Observability tools (Grafana, Prometheus, Alertmanager) accessible
  - [ ] Remote environments collapsed by default
  - [ ] No console errors (check browser DevTools)

- [ ] **8.3** Take screenshots for documentation
  - Full dashboard view
  - Each major section
  - Compare with initial baseline screenshot

- [ ] **8.4** Validate widget data accuracy:
  - Compare CPU/RAM/Disk with `docker stats` or `htop`
  - Verify container health matches `docker ps`
  - Check Prometheus queries return data

### Phase 9: Alertmanager Integration (Optional)

**If adding alert count badge:**

- [ ] **9.1** Add Alertmanager widget to Observability section
  ```yaml
  - Alertmanager:
      icon: mdi-bell
      href: http://localhost:9093
      description: Alert routing and management
      target: _blank
      widget:
        type: customapi
        url: http://alertmanager:9093/api/v2/alerts
        method: GET
        display: count
        field: data
        label: Active Alerts
  ```

- [ ] **9.2** Test alert count appears and updates

### Phase 10: Documentation & Finalization

- [ ] **10.1** Create `homepage/README.md` documenting new structure
  - Explain each section
  - Document required dependencies (Glances, Docker socket)
  - Troubleshooting tips

- [ ] **10.2** Update main README.md with Homepage.dev info
  - Add link to Homepage dashboard
  - Update "Access Services" section

- [ ] **10.3** Commit changes with descriptive message
  ```bash
  git add homepage/
  git commit -m "feat(homepage): Transform into high-signal operational dashboard

  - Add settings.yaml with dark theme and cinematic layout
  - Add widgets.yaml for system health metrics (CPU, RAM, Disk, Uptime)
  - Reorganize services.yaml with local-first sections
  - Add Docker container health widget
  - Add Pipeline health section with Prometheus widgets
  - Move remote environments to collapsed accordion
  - Enable Docker socket access for container monitoring
  "
  ```

- [ ] **10.4** Test on fresh clone (if possible)
  - Verify configs are portable
  - Check for hardcoded paths or assumptions

### Phase 11: Future Enhancements (Post-MVP)

**Not required for initial implementation, but noted for future work:**

- [ ] Custom CSS for tighter spacing and typography
- [ ] Bookmarks.yaml for quick commands (docker compose restart, logs, etc.)
- [ ] Additional Prometheus widgets (LLM latency, queue age, etc.)
- [ ] Background image creation (dark topology pattern)
- [ ] Alert severity color coding (red/amber/green)
- [ ] Webhook integration for real-time updates

---

## Success Criteria

This plan is successful if:

✅ **Executor can implement blindly:** Each step is clear, ordered, and actionable  
✅ **Dashboard feels professional:** Dark, cinematic, high-density aesthetic  
✅ **Operator can assess health in <10 seconds:** System/container status immediately visible  
✅ **Aesthetic matches reference mood:** Dark theme, glassmorphism, calm but dense  
✅ **No security regressions:** Docker socket is read-only; no new ports exposed  

---

## Constraints Honored

✅ **No infrastructure architecture changes:** Only Homepage.dev configuration  
✅ **No new services added:** Using existing Prometheus, Grafana, Docker  
✅ **No new ports exposed:** All links use existing service ports  
✅ **No security weakening:** Read-only mounts, internal-only access  
✅ **Planning only:** This document does not implement; it guides implementation  

---

## Appendix A: Homepage.dev Widget Reference

**Widget Types Available:**

1. **Glances Widget:** System metrics (CPU, RAM, Disk, Uptime)
   - Requires: Glances server running on host
   - Best for: Real-time host metrics with minimal setup

2. **Docker Widget:** Container status and health
   - Requires: Docker socket mount (`/var/run/docker.sock`)
   - Best for: Container visibility and health monitoring

3. **Prometheus Widget:** Custom Prometheus queries
   - Requires: Prometheus URL and valid PromQL query
   - Best for: Application-specific metrics (queue depth, staleness, etc.)

4. **Ping Widget:** HTTP endpoint health checks
   - Requires: Accessible HTTP endpoint
   - Best for: Service availability (green/red status)

5. **Custom API Widget:** Generic JSON API queries
   - Requires: API endpoint and JSON path
   - Best for: Alert counts, custom metrics from any API

**Documentation:** https://gethomepage.dev/latest/widgets/

---

## Appendix B: Prometheus Query Examples

**Useful TutorDex-specific queries for Homepage widgets:**

```promql
# Collector staleness (seconds since last message)
tutordex:collector:seconds_since_last_message

# Worker queue depth (pending jobs)
tutordex_worker_queue_pending_jobs

# Worker throughput (jobs per second)
tutordex:worker:throughput_jobs_per_s

# Parse failure rate (errors per second)
tutordex:worker:parse_failure_rate_per_s

# LLM failure rate (errors per second)
tutordex:worker:llm_fail_rate_per_s

# Backend HTTP request rate (requests per second)
sum(rate(http_requests_total{job="tutordex_backend"}[5m]))

# Active alerts count
sum(ALERTS{alertstate="firing"})
```

**Documentation:** See `observability/prometheus/recording_rules.yml` for all pre-computed metrics.

---

## Appendix C: Docker Compose Socket Mount (Security Note)

**Why Docker socket is needed:**
- Homepage.dev Docker widget reads container status from Docker API
- Mounted as **read-only** (`:ro`) for security

**Security implications:**
- Homepage can read container metadata (names, status, health)
- Homepage **cannot** start/stop/modify containers (read-only mount)
- Homepage runs as non-root user in container

**Alternative (if Docker socket mount is unacceptable):**
- Skip Docker widget
- Use Prometheus cAdvisor metrics for container health instead
- Trade-off: Less real-time, more complex queries

---

## Appendix D: Glances vs. Prometheus for System Metrics

**Glances Widget Pros:**
- Real-time host metrics (1-second refresh)
- Built-in nice UI formatting
- Single widget for all system metrics
- Minimal configuration

**Glances Widget Cons:**
- Requires separate Glances server on host
- Additional dependency to maintain
- Not containerized (host-level process)

**Prometheus Widget Pros:**
- Uses existing Prometheus stack (no new dependencies)
- Historical data available (not just current)
- Consistent with other TutorDex metrics

**Prometheus Widget Cons:**
- More verbose configuration (separate widget per metric)
- Requires PromQL knowledge
- 15-second scrape interval (less real-time)

**Recommendation:** Start with **Glances** if available, fallback to **Prometheus** if not.

---

## Appendix E: Reference Implementation (Minimal Example)

**Minimal viable dashboard** (for quick testing):

**settings.yaml:**
```yaml
title: TutorDex Infrastructure
theme: dark
color: slate
```

**services.yaml:**
```yaml
- Observability:
    - Grafana:
        icon: grafana
        href: http://localhost:3300
    - Prometheus:
        icon: prometheus
        href: http://localhost:9090
    - Alertmanager:
        icon: mdi-bell
        href: http://localhost:9093

- Core Services:
    - Backend API:
        icon: mdi-api
        href: http://localhost:8000/docs
```

**widgets.yaml:**
```yaml
# Empty for minimal version; add metrics later
```

This minimal setup validates the theme and layout before adding complexity.

---

**END OF PLAN**

---

**Next Steps for Executor Agent:**
1. Follow "Executor Checklist" (Section 6) sequentially
2. Test each phase before proceeding to next
3. Take screenshots for validation
4. Document any deviations or issues encountered
5. Create PR with all changes and screenshots

**Estimated Implementation Time:** 2-4 hours (with testing and validation)

**Risk Assessment:** Low (all changes are read-only config files; easily reversible)
