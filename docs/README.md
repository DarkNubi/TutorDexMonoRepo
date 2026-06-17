# TutorDex Documentation

<!-- doc_lint:enforce -->
Doc type: Index

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-17
**Review trigger:** Update when canonical docs, historical classification, docs health, ADR lane, or generated inventory surfaces change.

## 📚 Documentation Index

Welcome to the TutorDex technical documentation. This directory contains comprehensive documentation for the TutorDex tuition assignment aggregator system.

---

## 🚀 Quick Start

- **AI agent / operator?** Start with [../AGENTS.md](../AGENTS.md), then [SYSTEM_MAP.md](SYSTEM_MAP.md), [ARCHITECTURE.md](ARCHITECTURE.md), [KNOWN_INVARIANTS.md](KNOWN_INVARIANTS.md), [DEPLOYMENT_TOPOLOGY.md](DEPLOYMENT_TOPOLOGY.md), [TESTING.md](TESTING.md), [OPERATIONS.md](OPERATIONS.md), and [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md)
- **Changing behavior?** Check [DOCS_CHANGE_POLICY.md](DOCS_CHANGE_POLICY.md), run `python3 scripts/docs_change_guard.py --base HEAD`, and record the docs update/skip decision in task evidence.
- **Architecture decision?** Use [adr/README.md](adr/README.md) and [adr/ADR_TEMPLATE.md](adr/ADR_TEMPLATE.md) for TutorDex-local decisions.
- **Docs health?** Run `python3 scripts/docs_health.py` and use [DOCS_SCORECARD.md](DOCS_SCORECARD.md) for the current SOTA audit.
- **New Developer?** Start with [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for architecture overview
- **Setting up environment?** See [../DEPENDENCIES.md](../DEPENDENCIES.md) and [../scripts/bootstrap.sh](../scripts/bootstrap.sh)
- **What to work on?** See [OUTSTANDING_TASKS_SUMMARY.md](OUTSTANDING_TASKS_SUMMARY.md) ⭐ for prioritized task list
- **Audit tasks?** See [Audit Documentation](#audit-documentation) section

---

## 📖 Core Documentation

### System Architecture
- **[../AGENTS.md](../AGENTS.md)** - Short repo-wide agent entrypoint: canonical docs, execution surfaces, safety rules
- **[SYSTEM_MAP.md](SYSTEM_MAP.md)** - Skimmable repo map: what exists, primary flows, runtime surfaces, debug entry points
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Design boundaries, ownership, invariants, runtime boundaries, failure modes
- **[KNOWN_INVARIANTS.md](KNOWN_INVARIANTS.md)** - Must-not-break assumptions for data, extraction, side effects, runtime surfaces, security, and docs
- **[DEPLOYMENT_TOPOLOGY.md](DEPLOYMENT_TOPOLOGY.md)** - Deployment/runtime surfaces, release flow, proof requirements, rollback paths
- **[TESTING.md](TESTING.md)** - Test layers, smoke gates, what each check proves, evidence recording
- **[OPERATIONS.md](OPERATIONS.md)** - Current operational runbook: health checks, incident starting points, proof expectations
- **[SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md)** - Authoritative system architecture and behavior documentation (1,246 lines)
  - Message collection and extraction pipeline
  - Persistence and merge strategies
  - Signal extraction (deterministic + LLM)
  - Distribution and broadcasting
  - Recovery and catchup procedures
- **[DEPLOYMENT_RELEASE_FLOW.md](DEPLOYMENT_RELEASE_FLOW.md)** - GitHub Actions and Firebase release flow
  - `main` push deploy surfaces
  - Firebase staging and production promotion checklist
  - Documentation rules for deploy behavior
- **[DOCS_CHANGE_POLICY.md](DOCS_CHANGE_POLICY.md)** - Change-to-docs routing matrix and local advisory guard
- **[DOCS_CATALOG.md](DOCS_CATALOG.md)** - Active vs historical docs classification
- **[GENERATED_INVENTORY.md](GENERATED_INVENTORY.md)** - Compact generated repo inventory
- **[DOCS_SCORECARD.md](DOCS_SCORECARD.md)** - SOTA docs audit, residual gaps, final recommendation
- **[adr/README.md](adr/README.md)** - TutorDex repo-local ADR lane and decision index

### Features
- **[signals.md](signals.md)** - Signal extraction documentation (tutor types, rate breakdown)
- **[time_availability.md](time_availability.md)** - Time slot availability parsing
- **[recovery_catchup.md](recovery_catchup.md)** - Backfill and reprocessing procedures

### Duplicate Detection
- **[DUPLICATE_DETECTION_INDEX.md](DUPLICATE_DETECTION_INDEX.md)** - Main index for duplicate detection documentation
- **[DUPLICATE_DETECTION.md](DUPLICATE_DETECTION.md)** - Comprehensive duplicate detection guide (1,453 lines)
- **Note:** Additional duplicate detection docs archived in [archive/duplicate-detection/](archive/duplicate-detection/)

### Assignment Features
- **[assignment_rating_system.md](assignment_rating_system.md)** - Assignment rating and feedback system
- **[ASSIGNMENT_RATING_IMPLEMENTATION_SUMMARY.md](ASSIGNMENT_RATING_IMPLEMENTATION_SUMMARY.md)** - Implementation details

### Integrations
- **[TELEGRAM_WEBHOOK_SETUP.md](TELEGRAM_WEBHOOK_SETUP.md)** - Telegram webhook configuration
- **[TELEGRAM_WEBHOOK_QUICKREF.md](TELEGRAM_WEBHOOK_QUICKREF.md)** - Quick reference guide
- **[BROADCAST_SYNC_IMPLEMENTATION.md](BROADCAST_SYNC_IMPLEMENTATION.md)** - Broadcast synchronization

### Database
- **[MIGRATION_2026-01-07_estimated_postal_distance.md](MIGRATION_2026-01-07_estimated_postal_distance.md)** - Database migration documentation

### Observability
- **[GRAFANA_AUDIT_SUMMARY.md](GRAFANA_AUDIT_SUMMARY.md)** - Grafana observability audit
- **[GRAFANA_DASHBOARD_REPAIR_REPORT.md](GRAFANA_DASHBOARD_REPAIR_REPORT.md)** - Dashboard repair report

### Infrastructure Dashboard
- **[HOMEPAGE_DASHBOARD_PLAN.md](HOMEPAGE_DASHBOARD_PLAN.md)** - Complete Homepage.dev transformation plan (1,041 lines)
  - Current state analysis of 17 services
  - Dashboard blueprint with visual hierarchy
  - 50+ step executor checklist
  - Aesthetic implementation guide (dark theme, glassmorphism)
- **[HOMEPAGE_QUICK_START.md](HOMEPAGE_QUICK_START.md)** - 30-minute quick start guide
  - Minimal viable dashboard setup
  - Widget configuration examples
  - Troubleshooting guide

---

## 🔍 Audit Documentation

### January 2026 Codebase Quality Audits

**Current Audit (January 15, 2026):**
- **[CODEBASE_QUALITY_AUDIT_2026-01-15.md](CODEBASE_QUALITY_AUDIT_2026-01-15.md)** - Latest comprehensive audit
  - **Status:** Good (3 critical risks identified)
  - Overall quality assessment after 16 priorities completed
  - Risk map with 10 critical zones
- **[AUDIT_ACTION_PLAN_2026-01-15.md](AUDIT_ACTION_PLAN_2026-01-15.md)** - Actionable priorities
  - 9 prioritized actions (3 critical, 3 high-priority, 3 medium-priority)
  - Week-by-week tracking with success metrics
- **[AUDIT_CHECKLIST.md](AUDIT_CHECKLIST.md)** - Progress tracking (16/16 complete ✅)

**Implementation Planning:**
- **[IMPLEMENTATION_PLAN_2026-01-16.md](IMPLEMENTATION_PLAN_2026-01-16.md)** - Current implementation plan
- **[CONSOLIDATION_PLAN.md](CONSOLIDATION_PLAN.md)** - Documentation consolidation strategy
- **[OUTSTANDING_TASKS_SUMMARY.md](OUTSTANDING_TASKS_SUMMARY.md)** - ⭐ **Quick reference for outstanding work** (6 min read)
- **[OUTSTANDING_TASKS_2026-01-16.md](OUTSTANDING_TASKS_2026-01-16.md)** - Comprehensive outstanding tasks list (15 min read)

**Status:** ✅ 16/16 audit priorities complete, 3 new critical risks identified

**Note:** Additional audit docs archived in [archive/audit-2026-01/](archive/audit-2026-01/)

---

## 📦 Archived Documentation

Historical documentation from completed projects is preserved in the archive:

- **[archive/](archive/)** - Main archive directory ([README](archive/README.md))
  - **[archive/audit-2026-01/](archive/audit-2026-01/)** - Completed audit docs (11 files)
  - **[archive/refactoring-2026-01/](archive/refactoring-2026-01/)** - Completed refactoring docs (7 files)
  - **[archive/duplicate-detection/](archive/duplicate-detection/)** - Consolidated dup detection docs (5 files)
  - **[archive/phase-tracking/](archive/phase-tracking/)** - Phase tracking documents (5 files)

**Total Archived:** 28 files (preserved for historical reference)

**Why Archive?**
- Work is complete
- Superseded by newer documentation
- Historical value preserved
- Cleaner active documentation structure

---

## 🛠️ Additional Resources

### Developer Tools
- **[codex-instructions.md](codex-instructions.md)** - AI coding assistant instructions
- **[../.github/copilot-instructions.md](../.github/copilot-instructions.md)** - GitHub Copilot configuration
- **[../scripts/tutordex_healthcheck.sh](../scripts/tutordex_healthcheck.sh)** - Read-only orientation helper for agents; does not source or print env files itself

### Component READMEs
- **[../TutorDexAggregator/README.md](../TutorDexAggregator/README.md)** - Aggregator service documentation
- **[../TutorDexBackend/README.md](../TutorDexBackend/README.md)** - Backend API documentation
- **[../TutorDexWebsite/README.md](../TutorDexWebsite/README.md)** - Website documentation

### Configuration & Setup
- **[../DEPENDENCIES.md](../DEPENDENCIES.md)** - External dependencies documentation
- **[../scripts/bootstrap.sh](../scripts/bootstrap.sh)** - One-command environment setup
- **[../docker-compose.yml](../docker-compose.yml)** - Docker Compose configuration
- **[ENV_CONFIG_README.md](ENV_CONFIG_README.md)** - Pydantic environment configuration overview
- **[PYDANTIC_CONFIG_QUICKSTART.md](PYDANTIC_CONFIG_QUICKSTART.md)** - Quick start guide for Pydantic config
- **[PYDANTIC_CONFIG.md](PYDANTIC_CONFIG.md)** - Complete Pydantic-Settings guide (24KB)

### Testing & Quality
- **[../tests/](../tests/)** - Test suite (70+ tests)
- **[../.githooks/](../.githooks/)** - Pre-commit hooks for code quality
- **[../pytest.ini](../pytest.ini)** - PyTest configuration

---

## 📁 Documentation Organization

```
docs/
├── README.md (this file)                        # Documentation index
├── SYSTEM_MAP.md                                # Skimmable repo map
├── ARCHITECTURE.md                              # Design boundaries and invariants
├── KNOWN_INVARIANTS.md                          # Must-not-break assumptions
├── DEPLOYMENT_TOPOLOGY.md                       # Runtime/deploy surfaces
├── TESTING.md                                   # Test and proof gates
├── OPERATIONS.md                                # Current operator runbook
├── DOCS_CHANGE_POLICY.md                        # Change-to-docs routing
├── DOCS_CATALOG.md                              # Active/historical classification
├── GENERATED_INVENTORY.md                       # Generated inventory
├── DOCS_SCORECARD.md                            # SOTA docs scorecard
├── adr/                                         # Repo-local ADR lane
├── CONSOLIDATION_PLAN.md                        # Documentation consolidation strategy
├── IMPLEMENTATION_PLAN_2026-01-16.md            # Current implementation plan
│
├── Core System (4 files)
│   ├── SYSTEM_INTERNAL.md                       # System architecture (primary)
│   ├── signals.md                               # Signal extraction
│   ├── time_availability.md                     # Time parsing
│   └── recovery_catchup.md                      # Backfill procedures
│
├── Configuration (3 files)
│   ├── ENV_CONFIG_README.md                     # Pydantic config overview
│   ├── PYDANTIC_CONFIG_QUICKSTART.md            # Quick start guide
│   └── PYDANTIC_CONFIG.md                       # Complete Pydantic guide
│
├── Current Audit (3 files)
│   ├── CODEBASE_QUALITY_AUDIT_2026-01-15.md     # Latest audit (Jan 15)
│   ├── AUDIT_ACTION_PLAN_2026-01-15.md          # Actionable priorities
│   └── AUDIT_CHECKLIST.md                       # Progress tracking (16/16 ✅)
│
├── Features (7 files)
│   ├── DUPLICATE_DETECTION_INDEX.md             # Duplicate detection hub
│   ├── DUPLICATE_DETECTION.md                   # Comprehensive guide
│   ├── assignment_rating_system.md              # Rating system
│   ├── ASSIGNMENT_RATING_IMPLEMENTATION_SUMMARY.md
│   ├── TELEGRAM_WEBHOOK_SETUP.md                # Telegram integration
│   ├── TELEGRAM_WEBHOOK_QUICKREF.md             # Quick reference
│   └── BROADCAST_SYNC_IMPLEMENTATION.md         # Broadcasting
│
├── Observability (2 files)
│   ├── GRAFANA_AUDIT_SUMMARY.md                 # Monitoring audit
│   └── GRAFANA_DASHBOARD_REPAIR_REPORT.md       # Dashboard updates
│
├── Current Refactoring (1 file)
│   └── AGENT_HANDOVER_COMPLETE_REFACTORING.md   # Refactoring status
│
├── Database (1 file)
│   └── MIGRATION_2026-01-07_estimated_postal_distance.md
│
├── AI Tools (1 file)
│   └── codex-instructions.md                    # AI assistant instructions
│
└── archive/                                      # Archived documentation (28 files)
    ├── audit-2026-01/                           # Completed audit docs (11 files)
    ├── refactoring-2026-01/                     # Completed refactoring docs (7 files)
    ├── duplicate-detection/                     # Consolidated dup detection docs (5 files)
    └── phase-tracking/                          # Phase tracking documents (5 files)
```

**Active Documentation:** ~24 files  
**Archived Documentation:** 28 files  
**Total:** 52 files

---

## 🎯 Common Tasks

### Understanding the System
1. Read [SYSTEM_MAP.md](SYSTEM_MAP.md) for navigation and debug entry points
2. Read [ARCHITECTURE.md](ARCHITECTURE.md) for boundaries and ownership
3. Read [KNOWN_INVARIANTS.md](KNOWN_INVARIANTS.md) for assumptions that must not break
4. Read [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for detailed behavior
5. Check [../DEPENDENCIES.md](../DEPENDENCIES.md) for external services
6. Review [DUPLICATE_DETECTION_INDEX.md](DUPLICATE_DETECTION_INDEX.md) for duplicate handling

### Setting Up Development Environment
1. Run `../scripts/bootstrap.sh` to set up everything automatically
2. See [../DEPENDENCIES.md](../DEPENDENCIES.md) for manual setup
3. Check component READMEs for service-specific setup

### Working on Features
1. Consult [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for affected components
2. Update relevant feature documentation in `docs/`
3. Add tests in `../tests/`
4. Run pre-commit hooks with `git commit` (see `../.githooks/`)

### Monitoring & Debugging
1. Start with [OPERATIONS.md](OPERATIONS.md) and state the execution surface checked
2. Run `../scripts/tutordex_healthcheck.sh` for a read-only orientation pass
3. See [GRAFANA_AUDIT_SUMMARY.md](GRAFANA_AUDIT_SUMMARY.md) for available dashboards
4. Check `../observability/` for Prometheus, Grafana, Tempo configuration
5. Use [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for debugging pipeline issues

---

## 📝 Documentation Standards

### File Naming
- Use `SCREAMING_SNAKE_CASE.md` for major documents (e.g., `SYSTEM_INTERNAL.md`)
- Use `lowercase_with_underscores.md` for feature docs (e.g., `signals.md`)
- Use descriptive prefixes for related docs (e.g., `DUPLICATE_DETECTION_*.md`)

### Content Structure
- Start with a title and brief description
- Include a table of contents for documents >200 lines
- Use clear section headers
- Provide code examples where relevant
- Include troubleshooting sections

### Maintenance
- Update [SYSTEM_MAP.md](SYSTEM_MAP.md) when components, flows, or debug entry points move
- Update [ARCHITECTURE.md](ARCHITECTURE.md) when ownership boundaries, invariants, or runtime boundaries change
- Update [KNOWN_INVARIANTS.md](KNOWN_INVARIANTS.md) when a must-not-break assumption changes
- Update [DEPLOYMENT_TOPOLOGY.md](DEPLOYMENT_TOPOLOGY.md) when deployment/runtime surfaces change
- Update [TESTING.md](TESTING.md) when test commands, smoke gates, or proof expectations change
- Update [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) when changing core behavior
- Update [OPERATIONS.md](OPERATIONS.md) when changing production operations, health checks, recovery, or verification procedures
- Keep audit documentation frozen (historical record)
- Update this index when adding new major documentation

---

## 🔗 External Links

- **Repository:** https://github.com/DarkNubi/TutorDexMonoRepo
- **Grafana:** http://localhost:3300 (when running locally)
- **Prometheus:** http://localhost:9090 (when running locally)
- **Backend API:** http://localhost:8000/docs (Swagger UI)
- **Tempo:** http://localhost:3200 (distributed tracing)

---

## ❓ Getting Help

1. **Search this documentation** - Use your editor's search or `grep`
2. **Check component READMEs** - Service-specific information
3. **Review [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md)** - Authoritative architecture reference
4. **Inspect code** - Well-commented with type hints
5. **Check tests** - Examples of usage in `../tests/`

---

**Last Updated:** 2026-01-16  
**Documentation Version:** 1.1 (Post-Consolidation)  
**Active Files:** ~24 | **Archived Files:** 28 | **Total:** 52
