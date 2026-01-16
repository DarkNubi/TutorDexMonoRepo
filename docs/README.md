# TutorDex Documentation

## 📚 Documentation Index

Welcome to the TutorDex technical documentation. This directory contains comprehensive documentation for the TutorDex tuition assignment aggregator system.

---

## 🚀 Quick Start

- **New Developer?** Start with [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for architecture overview
- **Setting up environment?** See [../DEPENDENCIES.md](../DEPENDENCIES.md) and [../scripts/bootstrap.sh](../scripts/bootstrap.sh)
- **Audit tasks?** See [Audit Documentation](#audit-documentation) section

---

## 📖 Core Documentation

### System Architecture
- **[SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md)** - Authoritative system architecture and behavior documentation (1,246 lines)
  - Message collection and extraction pipeline
  - Persistence and merge strategies
  - Signal extraction (deterministic + LLM)
  - Distribution and broadcasting
  - Recovery and catchup procedures

### Features
- **[signals.md](signals.md)** - Signal extraction documentation (tutor types, rate breakdown)
- **[time_availability.md](time_availability.md)** - Time slot availability parsing
- **[recovery_catchup.md](recovery_catchup.md)** - Backfill and reprocessing procedures

### Duplicate Detection
- **[DUPLICATE_DETECTION_INDEX.md](DUPLICATE_DETECTION_INDEX.md)** - Main index for duplicate detection documentation
- **[DUPLICATE_DETECTION.md](DUPLICATE_DETECTION.md)** - Comprehensive duplicate detection guide (1,453 lines)
- **[DUPLICATE_DETECTION_QUICKSTART.md](DUPLICATE_DETECTION_QUICKSTART.md)** - Quick start guide (764 lines)
- **[DUPLICATE_DETECTION_ADMIN.md](DUPLICATE_DETECTION_ADMIN.md)** - Admin operations guide
- **[DUPLICATE_DETECTION_SUMMARY.md](DUPLICATE_DETECTION_SUMMARY.md)** - Summary document
- **[DUPLICATE_DETECTION_ASSUMPTIONS_VALIDATION.md](DUPLICATE_DETECTION_ASSUMPTIONS_VALIDATION.md)** - Validation results
- **[DUPLICATE_DETECTION_VALIDATION_RESULTS.md](DUPLICATE_DETECTION_VALIDATION_RESULTS.md)** - Test results
- **[DUPLICATE_DETECTION_FLOW.txt](DUPLICATE_DETECTION_FLOW.txt)** - Flow diagram

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

---

## 🔍 Audit Documentation

### January 2026 Codebase Quality Audits

**Latest Audit (January 15, 2026):**
- **[CODEBASE_QUALITY_AUDIT_2026-01-15.md](CODEBASE_QUALITY_AUDIT_2026-01-15.md)** - Updated comprehensive audit (35,000+ words)
  - **Status:** Good (3 critical new risks identified)
  - Overall quality assessment after 16 priorities completed
  - Risk map with 10 critical zones
  - Concrete improvement plan (short/medium/long term)
- **[AUDIT_ACTION_PLAN_2026-01-15.md](AUDIT_ACTION_PLAN_2026-01-15.md)** - Actionable priorities with owners and deadlines
  - 9 prioritized actions (3 critical, 3 high-priority, 3 medium-priority)
  - Week-by-week tracking with success metrics
  - Estimated ROI: 5× faster incident resolution, 3× fewer bugs

**Previous Audit (January 12, 2026):**
- **[CODEBASE_QUALITY_AUDIT_2026-01.md](CODEBASE_QUALITY_AUDIT_2026-01.md)** - Original audit report (1,400 lines)
  - Identified 16 priorities for code quality improvements
  - All 16 priorities now complete ✅

**Audit Tracking & Implementation:**
- **[AUDIT_README.md](AUDIT_README.md)** - Navigation hub for audit documentation
- **[AUDIT_CHECKLIST.md](AUDIT_CHECKLIST.md)** - Progress tracking checklist (16/16 complete)
- **[AUDIT_TODO_SUMMARY.md](AUDIT_TODO_SUMMARY.md)** - Quick reference summary
- **[REMAINING_AUDIT_TASKS.md](REMAINING_AUDIT_TASKS.md)** - Detailed implementation guide (1,047 lines)

**Status:** ✅ Phase 1 complete (16/16), 🔴 Phase 2 critical actions required (9 priorities)

---

## 🛠️ Additional Resources

### Developer Tools
- **[codex-instructions.md](codex-instructions.md)** - AI coding assistant instructions
- **[../.github/copilot-instructions.md](../.github/copilot-instructions.md)** - GitHub Copilot configuration

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
├── README.md (this file)                    # Documentation index
│
├── Core System
│   ├── SYSTEM_INTERNAL.md                   # System architecture (primary)
│   ├── signals.md                           # Signal extraction
│   ├── time_availability.md                 # Time parsing
│   └── recovery_catchup.md                  # Backfill procedures
│
├── Configuration
│   ├── ENV_CONFIG_README.md                 # Pydantic config overview
│   ├── PYDANTIC_CONFIG_QUICKSTART.md        # Quick start guide
│   └── PYDANTIC_CONFIG.md                   # Complete Pydantic guide
│
├── Audit (2026-01)
│   ├── CODEBASE_QUALITY_AUDIT_2026-01-15.md # Latest audit (Jan 15)
│   ├── AUDIT_ACTION_PLAN_2026-01-15.md      # Actionable priorities
│   ├── CODEBASE_QUALITY_AUDIT_2026-01.md    # Original audit (Jan 12)
│   ├── AUDIT_README.md                       # Audit documentation hub
│   ├── AUDIT_CHECKLIST.md                    # Progress tracking (16/16 ✅)
│   ├── AUDIT_TODO_SUMMARY.md                 # Quick reference
│   └── REMAINING_AUDIT_TASKS.md              # Implementation guide
│
├── Features
│   ├── DUPLICATE_DETECTION_INDEX.md         # Duplicate detection hub
│   ├── DUPLICATE_DETECTION*.md              # Duplicate detection docs
│   ├── assignment_rating_system.md          # Rating system
│   ├── TELEGRAM_WEBHOOK*.md                 # Telegram integration
│   └── BROADCAST_SYNC_IMPLEMENTATION.md     # Broadcasting
│
└── Observability
    ├── GRAFANA_AUDIT_SUMMARY.md             # Monitoring audit
    └── GRAFANA_DASHBOARD_REPAIR_REPORT.md   # Dashboard updates
```

---

## 🎯 Common Tasks

### Understanding the System
1. Read [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for overall architecture
2. Check [../DEPENDENCIES.md](../DEPENDENCIES.md) for external services
3. Review [DUPLICATE_DETECTION_INDEX.md](DUPLICATE_DETECTION_INDEX.md) for duplicate handling

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
1. See [GRAFANA_AUDIT_SUMMARY.md](GRAFANA_AUDIT_SUMMARY.md) for available dashboards
2. Check `../observability/` for Prometheus, Grafana, Tempo configuration
3. Use [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) for debugging pipeline issues

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
- Update [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md) when changing core behavior
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

**Last Updated:** 2026-01-14  
**Documentation Version:** 1.0 (Post-Audit Cleanup)
