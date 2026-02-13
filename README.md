# TutorDex MonoRepo

**A tuition assignment aggregator that collects, parses, and distributes tutor assignment posts from multiple Telegram channels.**

---

## 🎯 Project Status: Milestone 1 Complete ✅

TutorDex has achieved **Aggregation Accuracy** with a production-ready infrastructure:
- ✅ Multi-channel Telegram aggregation with LLM parsing
- ✅ Redis matching engine + Supabase persistence
- ✅ DM delivery to matched tutors
- ✅ Website with filtering, search, and authentication
- ✅ Full observability stack (50+ metrics, 17 alerts)

**Ready for beta testing with real tutors.**

---

---

## 📚 Documentation

**📖 Start Here:**
- **[docs/README.md](docs/README.md)** - Complete documentation index and navigation guide
- **[docs/SYSTEM_INTERNAL.md](docs/SYSTEM_INTERNAL.md)** - Authoritative system architecture (primary reference)
- **[DEPENDENCIES.md](DEPENDENCIES.md)** - External dependencies and setup guide
- **[scripts/bootstrap.sh](scripts/bootstrap.sh)** - One-command environment setup

**Component Documentation:**
- [TutorDexAggregator/README.md](TutorDexAggregator/README.md) - Message collector and LLM parser
- [TutorDexBackend/README.md](TutorDexBackend/README.md) - FastAPI matching engine and API
- [TutorDexWebsite/README.md](TutorDexWebsite/README.md) - React + Firebase website
- [observability/](observability/) - Prometheus, Grafana, Alertmanager, Tempo/OTEL stack

**Feature Documentation:**
- [docs/DUPLICATE_DETECTION_INDEX.md](docs/DUPLICATE_DETECTION_INDEX.md) - Duplicate detection hub
- [docs/assignment_rating_system.md](docs/assignment_rating_system.md) - Assignment rating and feedback
- [docs/signals.md](docs/signals.md) - Signal extraction (tutor types, rates)
- [docs/TELEGRAM_WEBHOOK_SETUP.md](docs/TELEGRAM_WEBHOOK_SETUP.md) - Telegram integration

**Quality & Testing:**
- [docs/CODEBASE_QUALITY_AUDIT_2026-01-15.md](docs/CODEBASE_QUALITY_AUDIT_2026-01-15.md) - Full audit report
- [docs/AUDIT_CHECKLIST.md](docs/AUDIT_CHECKLIST.md) - Audit completion status (16/16 ✅)
- [tests/](tests/) - Test suite (70+ tests)
- [.githooks/](.githooks/) - Pre-commit hooks for code quality

---

## 🚀 Quick Start (Development)

### Prerequisites
- Python 3.9+ with pip
- Node.js 18+ with npm
- Docker Desktop (recommended)
- Local LLM server (LM Studio or compatible)

### Automated Setup (Recommended)

```bash
# Clone the repository
git clone https://github.com/DarkNubi/TutorDexMonoRepo.git
cd TutorDexMonoRepo

# Run the bootstrap script (checks prereqs, starts services, installs deps)
./scripts/bootstrap.sh
```

### Manual Setup

```bash
# Configure environment variables
cp TutorDexAggregator/.env.example TutorDexAggregator/.env
cp TutorDexBackend/.env.example TutorDexBackend/.env
cp TutorDexWebsite/.env.example TutorDexWebsite/.env
# Edit .env files with your credentials

# Start all services with Docker
docker compose up -d --build

# Check logs
docker compose logs -f
```

See [DEPENDENCIES.md](DEPENDENCIES.md) for detailed setup instructions.

### Access Services

- **Backend API:** http://localhost:8000/docs (Swagger UI)
- **Website:** http://localhost:5173 (development) or deploy to Firebase
- **Grafana:** http://localhost:3300 (default: admin/admin)
- **Prometheus:** http://localhost:9090
- **Tempo:** http://localhost:3200 (distributed tracing)
- **Alertmanager:** http://localhost:9093

---

## 🏗️ Architecture

