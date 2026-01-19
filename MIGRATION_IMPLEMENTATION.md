# Dual Environment Migration - Implementation Complete

## What Was Done

This PR implements the code changes required for the dual-environment migration plan documented in `docs/DUAL_ENVIRONMENT_MIGRATION_PLAN.md`.

### Changes Implemented

1. **docker-compose.yml modifications**
   - Added `APP_ENV` environment variable to all application services
   - Parameterized external ports (BACKEND_PORT, PROMETHEUS_PORT, TEMPO ports)
   - Removed hardcoded network names (auto-generated based on compose project)
   - Parameterized Supabase network name (SUPABASE_NETWORK)
   - Updated OTEL collector to use APP_ENV

2. **Safety guardrails**
   - Added `validate_environment_integrity()` in `shared/config.py`
   - Validates prod vs staging Supabase URLs (port-based: 54321 vs 54322)
   - Validates production auth requirements
   - Integrated validation in collector, worker, and backend startup

3. **Broadcast and DM safety checks**
   - Added `_validate_broadcast_safety()` to prevent staging→prod broadcasts
   - Added `_validate_dm_safety()` to warn about staging DMs

4. **Deployment scripts**
   - Created 7 bash scripts for staging/prod management
   - All scripts are executable and syntax-validated

## What's Next (Manual Steps Required)

### Prerequisites
- Windows host with Docker Desktop
- Separate Supabase instances (staging + prod)
- Test Telegram bots for staging
- Backed up production data

### Deployment Steps

Follow sections 7-8 of the migration plan:

#### 1. Create Environment Files

Create `.env.staging` with staging-specific values:
```bash
APP_ENV=staging
COMPOSE_PROJECT_NAME=tutordex-staging
BACKEND_PORT=8001
PROMETHEUS_PORT=9091
GRAFANA_PORT=3301
SUPABASE_NETWORK=supabase_staging_default
SUPABASE_URL=http://localhost:54322  # Staging Supabase
# ... plus all other env vars with staging credentials
```

Create `.env.prod` with production values:
```bash
APP_ENV=prod
COMPOSE_PROJECT_NAME=tutordex-prod
BACKEND_PORT=8000
PROMETHEUS_PORT=9090
GRAFANA_PORT=3300
SUPABASE_NETWORK=supabase_default
SUPABASE_URL=http://localhost:54321  # Production Supabase
# ... plus all other env vars with production credentials
```

#### 2. Deploy Staging Supabase

```bash
# Deploy separate Supabase instance for staging
cd /path/to/supabase-staging
docker compose -p supabase-staging up -d
```

#### 3. Test Staging Environment

```bash
# Validate staging env file
./scripts/validate_env.sh .env.staging

# Deploy staging
./scripts/deploy_staging.sh

# Verify staging works
curl http://localhost:8001/health
```

#### 4. Production Migration (During Maintenance Window)

```bash
# Stop current production
docker compose down

# Validate prod env file
./scripts/validate_env.sh .env.prod

# Deploy production with new structure
./scripts/deploy_prod.sh

# Verify production works
curl http://localhost:8000/health
```

## Safety Features

The code now prevents these catastrophic errors:

❌ **Blocked**: APP_ENV=prod with staging Supabase URL (port :54322)
❌ **Blocked**: APP_ENV=staging with production Supabase URL (port :54321)
❌ **Blocked**: Production without AUTH_REQUIRED=true
❌ **Blocked**: Production without FIREBASE_ADMIN_ENABLED=true
❌ **Blocked**: Production with weak ADMIN_API_KEY
⚠️ **Warning**: Staging with broadcasts enabled
⚠️ **Warning**: Staging with DMs enabled

## Verification Completed

✅ All Python files compile successfully
✅ All bash scripts have valid syntax
✅ docker-compose.yml YAML is valid
✅ Environment validation logic tested

## Commands Quick Reference

```bash
# Staging
./scripts/deploy_staging.sh      # Deploy staging
./scripts/stop_staging.sh        # Stop staging
./scripts/logs_staging.sh        # View logs

# Production
./scripts/deploy_prod.sh         # Deploy production (with confirmation)
./scripts/stop_prod.sh           # Stop production (with confirmation)
./scripts/logs_prod.sh           # View logs

# Validation
./scripts/validate_env.sh .env.staging   # Validate staging config
./scripts/validate_env.sh .env.prod      # Validate production config

# Docker commands (if needed)
docker compose -p tutordex-staging ps    # List staging containers
docker compose -p tutordex-prod ps       # List production containers
docker volume ls | grep tutordex         # List volumes
docker network ls | grep tutordex        # List networks
```

## Important Notes

- **DO NOT** copy production secrets to staging
- **DO NOT** use production Telegram bots in staging
- **DO NOT** skip the validation scripts
- **ALWAYS** test in staging first
- **ALWAYS** use deployment scripts (not raw docker compose)

## Rollback Plan

If something goes wrong, see section 8 of the migration plan for the complete rollback procedure.
