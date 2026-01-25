# TutorDex Homepage — Infrastructure Operating Doctrine Compliance

**Status:** ✅ Compliant (as of 2026-01-25)

## Executive Summary

The TutorDex homepage implementation fully adheres to the **TutorDex Infrastructure Operating Doctrine (Homepage-Centric Model)**. This document validates compliance and provides maintenance guidelines.

---

## Doctrine Principles

### Core Operating Model

```
Homepage = Observe
Grafana = Understand  
Alertmanager = Interrupt
CI/CD = Mutate
Humans = Decide
```

**If something violates this separation, it's a smell.**

---

## Compliance Verification

### ✅ 1. Read-Only Forever

**Requirement:** Homepage must remain read-only forever. No restart/trigger/edit/mutation capabilities.

**Implementation:**
```yaml
# docker-compose.yml
volumes:
  - ./homepage/config:/app/config:ro              # Read-only
  - ./homepage/assets:/app/public/assets:ro       # Read-only
  - /var/run/docker.sock:/var/run/docker.sock:ro  # Read-only
```

**Verification:**
- ✅ All volumes mounted with `:ro` flag
- ✅ No action buttons or triggers in config
- ✅ No JavaScript execution capabilities
- ✅ No API write endpoints
- ✅ No secrets or credentials stored

**Safety:**
Can be safely shown to:
- Collaborators
- Future hires
- Auditors
- Advisors

Without fear they'll break prod.

---

### ✅ 2. Environment-First Grouping

**Requirement:** Top-level grouping by environment (Dev → Staging → Prod), not by technology.

**Implementation:**
```
TutorDex Infrastructure
├── 🔧 Dev — Core Platform
├── 🔧 Dev — Data & Identity
├── 🔧 Dev — Observability
├── 🔧 Dev — Bots & Automation
│
├── 🧪 Staging — Core Platform
├── 🧪 Staging — Data & Identity
├── 🧪 Staging — Observability
│
└── ⚠️ PROD — Core Platform
    ⚠️ PROD — Data & Identity
    ⚠️ PROD — Observability
```

**Visual Indicators:**
- 🔧 Dev (wrench) = Safe to experiment
- 🧪 Staging (test tube) = Testing environment
- ⚠️ PROD (warning) = Production warning

**Verification:**
- ✅ Environment is the top-level grouping
- ✅ Clear visual distinction via emoji prefixes
- ✅ URLs encode environment (staging-, prod- prefixes)
- ✅ Never mixed dev/staging/prod in same visual group

**Why This Matters:**
When something breaks, your brain should instantly know: "This is prod. This matters."

---

### ✅ 3. Intent-Based Sections (Not Tech-Based)

**Requirement:** Group by mental model/intent, NOT by technology, ports, or vendors.