```
┌─────────────────┐
│ Telegram        │
│ Channels        │
└────────┬────────┘
         │ (Telethon)
         ▼
┌─────────────────┐      ┌─────────────┐
│ Collector       │─────▶│ Supabase    │
│ (collector.py)  │      │ (PostgreSQL)│
└────────┬────────┘      └──────┬──────┘
         │                      │
         │ (Queue jobs)         │
         ▼                      │
┌─────────────────┐             │
│ Extraction      │             │
│ Worker          │◀────────────┘
│ (LLM + hardening)│
└────────┬────────┘
         │ (Persist + broadcast)
         ▼
┌─────────────────┐      ┌─────────────┐
│ Matching        │◀─────│ Redis       │
│ Backend         │      │ (preferences)│
│ (FastAPI)       │      └─────────────┘
└────────┬────────┘
         │
         ├─▶ DM Bot (Telegram)
         └─▶ Website (React + Firebase)
```

---

## 🛠️ Technology Stack

**Backend (Python):**
- FastAPI, Uvicorn, Telethon
- Redis, Supabase (PostgreSQL)
- OpenAI-compatible LLM API
- Prometheus metrics, OpenTelemetry

**Frontend (JavaScript/TypeScript):**
- Vite, React, Firebase Auth
- Framer Motion, Lucide React

**Infrastructure:**
- Docker + Docker Compose
- Prometheus, Grafana, Alertmanager, Tempo
- Self-hosted Supabase

---

## 🔧 Development Workflow

1. **Make changes** to code in `TutorDexAggregator/`, `TutorDexBackend/`, or `TutorDexWebsite/`
2. **Test locally** with `docker compose up --build`
3. **Check observability** dashboards for metrics and logs
4. **Commit and push** to trigger CI/CD
5. **Deploy** automatically via GitHub Actions

---

## 📊 Monitoring

All services emit metrics and structured logs:
- **Metrics:** Scraped by Prometheus, visualized in Grafana
- **Logs:** Services emit structured logs to container stdout (`docker compose logs`)
- **Traces:** Collected by OTEL Collector, stored in Tempo (enabled by default)
- **Alerts:** Defined in Prometheus, routed by Alertmanager to Telegram

See [observability/](observability/) for configuration details.

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_backend_api.py

# Run with coverage
pytest --cov=TutorDexAggregator --cov=TutorDexBackend tests/
```

**Test Coverage:**
- 40+ Backend API integration tests
- 16 Assignment state machine tests
- 17 Supabase client tests
- Total: 70+ tests

See [tests/](tests/) for more details.

---

## 🔒 Security & Quality

- **Pre-commit hooks:** Installed via `.githooks/` - warns on large files (>500 lines)
- **Rate limiting:** Implemented for all public API endpoints
- **Authentication:** Firebase Auth with admin verification
- **Configuration:** Type-safe with pydantic-settings validation
- **Circuit breakers:** LLM API protection against failures
- **RPC 300 detection:** Prevents silent Supabase RPC failures

---

## 🎯 Recent Improvements (January 2026)

✅ **Codebase Quality Audit Complete (16/16 priorities)**
- HTTP integration tests for all 30 API endpoints
- Centralized configuration with pydantic-settings
- End-to-end distributed tracing (Tempo + OTEL)
- Assignment state machine with enforced transitions
- Business metrics dashboard (9 KPIs)
- Rate limiting middleware with Redis backend
- Unified Supabase client with RPC 300 detection
- Comprehensive dependency documentation
- Pre-commit hooks for code quality

See [docs/AUDIT_CHECKLIST.md](docs/AUDIT_CHECKLIST.md) for details.

---

## 🤝 Contributing

This is currently a private project. For questions or suggestions:
1. Open an issue in this repository
2. Contact the maintainer: DarkNubi

---

## 📄 License

Proprietary - All rights reserved

---

## 🔗 Quick Links

- [System Internal](docs/SYSTEM_INTERNAL.md) - Authoritative architecture and behavior
- [Outstanding Tasks](docs/OUTSTANDING_TASKS_SUMMARY.md) - Prioritized work summary
- [Implementation Plan](docs/IMPLEMENTATION_PLAN_2026-01-16.md) - Current implementation plan
- [Component READMEs](TutorDexAggregator/README.md) - Detailed setup instructions
- [Observability Guide](observability/README.md) - Monitoring and alerting

---

**Last Updated:** February 13, 2026  
**Status:** Production-ready, Milestone 2 in progress
