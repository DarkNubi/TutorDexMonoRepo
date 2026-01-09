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

## 📋 Next Steps: Recommended Milestones

We've completed a comprehensive project review and identified the next three strategic milestones:

### 📊 [Milestone 2: Product Analytics & Loop Validation](MILESTONE_SUMMARY.md#-milestone-2-product-analytics--loop-validation-2-3-weeks) (2-3 weeks)
- Implement frontend analytics events
- Build tutor feedback UI (report scam/filled/no-reply)
- Create KPI dashboard to understand tutor behavior
- **Goal:** Validate product-market fit with real usage data

### 🚀 [Milestone 3: One-Click Apply & Application Flow](MILESTONE_SUMMARY.md#-milestone-3-one-click-apply--application-flow-3-4-weeks) (3-4 weeks)
- Build one-click apply system
- Route applications through TutorDex
- Track application outcomes
- **Goal:** Build agency leverage and data moat

### 💰 [Milestone 4: Soft Monetization & User Tiers](MILESTONE_SUMMARY.md#-milestone-4-soft-monetization--tiers-2-3-weeks) (2-3 weeks)
- Implement user tiers (free/supporter/premium)
- Create payment flow (start with manual PayNow)
- Add premium features (instant DMs, tighter filters, historical data)
- **Goal:** Validate willingness to pay and offset infrastructure costs

---

## 📚 Documentation

**Quick Start:**
- [Visual Roadmap](MILESTONES_VISUAL.md) - ASCII diagram with week-by-week breakdown
- [Executive Summary](MILESTONE_SUMMARY.md) - High-level overview (5 min read)
- [Full Milestone Details](NEXT_MILESTONES.md) - Complete implementation guide (25 min read)

**Component Documentation:**
- [TutorDexAggregator](TutorDexAggregator/README.md) - Message collector and LLM parser
- [TutorDexBackend](TutorDexBackend/README.md) - FastAPI matching engine and API
- [TutorDexWebsite](TutorDexWebsite/README.md) - React + Firebase website
- [Observability](observability/README.md) - Prometheus, Grafana, Loki stack
- [Duplicate Detection](docs/DUPLICATE_DETECTION_SUMMARY.md) - Cross-agency duplicate assignment handling
- [Assignment Rating System](docs/assignment_rating_system.md) - **NEW:** Adaptive threshold and quality scoring

**Strategic Context:**
- [Strategic Vision](TutorDex%20background%20info.txt) - Business goals and monetization strategy
- [Observability Status](TODO_OBSERVABILITY.md) - Monitoring and analytics capabilities
- [Duplicate Detection Plan](docs/DUPLICATE_DETECTION.md) - Comprehensive plan for handling duplicate assignments

---

## 🚀 Quick Start (Development)

### Prerequisites
- Python 3.9+ with pip
- Node.js 18+ with npm
- Docker Desktop (recommended)
- Local LLM server (LM Studio or compatible)

### Start All Services

```bash
# Clone the repository
git clone https://github.com/DarkNubi/TutorDexMonoRepo.git
cd TutorDexMonoRepo

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

### Access Services

- **Backend API:** http://localhost:8000/docs (Swagger UI)
- **Website:** http://localhost:5173 (development) or deploy to Firebase
- **Grafana:** http://localhost:3300 (admin/admin)
- **Prometheus:** http://localhost:9090
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
- Prometheus, Grafana, Loki, Alertmanager
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
- **Logs:** Collected by Promtail, stored in Loki, queried in Grafana
- **Alerts:** Defined in Prometheus, routed by Alertmanager to Telegram

See [observability/CAPABILITIES.md](observability/CAPABILITIES.md) for full details.

---

## 🎯 Current Priority: Start Milestone 2.1

**This Week:** Implement frontend analytics events

Add event tracking to the website:
```javascript
// TutorDexWebsite/src/page-assignments.js
await trackEvent({
  event_type: "assignment_list_view",
  meta: { filters, sort, surface: "website" }
});

await trackEvent({
  event_type: "assignment_view",
  assignment_external_id: assignment.external_id,
  agency_name: assignment.agency_name
});
```

See [MILESTONES_VISUAL.md](MILESTONES_VISUAL.md#what-to-build-first-this-week) for implementation guide.

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

- [Visual Roadmap](MILESTONES_VISUAL.md) - Week-by-week breakdown
- [Executive Summary](MILESTONE_SUMMARY.md) - High-level overview
- [Full Milestone Details](NEXT_MILESTONES.md) - Complete implementation guide
- [Component READMEs](TutorDexAggregator/README.md) - Detailed setup instructions
- [Observability Guide](observability/README.md) - Monitoring and alerting

---

**Last Updated:** January 8, 2026  
**Status:** Production-ready, Milestone 2 in progress