**✅ Correct Implementation:**
- Core Platform (what delivers value)
- Data & Identity (where state lives)
- Observability (how we see what's happening)
- Bots & Automation (supporting automation)

**❌ What We Avoid:**
- Grouping by "Docker containers"
- Grouping by "Port 8000 services"
- Grouping by "Grafana Labs tools"
- Grouping by "Tailscale services"

**Verification:**
- ✅ Services.yaml uses intent-based section names
- ✅ Settings.yaml layout follows intent model
- ✅ No technology-specific top-level groups

---

### ✅ 4. No Mutation Surface

**Requirement:** Homepage shows status, never changes it.

**What We Show:**
- Links (navigation)
- Health checks (ping status)
- Metrics (read-only Prometheus queries)
- Status indicators (up/down)

**What We Don't Have:**
- ❌ Restart buttons
- ❌ Trigger workflows
- ❌ Edit configs
- ❌ Run commands
- ❌ Modify state
- ❌ Delete resources

**Verification:**
- ✅ Widgets.yaml contains only read-only Prometheus queries
- ✅ Services.yaml contains only links and descriptions
- ✅ No forms or input fields
- ✅ No POST/PUT/DELETE actions

---

## Implementation Details

### File Structure

```
homepage/
├── config/
│   ├── services.yaml     # Doctrine-compliant service links
│   ├── settings.yaml     # Theme and layout config
│   ├── widgets.yaml      # Read-only metrics
│   ├── bookmarks.yaml    # Optional bookmarks
│   └── logs/             # Homepage logs (created at runtime)
├── assets/
│   └── TutorDex-logo-1024.png
└── README.md             # Doctrine documentation
```

### Services Configuration

**Structure:**
```yaml
- Environment — Section:
    - Service Name:
        icon: <icon-name>
        href: <url>
        description: <text>
        target: _blank
        ping: <health-check-url>  # Optional
```

**Example:**
```yaml
- 🔧 Dev — Observability:
    - Grafana:
        icon: grafana
        href: http://localhost:3300
        description: Metrics visualization and dashboards
        target: _blank
        ping: http://grafana:3000
```

### Widgets Configuration

**Prometheus Metrics (Read-Only):**
```yaml
- prometheus:
    href: http://prometheus:9090
    fields:
      - CPU Usage:
          query: 100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
          suffix: "%"
```

---

## Maintenance Guidelines

### ✅ Safe Changes

You can safely:
- Add new links to existing services
- Update URLs or descriptions
- Add new service groups (following doctrine structure)
- Add new read-only Prometheus metrics
- Update visual styling (theme, colors, layout)

### ⚠️ Requires Review

Needs careful consideration:
- Adding interactive widgets
- Mounting new Docker sockets
- Adding authentication
- Storing secrets in config

### 🚫 Prohibited Changes

Never do:
- Remove `:ro` flags from volume mounts
- Add action buttons or triggers
- Add forms or user input
- Store credentials or secrets
- Create mutation endpoints
- Add click-to-restart capabilities

**Rule:** If you ever think "It would be nice if I could just click and restart…" — Stop. That's how prod accidents happen.

---

## Kill Rules

Remove or redesign homepage if it:
- ❌ Starts executing actions
- ❌ Becomes interactive beyond links
- ❌ Duplicates Grafana dashboards
- ❌ Requires a database
- ❌ Becomes a "mini app"

**Homepage should feel boring. Boring infra is good infra.**

---

## Validation Checklist

Use this checklist to verify doctrine compliance after changes:

### Environment Separation
- [ ] Dev, Staging, and Prod are top-level groups
- [ ] Visual indicators clearly distinguish environments
- [ ] URLs encode environment information
- [ ] Never mixed environments in same section

### Intent-Based Grouping
- [ ] Sections named by intent, not technology
- [ ] Core Platform, Data & Identity, Observability present
- [ ] No "Docker" or vendor-specific top-level groups

### Read-Only Nature
- [ ] All volume mounts use `:ro` flag
- [ ] No action buttons in UI
- [ ] No mutation capabilities anywhere
- [ ] Widgets show metrics only (no controls)

### Safety Posture
- [ ] No credentials stored in config
- [ ] No execution paths available
- [ ] Safe to share with external stakeholders
- [ ] Low blast radius

---

## Operational Benefits

### Clarity
- Instant environment recognition (🔧/🧪/⚠️)
- Mental model matches UI structure
- No URL memorization needed

### Safety
- No accidental prod mutations
- Read-only prevents operator errors
- Clear separation of concerns

### Scalability
- Easy to add new services
- Consistent structure as system grows
- Future-proof for partnerships

### Trust
- Auditable and transparent
- Safe to share with stakeholders
- Neutral posture (no vendor lock-in)

---

## Related Documentation

- [Homepage README](../homepage/README.md) - Setup and configuration
- [System Architecture](SYSTEM_INTERNAL.md) - How TutorDex works
- [Observability Stack](../observability/README.md) - Prometheus, Grafana, Alertmanager
- [Docker Compose](../docker-compose.yml) - Service definitions

---

## Maintenance History

| Date       | Change | Compliance Status |
|------------|--------|-------------------|
| 2026-01-25 | Initial doctrine implementation | ✅ Compliant |

---

## Contact

For questions about homepage doctrine compliance:
- Review this document first
- Check [Homepage README](../homepage/README.md) for configuration
- Reference the original doctrine specification in issue/PR

---

**Remember:** Homepage = Observe. If it does anything else, it's wrong.
