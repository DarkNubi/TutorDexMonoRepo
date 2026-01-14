# Rate Limiting Integration Guide

This document explains how to integrate rate limiting into the TutorDex Backend API.

## Overview

Rate limiting protects the API from abuse and ensures fair usage across all clients. We use `slowapi` (FastAPI-compatible rate limiting) with Redis backend for distributed rate limiting.

## Configuration

### Environment Variables

```bash
# Enable/disable rate limiting
RATE_LIMIT_ENABLED=1  # 1=enabled, 0=disabled

# Redis URL for rate limit storage (optional, falls back to in-memory)
REDIS_URL=redis://localhost:6379/0
```

### Rate Limit Presets

The middleware provides several presets:

- **PUBLIC_STRICT**: 30/minute - For expensive queries
- **PUBLIC_MODERATE**: 100/minute - For typical public endpoints
- **PUBLIC_GENEROUS**: 300/minute - For lightweight endpoints
- **AUTH_DEFAULT**: 300/minute - For authenticated users
- **AUTH_GENEROUS**: 1000/minute - For high-volume operations
- **ADMIN_DEFAULT**: 1000/minute - For admin operations

## Integration into app.py

### Step 1: Import Rate Limiting

```python
from TutorDexBackend.middleware.rate_limit import (
    get_limiter,
    get_rate_limit_middleware,
    rate_limit_exceeded_handler,
    RateLimits,
)
from slowapi.errors import RateLimitExceeded

limiter = get_limiter()
```

### Step 2: Add Middleware and Exception Handler

```python
# Add to app initialization
app = FastAPI(title="TutorDex Backend", version="0.1.0")

# Add rate limiting state
app.state.limiter = limiter

# Add rate limit middleware
app.add_middleware(get_rate_limit_middleware(), limiter=limiter)

# Add exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
```

### Step 3: Apply Rate Limits to Endpoints

#### Public Endpoints (No Auth Required)

```python
from fastapi import Request

# Expensive endpoint (strict limit)
@app.get("/assignments/search")
@limiter.limit(RateLimits.PUBLIC_STRICT)
async def search_assignments(request: Request, q: str):
    # Complex search query
    return {"results": [...]}

# Typical public endpoint (moderate limit)
@app.get("/assignments")
@limiter.limit(RateLimits.PUBLIC_MODERATE)
async def list_assignments(request: Request):
    # Standard list operation
    return {"assignments": [...]}

# Lightweight endpoint (generous limit)
@app.get("/assignments/facets")
@limiter.limit(RateLimits.PUBLIC_GENEROUS)
async def get_facets(request: Request):
    # Cached or lightweight query
    return {"facets": {...}}
```

#### Authenticated Endpoints

```python
# Authenticated endpoint (generous limit)
@app.get("/me/tutor")
@limiter.limit(RateLimits.AUTH_DEFAULT)
async def get_my_tutor_profile(request: Request):
    uid = await _auth_service.require_uid(request)
    # User-specific operation
    return {"profile": {...}}
```

#### Admin Endpoints

```python
# Admin endpoint (very generous limit)
@app.get("/admin/stats")
@limiter.limit(RateLimits.ADMIN_DEFAULT)
async def get_admin_stats(request: Request):
    await _auth_service.require_admin(request)
    # Admin-only operation
    return {"stats": {...}}
```

#### Health Endpoints (No Rate Limit)

```python
# Health check - no rate limit needed
@app.get("/health")
async def health():
    return {"ok": True}
```

### Step 4: Custom Rate Limits

For specific needs, you can define custom limits:

```python
# Custom limit: 10 requests per 5 minutes
@app.post("/expensive-operation")
@limiter.limit("10/5minutes")
async def expensive_operation(request: Request):
    # Very expensive operation
    return {"status": "processing"}
```

## Response Headers

When rate limiting is active, responses include:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1640000000
```

## Error Response

When rate limit is exceeded (429 status):

```json
{
  "error": "rate_limit_exceeded",
  "detail": "Too many requests. Please try again later.",
  "retry_after": 60
}
```

## Testing Rate Limits

### Unit Tests

```python
from fastapi.testclient import TestClient

def test_rate_limit():
    client = TestClient(app)
    
    # Make requests up to limit
    for i in range(100):
        response = client.get("/assignments")
        assert response.status_code == 200
    
    # Next request should be rate limited
    response = client.get("/assignments")
    assert response.status_code == 429
    assert "retry_after" in response.json()
```

### Manual Testing

```bash
# Test with curl
for i in {1..150}; do
    curl -w "%{http_code}\n" http://localhost:8000/assignments
done

# Should see 200 responses followed by 429
```

## Monitoring

Rate limit metrics are exposed via Prometheus:

```promql
# Rate limit hits (429 responses)
rate(http_requests_total{status_code="429"}[5m])

# Success rate
rate(http_requests_total{status_code="200"}[5m]) / rate(http_requests_total[5m])
```

## Disabling Rate Limiting

To disable rate limiting (e.g., for testing):

```bash
export RATE_LIMIT_ENABLED=0
```

Or in `.env`:
```
RATE_LIMIT_ENABLED=0
```

## Redis vs In-Memory Storage

### With Redis (Recommended for Production)

```bash
REDIS_URL=redis://localhost:6379/0
```

- ✅ Works across multiple app instances
- ✅ Persistent across restarts
- ✅ Accurate limits in distributed deployments

### Without Redis (Development Only)

If `REDIS_URL` is not set, slowapi falls back to in-memory storage:

- ⚠️ Only works with single app instance
- ⚠️ Resets on restart
- ⚠️ Not suitable for production

## Best Practices

1. **Apply rate limits to all public endpoints** - Prevents abuse
2. **Use stricter limits for expensive operations** - Protects resources
3. **Be generous with authenticated users** - Better UX
4. **Monitor 429 responses** - Indicates if limits are too strict
5. **Document limits in API docs** - Helps clients implement backoff

## References

- slowapi Documentation: https://slowapi.readthedocs.io/
- FastAPI Middleware: https://fastapi.tiangolo.com/advanced/middleware/
