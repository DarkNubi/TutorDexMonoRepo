# GitHub Copilot Instructions for TutorDex MonoRepo

## Project Overview

TutorDex is a tuition assignment aggregator that collects, parses, and distributes tutor assignment posts from multiple Telegram channels. The system matches assignments with tutors based on their preferences and delivers personalized notifications.

### Architecture

This is a **monorepo** containing three main components:

1. **TutorDexAggregator** (Python) - Telegram message collector and LLM-based parser
2. **TutorDexBackend** (Python FastAPI) - Matching engine and API service
3. **TutorDexWebsite** (JavaScript/TypeScript + Vite) - Static website with Firebase Auth

Additional components:
- **shared/** - Shared Python modules for contracts and taxonomy
- **observability/** - Prometheus, Grafana, Loki, Alertmanager stack
- **tests/** - Repository-level test suite
- **scripts/** - Utility scripts for validation and deployment

## Technology Stack

### Backend (Python)
- **Framework**: FastAPI, Uvicorn
- **Database**: Redis (matching preferences), Supabase (PostgreSQL for persistence)
- **Message Queue**: Telegram API (Telethon), extraction queue in Supabase
- **AI/ML**: Local LLM API (OpenAI-compatible, typically LM Studio)
- **Observability**: Prometheus metrics, OpenTelemetry, structured logging
- **Authentication**: Firebase Admin SDK (token verification)

### Frontend (JavaScript/TypeScript)
- **Build Tool**: Vite
- **Framework**: React with TypeScript
- **Authentication**: Firebase Auth (email/password, Google sign-in)
- **Deployment**: Firebase Hosting
- **UI Libraries**: Framer Motion, Lucide React

### Infrastructure
- **Containerization**: Docker + Docker Compose
- **Orchestration**: Docker Compose (development and production)
- **Networking**: Tailscale for secure deployment
- **Self-hosted Services**: Supabase (PostgreSQL), Redis

## Development Setup

### Prerequisites
- Python 3.9+ with pip
- Node.js 18+ with npm
- Docker Desktop (for local development)
- Firebase CLI (`npm i -g firebase-tools`)
- Local LLM server (LM Studio or compatible)

### Environment Configuration

Each component requires a `.env` file. Use the `.env.example` files as templates:
- `TutorDexAggregator/.env.example` → `TutorDexAggregator/.env`
- `TutorDexBackend/.env.example` → `TutorDexBackend/.env`
- `TutorDexWebsite/.env.example` → `TutorDexWebsite/.env`

**Important**: Never commit `.env` files or secrets to git.

### Local Development

#### Using Docker (Recommended)
```bash
# Start all services (backend, aggregator, observability)
docker compose up -d --build

# View logs
docker compose logs -f

# Stop all services
docker compose down
```

#### Manual Setup

**TutorDexAggregator**:
```bash
cd TutorDexAggregator
pip install -r requirements.txt
python collector.py tail  # Start collector
python workers/extract_worker.py  # Start extraction worker
```

**TutorDexBackend**:
```bash
cd TutorDexBackend
pip install -r requirements.txt
uvicorn TutorDexBackend.app:app --host 0.0.0.0 --port 8000
```

**TutorDexWebsite**:
```bash
cd TutorDexWebsite
npm install
npm run dev  # Development server
npm run build  # Production build
firebase emulators:start --only hosting  # Firebase emulator
```

## Code Conventions

### Python

#### Style
- Follow PEP 8 conventions
- Use type hints for function parameters and return values
- Use `from __future__ import annotations` for forward references
- Prefer explicit over implicit (clear variable names, no magic values)

#### Naming
- Files: `snake_case.py`
- Functions/variables: `snake_case`
- Classes: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- Private members: prefix with `_`

#### Imports
- Standard library imports first
- Third-party imports second
- Local imports last
- Use absolute imports from repo root (e.g., `from TutorDexAggregator.extract_key_info import ...`)

#### Error Handling
- Use structured logging (`logger.error()`, `logger.warning()`)
- Catch specific exceptions rather than bare `except:`
- Provide context in error messages
- Return status indicators rather than raising for expected failures

#### Logging
- Use the configured logger (typically from `logging_setup.py`)
- Log levels: `DEBUG` for verbose, `INFO` for key events, `WARNING` for issues, `ERROR` for failures
- Include relevant context (IDs, values) in log messages
- Use structured logging (JSON format in production)

### JavaScript/TypeScript

#### Style
- Use ES6+ features (arrow functions, destructuring, template literals)
- Prefer `const` over `let`, avoid `var`
- Use TypeScript types for new code
- Follow existing patterns in the codebase

#### Naming
- Files: `camelCase.js` or `kebab-case.js` depending on context
- Functions/variables: `camelCase`
- Components: `PascalCase`
- Constants: `UPPER_SNAKE_CASE` or `camelCase` depending on context

#### React Patterns
- Functional components with hooks
- Use Framer Motion for animations
- Keep components focused and composable

## Testing

### Python Tests
Located in `tests/` directory:
```bash
# Run all tests (requires pytest)
pytest tests/

# Run specific test
pytest tests/test_signals_builder.py

# Syntax check (recommended for CI)
python -m py_compile TutorDexAggregator/*.py TutorDexBackend/*.py
./check_python.sh
```

### Test Patterns
- Use descriptive test names: `test_<what>_<scenario>_<expected>`
- Mock external dependencies (Supabase, Redis, LLM API)
- Test both success and failure cases
- Include edge cases (empty input, malformed data)

### Validation Scripts
- `scripts/smoke_test.py` - End-to-end health checks
- `shared/contracts/validate_contracts.py` - Contract validation
- `shared/taxonomy/subjects/validate_taxonomy.py` - Taxonomy validation

## Build and Deployment

### CI/CD Workflows

Located in `.github/workflows/`:
- `deploy.yml` - Deploys to production via Tailscale SSH after PR merge
- `firebase-hosting.yml` - Deploys website to Firebase Hosting
- `taxonomy-validate.yml` - Validates taxonomy on changes
- `contracts-validate.yml` - Validates contracts on changes

### Production Deployment

Production runs on a Windows server via Docker Compose:
1. PR is merged to `main`
2. GitHub Actions triggers `deploy.yml`
3. Server pulls latest code via git
4. Docker Compose rebuilds and restarts services

### Website Deployment

Firebase Hosting auto-deploys on push to `main`:
```bash
cd TutorDexWebsite
npm run build
firebase deploy --only hosting
```

## Key Patterns and Best Practices

### Data Flow

1. **Ingestion**: Telegram messages → `collector.py` → Supabase raw table
2. **Extraction**: Extraction worker → LLM API → Parse & enrich → Supabase assignments table
3. **Matching**: Assignment → Backend `/match/payload` → Redis → Matching tutors
4. **Distribution**: Matched tutors → Telegram DM bot → Individual notifications

### Message Processing Pipeline

- **collector.py**: Reads Telegram, writes raw messages, enqueues extraction jobs
- **extract_worker.py**: Claims jobs, calls LLM, validates output, persists to Supabase
- **Deterministic hardening**: Normalizes text, validates structure, computes matching signals
- **Broadcasting**: Sends to aggregator channel (optional)
- **DM delivery**: Sends personalized messages to matched tutors (optional)

### Configuration Management

- Use environment variables for all configuration
- Provide sensible defaults in code
- Document all env vars in README files and `.env.example`
- Use `_env_first()` helper for fallback chains

### Secrets Management

- Never commit secrets to git (use `.gitignore`)
- Store secrets in `.env` files (local) or GitHub Secrets (CI)
- Use Firebase Admin service account JSON (store in `secrets/` directory, gitignored)
- Use environment-specific URLs (Docker vs host)

### Error Recovery

- Retry with exponential backoff for transient failures
- Log failures with context for debugging
- Use extraction queue for resilience (failed jobs can be retried)
- Monitor via observability stack (Prometheus alerts)

### Performance Considerations

- Use connection pooling (Redis, Supabase)
- Cache LLM results when possible
- Limit DM recipients per assignment (`DM_MAX_RECIPIENTS`)
- Use pagination for large result sets
- Monitor cardinality (see `observability/CARDINALITY.md`)

## Common Tasks

### Adding a New Python Dependency

1. Add to appropriate `requirements.txt`
2. Test locally: `pip install <package>`
3. Rebuild Docker image: `docker compose build <service>`
4. Update documentation if needed

### Adding a New API Endpoint (Backend)

1. Define route in `TutorDexBackend/app.py`
2. Add validation with Pydantic models
3. Implement handler function
4. Add metrics/logging
5. Test with curl or Postman
6. Document in README

### Adding a New LLM Extraction Field

1. Update prompt in `TutorDexAggregator/message_examples/`
2. Modify parser in `extract_key_info.py`
3. Update Supabase schema if persisting
4. Add validation in `hard_validator.py`
5. Update tests
6. Consider deterministic fallback

### Modifying Matching Logic

1. Update scoring in `TutorDexBackend/matching.py`
2. Update preference schema in `redis_store.py`
3. Test with sample payloads
4. Update API documentation
5. Consider backward compatibility

## Observability

### Accessing Services

- Grafana: `http://localhost:3300` (admin/admin)
- Prometheus: `http://localhost:9090`
- Alertmanager: `http://localhost:9093`
- Backend API: `http://localhost:8000/docs` (Swagger UI)

### Monitoring

- Check service health: `GET /health` endpoints
- View metrics: Prometheus `/metrics` endpoints
- View logs: Grafana → Explore → Loki
- Check alerts: Alertmanager UI

### Debugging

1. Check logs in Grafana/Loki or `docker compose logs`
2. Verify environment variables are set correctly
3. Test connectivity to external services (Supabase, Redis, LLM API)
4. Use smoke test: `python scripts/smoke_test.py`
5. Check observability health: `./observability/doctor.sh`

## Important Files and Directories

- `docker-compose.yml` - Main orchestration file
- `TutorDexAggregator/collector.py` - Telegram message collector
- `TutorDexAggregator/workers/extract_worker.py` - Extraction queue worker
- `TutorDexAggregator/extract_key_info.py` - LLM extraction logic
- `TutorDexBackend/app.py` - FastAPI application
- `TutorDexBackend/matching.py` - Tutor matching algorithm
- `TutorDexWebsite/src/` - Website source code
- `shared/contracts/` - Shared data contracts
- `shared/taxonomy/subjects/` - Subject taxonomy and canonicalization
- `observability/` - Full observability stack configuration

## Resources

- Main documentation in component README files
- System design: `docs/SYSTEM_INTERNAL.md`
- Signals documentation: `docs/signals.md`
- Time availability: `docs/time_availability.md`
- Recovery/catchup: `docs/recovery_catchup.md`
- Observability runbooks: `observability/runbooks/`

## When Making Changes

1. **Understand the context**: Read relevant README and documentation
2. **Follow conventions**: Match existing code style and patterns
3. **Test locally**: Validate changes before committing
4. **Minimal changes**: Make surgical, focused modifications
5. **Update documentation**: Keep READMEs in sync with code changes
6. **Check CI**: Ensure all workflows pass
7. **Monitor production**: Watch observability dashboards after deployment

## Common Pitfalls to Avoid

- Don't hardcode URLs or credentials
- Don't commit `.env` files or secrets
- Don't break backward compatibility without migration
- Don't skip validation or error handling
- Don't ignore failing tests or linting
- Don't use global state or singletons unnecessarily
- Don't make network calls in hot paths without caching
- Don't log sensitive data (PII, credentials)
- Don't use blocking calls in async contexts
- Don't assume external services are always available

## Getting Help

- Check component-specific README files first
- Review relevant documentation in `docs/`
- Check observability dashboards for runtime issues
- Review existing code for similar patterns
- Test changes in Docker environment before deployment
