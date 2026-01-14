# Pydantic Environment Configuration Guide

**Status:** 🚧 **Available but Not Yet Implemented**  
**Created:** 2026-01-14  
**Purpose:** Comprehensive guide to the centralized Pydantic-based configuration system

---

## Table of Contents

1. [What is Pydantic-Settings?](#what-is-pydantic-settings)
2. [Why Use Pydantic-Settings?](#why-use-pydantic-settings)
3. [Current State vs. Target State](#current-state-vs-target-state)
4. [How It Works](#how-it-works)
5. [Configuration Structure](#configuration-structure)
6. [Usage Examples](#usage-examples)
7. [Migration Guide](#migration-guide)
8. [Best Practices](#best-practices)
9. [Frequently Asked Questions](#frequently-asked-questions)

---

## What is Pydantic-Settings?

**Pydantic-Settings** is an industry-standard Python library that extends Pydantic to manage application settings and configuration from environment variables. It provides:

- **Type-safe configuration**: Automatic validation and type coercion
- **Single source of truth**: All config in one place
- **IDE support**: Autocomplete and type hints
- **Clear documentation**: Self-documenting configuration schema
- **Validation at startup**: Fail fast if required config is missing

### Industry Adoption

Pydantic-Settings is used by major projects:
- **FastAPI** - Recommended in official docs
- **Prefect** - Workflow orchestration
- **Starlette** - ASGI framework
- **Many Fortune 500 companies** - Production deployments

It's considered the **Python community standard** for configuration management as of 2024-2026.

---

## Why Use Pydantic-Settings?

### Industry Best Practice Rationale

**1. Type Safety and Validation**

❌ **Old way** (manual parsing):
```python
# Scattered across 10+ files
def _truthy(val):
    return str(val).lower() in ("true", "1", "yes", "on")

ENABLE_BROADCAST = _truthy(os.getenv("ENABLE_BROADCAST", "0"))
MAX_ATTEMPTS = int(os.getenv("EXTRACTION_MAX_ATTEMPTS", "3"))
```

✅ **Pydantic way** (declarative):
```python
class AggregatorConfig(BaseSettings):
    enable_broadcast: bool = False  # Type-safe, validated
    extraction_max_attempts: int = 3  # Automatic int conversion
```

**Benefits:**
- No runtime type errors from `"true"` vs `True`
- No manual `int()` calls that can raise exceptions
- IDE autocomplete knows the type
- Mypy/Pyright can catch errors at development time

**2. Single Source of Truth**

❌ **Current problem:**
```
TutorDexAggregator/collector.py         - Has _env_first() helper
TutorDexAggregator/extract_worker.py    - Duplicates _truthy()
TutorDexAggregator/supabase_env.py      - Custom URL routing logic
TutorDexBackend/app.py                  - Different defaults
TutorDexBackend/redis_store.py          - Manual env parsing
... (10+ more files)
```

✅ **With Pydantic:**
```
shared/config.py - Single file, all config, clear defaults
```

**Benefits:**
- Find all config in one place (auditing, debugging)
- Change a default once, applies everywhere
- No inconsistent defaults across services
- Easy to see what's required vs. optional

**3. Fail Fast on Misconfiguration**

❌ **Current issue:**
```python
# Service starts successfully even if critical config is missing
supabase_url = os.getenv("SUPABASE_URL")  # Returns None if missing
# ... later (maybe hours later in production)
response = requests.post(supabase_url + "/rest/v1/table")  # TypeError!
```

✅ **With Pydantic:**
```python
class AggregatorConfig(BaseSettings):
    supabase_url: str  # No default = REQUIRED
    supabase_key: str  # No default = REQUIRED

# At startup:
config = AggregatorConfig()  # Raises ValidationError immediately if missing
```

**Benefits:**
- Catch config errors before deployment
- No silent failures hours later
- Clear error messages: "Field required: supabase_url"

**4. Self-Documenting Configuration**

✅ **Pydantic config is self-documenting:**
```python
class AggregatorConfig(BaseSettings):
    extraction_pipeline_version: str = Field(
        default="2026-01-02_det_time_v1",
        description="Pipeline version for extraction queue isolation"
    )
    extraction_max_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for failed extractions",
        ge=1,  # Must be >= 1
        le=10  # Must be <= 10
    )
```

**Benefits:**
- Config schema is documentation
- Can generate `.env.example` automatically
- Constraints are enforced (no negative retry counts)
- Docstrings live next to the config

**5. Environment-Specific Overrides**

```python
class BackendConfig(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    
    class Config:
        env_file = ".env"  # Load from .env file
        env_file_encoding = "utf-8"
        case_sensitive = False  # REDIS_URL or redis_url both work
        extra = "ignore"  # Don't fail on unknown env vars
```

**Load priority** (Pydantic-Settings default behavior):
1. Environment variables (highest priority)
2. `.env` file values
3. Default values in code (lowest priority)

This allows:
- Development: Use `.env` file
- Docker: Override with `docker-compose.yml` env vars
- CI/CD: Override with GitHub Secrets
- Production: Override with Kubernetes ConfigMaps

---

## Current State vs. Target State

### Current State (As of 2026-01-14)

**Status:** ✅ `shared/config.py` created but **not yet adopted**

The Pydantic configuration classes exist in `shared/config.py`:
- `AggregatorConfig` - 40+ configuration fields
- `BackendConfig` - 20+ configuration fields
- `WebsiteConfig` - 10+ configuration fields

**However:**
- No Python files currently import or use these classes
- All services still use manual `os.getenv()` parsing
- Existing `.env.example` files don't match the Pydantic schema

**Why not adopted yet?**
- Audit identified this as Priority 9 (medium priority)
- Higher priority tasks were completed first (Priorities 1-7)
- Migration requires touching 10+ files and testing each service

### Target State (After Migration)

**All services will:**
1. Import config from `shared/config.py`
2. Use typed config objects instead of `os.getenv()`
3. Validate configuration at startup
4. Share consistent defaults across services

**Example transformation:**

```python
# Before (extract_worker.py)
import os

SUPABASE_URL = os.getenv("SUPABASE_URL_DOCKER") or os.getenv("SUPABASE_URL")
PIPELINE_VERSION = os.getenv("EXTRACTION_PIPELINE_VERSION", "2026-01-02_det_time_v1")
ENABLE_BROADCAST = os.getenv("EXTRACTION_WORKER_BROADCAST", "1").lower() in ("1", "true")

# After
from shared.config import load_aggregator_config

config = load_aggregator_config()
# Now use: config.supabase_url, config.extraction_pipeline_version, config.enable_broadcast
```

---

## How It Works

### 1. Define Configuration Schema

In `shared/config.py`:

```python
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class AggregatorConfig(BaseSettings):
    # Required fields (no default)
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_key: str = Field(..., description="Supabase service role key")
    
    # Optional fields (with defaults)
    extraction_pipeline_version: str = Field(
        default="2026-01-02_det_time_v1",
        description="Pipeline version for extraction queue isolation"
    )
    
    enable_broadcast: bool = Field(
        default=False,
        description="Send assignments to broadcast Telegram channel"
    )
    
    # Optional with None
    telegram_api_id: Optional[str] = Field(
        default=None,
        description="Telegram API ID from my.telegram.org"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False  # Environment var names are case-insensitive
        extra = "ignore"  # Ignore unknown environment variables
```

### 2. Environment Variable Mapping

Pydantic automatically maps:

| Python Field | Environment Variable | Notes |
|--------------|---------------------|-------|
| `supabase_url` | `SUPABASE_URL` | Snake_case → UPPER_CASE |
| `extraction_pipeline_version` | `EXTRACTION_PIPELINE_VERSION` | Automatic conversion |
| `enable_broadcast` | `ENABLE_BROADCAST` | String → bool conversion |

**Boolean conversion rules:**
- True: `"1"`, `"true"`, `"True"`, `"TRUE"`, `"yes"`, `"on"`
- False: `"0"`, `"false"`, `"False"`, `"FALSE"`, `"no"`, `"off"`, `""`

### 3. Load Configuration

```python
from shared.config import load_aggregator_config

# Loads from environment + .env file
config = load_aggregator_config()

# Access with autocomplete and type hints
print(config.supabase_url)  # str
print(config.enable_broadcast)  # bool
```

### 4. Validation at Startup

```python
# If SUPABASE_URL is missing:
try:
    config = load_aggregator_config()
except ValidationError as e:
    print(e)
    # Output:
    # 1 validation error for AggregatorConfig
    # supabase_url
    #   field required (type=value_error.missing)
    sys.exit(1)
```

---

## Configuration Structure

### AggregatorConfig (40+ fields)

Used by: `TutorDexAggregator/*` (collector, workers)

**Categories:**
- **Supabase**: `supabase_url`, `supabase_key`
- **Pipeline**: `extraction_pipeline_version`, `schema_version`
- **Worker**: `extraction_max_attempts`, `extraction_worker_batch_size`, `extraction_worker_oneshot`
- **LLM**: `llm_api_url`, `llm_model_name`, `llm_circuit_breaker_threshold`
- **Side-effects**: `enable_broadcast`, `enable_dms`, `enable_persistence`
- **Telegram**: `telegram_api_id`, `telegram_api_hash`, `telegram_bot_token`
- **Observability**: `otel_enabled`, `log_level`, `prometheus_port`
- **Sentry**: `sentry_dsn`, `sentry_environment`

### BackendConfig (20+ fields)

Used by: `TutorDexBackend/app.py`

**Categories:**
- **Environment**: `app_env`, `app_host`, `app_port`
- **Auth**: `auth_required`, `firebase_admin_enabled`, `admin_api_key`
- **Database**: `supabase_url`, `supabase_key`, `redis_url`
- **Rate Limiting**: `rate_limit_enabled`, `rate_limit_default`
- **CORS**: `cors_allow_origins`
- **Observability**: `otel_enabled`, `log_level`
- **Sentry**: `sentry_dsn`, `sentry_environment`

### WebsiteConfig (10+ fields)

Used by: `TutorDexWebsite/` (frontend build)

**Categories:**
- **Firebase**: `firebase_api_key`, `firebase_auth_domain`, `firebase_project_id`
- **Backend**: `backend_api_url`
- **Sentry**: `sentry_dsn`, `sentry_environment`, `sentry_sample_rate`

**Special note:** Uses `env_prefix = "VITE_"` because Vite requires all env vars to start with `VITE_`.

---

## Usage Examples

### Example 1: Load Config in Worker

```python
# TutorDexAggregator/workers/extract_worker.py

from shared.config import load_aggregator_config

def main():
    # Load and validate configuration
    config = load_aggregator_config()
    
    # Use typed config (IDE knows the types!)
    print(f"Pipeline version: {config.extraction_pipeline_version}")
    print(f"Broadcast enabled: {config.enable_broadcast}")
    print(f"Max attempts: {config.extraction_max_attempts}")
    
    # Pass to functions
    worker = ExtractionWorker(
        supabase_url=config.supabase_url,
        pipeline_version=config.extraction_pipeline_version,
        batch_size=config.extraction_worker_batch_size
    )
    
    worker.run()

if __name__ == "__main__":
    main()
```

### Example 2: Use in FastAPI Backend

```python
# TutorDexBackend/app.py

from fastapi import FastAPI
from shared.config import load_backend_config

# Load at module level (cached)
config = load_backend_config()

# Use in app initialization
app = FastAPI(
    title="TutorDex Backend API",
    debug=(config.app_env == "dev")
)

# Use in endpoints
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "environment": config.app_env,
        "redis_configured": config.redis_url is not None
    }
```

### Example 3: Test with Custom Config

```python
# tests/test_worker.py

import pytest
from shared.config import AggregatorConfig

def test_worker_with_custom_config():
    # Override config for testing
    config = AggregatorConfig(
        supabase_url="http://test-supabase",
        supabase_key="test-key",
        enable_broadcast=False,  # Disable side-effects in tests
        enable_dms=False
    )
    
    worker = ExtractionWorker(config)
    # ... test worker behavior
```

### Example 4: Validate Config Before Deployment

```python
# scripts/validate_config.py

from shared.config import load_aggregator_config, load_backend_config

def validate_production_config():
    """Validate that production config is complete."""
    try:
        agg_config = load_aggregator_config()
        backend_config = load_backend_config()
        
        # Additional business logic validation
        if backend_config.app_env == "production":
            assert backend_config.auth_required, "Auth must be enabled in production"
            assert backend_config.admin_api_key, "Admin API key required in production"
            assert backend_config.firebase_admin_credentials_path, "Firebase credentials required"
        
        print("✅ Configuration validation passed")
        return True
        
    except ValidationError as e:
        print(f"❌ Configuration validation failed:\n{e}")
        return False

if __name__ == "__main__":
    import sys
    sys.exit(0 if validate_production_config() else 1)
```

---

## Migration Guide

### Phase 1: Preparation (No Code Changes)

**Step 1: Understand current config**
```bash
# Find all environment variable usage
grep -r "os.getenv\|os.environ" TutorDexAggregator/ TutorDexBackend/ --include="*.py"
```

**Step 2: Compare with Pydantic schema**
- Review `shared/config.py`
- Identify any missing fields
- Check for default value mismatches

### Phase 2: Migrate One Service at a Time

**Recommended order:**
1. Start with **extraction worker** (clear boundaries)
2. Then **collector** (simpler)
3. Then **backend** (more complex)
4. Finally **website** (different toolchain)

**For each service:**

**Step 1: Add import**
```python
from shared.config import load_aggregator_config
```

**Step 2: Load config at module level**
```python
# At top of file, after imports
config = load_aggregator_config()
```

**Step 3: Replace os.getenv() calls**
```python
# Before
SUPABASE_URL = os.getenv("SUPABASE_URL")
ENABLE_BROADCAST = os.getenv("ENABLE_BROADCAST", "0").lower() in ("1", "true")

# After
supabase_url = config.supabase_url
enable_broadcast = config.enable_broadcast
```

**Step 4: Update function signatures**
```python
# Before
def process_message(supabase_url, pipeline_version, enable_broadcast):
    pass

# After (pass config object)
def process_message(config: AggregatorConfig):
    # Access config.supabase_url, config.pipeline_version, etc.
    pass
```

**Step 5: Test thoroughly**
```bash
# Run service locally
python TutorDexAggregator/workers/extract_worker.py

# Check that all env vars are loaded correctly
# Test with different .env configurations
```

### Phase 3: Update .env.example Files

**Generate from schema:**
```python
# scripts/generate_env_example.py (future enhancement)

from shared.config import AggregatorConfig
from pydantic.fields import FieldInfo

def generate_env_example(config_class):
    """Generate .env.example from Pydantic config."""
    for field_name, field in config_class.__fields__.items():
        env_var = field_name.upper()
        default = field.default if field.default is not None else ""
        description = field.field_info.description or ""
        
        print(f"# {description}")
        print(f"{env_var}={default}")
        print()

generate_env_example(AggregatorConfig)
```

### Phase 4: Add Validation to CI/CD

```yaml
# .github/workflows/validate-config.yml

name: Validate Configuration
on: [push, pull_request]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install pydantic-settings
      - name: Validate config schema
        run: |
          python scripts/validate_config.py
```

---

## Best Practices

### 1. Required vs. Optional Fields

**Use `...` (Ellipsis) for required fields:**
```python
supabase_url: str = Field(..., description="Required: Supabase URL")
```

**Use `None` for truly optional fields:**
```python
sentry_dsn: Optional[str] = Field(None, description="Optional: Sentry DSN")
```

**Use defaults for optional fields with sensible fallbacks:**
```python
log_level: str = Field("INFO", description="Logging level")
```

### 2. Validation Rules

**Use Pydantic validators for complex validation:**
```python
from pydantic import validator, HttpUrl

class AggregatorConfig(BaseSettings):
    supabase_url: HttpUrl  # Validates it's a valid URL
    
    extraction_max_attempts: int = Field(default=3, ge=1, le=10)  # Between 1-10
    
    @validator('extraction_pipeline_version')
    def validate_pipeline_version(cls, v):
        # Custom validation logic
        if not v.startswith('2026-'):
            raise ValueError('Pipeline version must start with 2026-')
        return v
```

### 3. Secrets Management

**Never put secrets in defaults:**
```python
# ❌ BAD
supabase_key: str = "super-secret-key-12345"

# ✅ GOOD
supabase_key: str = Field(..., description="Required: Get from Supabase dashboard")
```

**Mark sensitive fields in description:**
```python
admin_api_key: Optional[str] = Field(
    None, 
    description="🔒 SECRET: Admin API key (required in production)"
)
```

### 4. Environment-Specific Defaults

**Use sensible defaults for development:**
```python
llm_api_url: str = Field(
    default="http://host.docker.internal:1234",
    description="LLM API URL (use host.docker.internal for Docker)"
)

redis_url: str = Field(
    default="redis://localhost:6379/0",
    description="Redis URL (use redis://redis:6379/0 in Docker)"
)
```

### 5. Documentation in Descriptions

**Good descriptions:**
- Explain what the field is for
- Mention where to get the value
- Note any special formatting requirements
- Indicate if it's environment-specific

```python
firebase_admin_credentials_path: Optional[str] = Field(
    default=None,
    description="Path to Firebase service account JSON file. "
                "Get from Firebase Console → Project Settings → Service Accounts. "
                "In Docker: /run/secrets/firebase-admin-service-account.json"
)
```

### 6. Grouping Related Config

**Use comments to group related fields:**
```python
class AggregatorConfig(BaseSettings):
    # Supabase persistence
    supabase_url: str = Field(...)
    supabase_key: str = Field(...)
    
    # Pipeline versioning
    extraction_pipeline_version: str = Field(...)
    schema_version: str = Field(...)
    
    # LLM configuration
    llm_api_url: str = Field(...)
    llm_model_name: str = Field(...)
```

### 7. Config Caching

**Load config once at module level:**
```python
# ✅ Good: Load once
from shared.config import load_aggregator_config

config = load_aggregator_config()  # Cached

def function_a():
    print(config.supabase_url)

def function_b():
    print(config.supabase_url)  # Same instance
```

**Avoid loading in every function:**
```python
# ❌ Bad: Loads multiple times
def function_a():
    config = load_aggregator_config()  # Loads again!
    print(config.supabase_url)
```

---

## Frequently Asked Questions

### Q1: Why not just use python-decouple or environs?

**A:** Pydantic-Settings is the industry standard as of 2024-2026 because:
- **Type safety**: Native Pydantic validation (same as FastAPI)
- **IDE support**: Better autocomplete and type hints
- **Integration**: Works seamlessly with FastAPI and other Pydantic-based tools
- **Ecosystem**: Largest community and most documentation
- **Future-proof**: Actively maintained, backed by Pydantic maintainers

Other libraries are fine, but Pydantic-Settings is the Python community consensus.

### Q2: What about backwards compatibility?

**A:** During migration, both approaches can coexist:

```python
# Gradual migration approach
try:
    from shared.config import load_aggregator_config
    config = load_aggregator_config()
    SUPABASE_URL = config.supabase_url
except ImportError:
    # Fallback to old approach
    import os
    SUPABASE_URL = os.getenv("SUPABASE_URL")
```

### Q3: How do I handle Docker vs. host environments?

**A:** Use environment variable overrides:

**.env file (development on host):**
```bash
SUPABASE_URL=http://127.0.0.1:54321
REDIS_URL=redis://localhost:6379/0
```

**docker-compose.yml (Docker):**
```yaml
services:
  aggregator:
    environment:
      - SUPABASE_URL=http://supabase-kong:8000  # Override
      - REDIS_URL=redis://redis:6379/0  # Override
```

The Docker env vars take precedence over `.env` file.

### Q4: Can I generate .env.example from the schema?

**A:** Yes! (Future enhancement)

```python
# scripts/generate_env_example.py

from shared.config import AggregatorConfig
import inspect

def generate_env_example(config_class):
    """Generate .env.example from Pydantic config."""
    lines = []
    lines.append(f"# {config_class.__doc__}")
    lines.append("")
    
    for field_name, field in config_class.__fields__.items():
        env_var = field_name.upper()
        
        # Get description
        if field.field_info.description:
            lines.append(f"# {field.field_info.description}")
        
        # Get default or mark as required
        if field.required:
            lines.append(f"{env_var}=  # REQUIRED")
        elif field.default is not None:
            lines.append(f"{env_var}={field.default}")
        else:
            lines.append(f"{env_var}=")
        
        lines.append("")
    
    return "\n".join(lines)

print(generate_env_example(AggregatorConfig))
```

### Q5: What about secrets rotation?

**A:** Pydantic-Settings reads env vars at startup. To rotate secrets:

1. Update environment variable (Kubernetes secret, Docker env, etc.)
2. Restart service
3. New config is loaded with new secret

For zero-downtime rotation, use rolling deployments.

### Q6: How do I test with different configs?

**A:** Create config instances in tests:

```python
def test_with_custom_config():
    config = AggregatorConfig(
        supabase_url="http://test",
        supabase_key="test-key",
        enable_broadcast=False  # Disable side-effects
    )
    
    # Use config in test
    worker = ExtractionWorker(config)
    assert worker.enable_broadcast == False
```

Or use environment variable overrides:

```python
import os

def test_with_env_override():
    os.environ["ENABLE_BROADCAST"] = "false"
    config = load_aggregator_config()
    assert config.enable_broadcast == False
```

### Q7: What if I need config not in shared/config.py?

**A:** Add it to the appropriate config class:

```python
# In shared/config.py

class AggregatorConfig(BaseSettings):
    # ... existing fields ...
    
    # Add new field
    new_feature_enabled: bool = Field(
        default=False,
        description="Enable new experimental feature"
    )
```

Submit a PR with the change. Config schema is versioned with the code.

---

## Summary

### Key Takeaways

1. **Pydantic-Settings is the industry standard** for Python configuration management
2. **Type safety prevents runtime errors** from misconfiguration
3. **Single source of truth** eliminates inconsistencies
4. **Fail fast at startup** catches errors before they cause problems
5. **Self-documenting schema** makes onboarding easier

### Current Status

- ✅ `shared/config.py` exists with complete schema
- ❌ Not yet adopted by any service
- ⏳ Migration planned as Priority 9 in audit

### Next Steps

When migrating to Pydantic-Settings:
1. Start with one service (extraction worker recommended)
2. Test thoroughly before moving to next service
3. Update `.env.example` files to match schema
4. Add config validation to CI/CD
5. Document any service-specific config quirks

### Further Reading

- [Pydantic-Settings Documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
- [FastAPI Configuration Guide](https://fastapi.tiangolo.com/advanced/settings/)
- [12-Factor App: Config](https://12factor.net/config)
- [TutorDex Audit Report](./CODEBASE_QUALITY_AUDIT_2026-01.md) - Priority 9

---

**Document Status:** Living document, will be updated as migration progresses.  
**Questions?** Open an issue or discussion on GitHub.
