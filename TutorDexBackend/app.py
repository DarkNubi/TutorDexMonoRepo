"""
TutorDex Backend API.

FastAPI service providing HTTP endpoints for the TutorDex website.
"""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from TutorDexBackend.metrics import observe_request
from TutorDexBackend.routes.admin_routes import router as admin_router
from TutorDexBackend.routes.analytics_routes import router as analytics_router
from TutorDexBackend.routes.assignments_routes import router as assignments_router
from TutorDexBackend.routes.duplicates_routes import router as duplicates_router
from TutorDexBackend.routes.health_routes import router as health_router
from TutorDexBackend.routes.telegram_routes import router as telegram_router
from TutorDexBackend.routes.user_routes import router as user_router
from TutorDexBackend.app_context import get_app_context
from TutorDexBackend.utils.request_utils import get_client_ip, parse_traceparent

_ctx = get_app_context()
auth_service = _ctx.auth_service
cfg = _ctx.cfg
logger = _ctx.logger
sb = _ctx.sb
store = _ctx.store

app = FastAPI(title="TutorDex Backend", version="0.1.0")

# Configure CORS
_cors_origins = str(getattr(cfg, "cors_allow_origins", "*") or "*").strip()
origins = ["*"] if _cors_origins == "*" else [o.strip() for o in _cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup_log() -> None:
    from shared.config import validate_environment_integrity
    validate_environment_integrity(cfg)
    auth_service.validate_production_config()
    logger.info(
        "startup",
        extra={
            "auth_required": auth_service.is_auth_required(),
            "app_env": getattr(cfg, "app_env", None),
            "supabase_enabled": sb.enabled(),
            "redis_prefix": getattr(getattr(store, "cfg", None), "prefix", None),
        },
    )


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or request.headers.get("X-Request-Id") or str(uuid.uuid4())
    start = time.perf_counter()
    status_code = 500
    trace_id, span_id = parse_traceparent(request.headers.get("traceparent") or request.headers.get("Traceparent"))

    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        status_code = getattr(response, "status_code", 200) or 200
        return response
    except Exception:
        logger.exception(
            "http_exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "client_ip": get_client_ip(request),
            },
        )
        raise
    finally:
        try:
            uid = auth_service.get_uid_from_request(request)
        except Exception:
            uid = None
        client_ip = get_client_ip(request)
        latency_ms = (time.perf_counter() - start) * 1000.0

        try:
            observe_request(
                method=request.method,
                path=request.url.path,
                status=status_code,
                latency_ms=latency_ms,
                client_ip=client_ip,
                uid=uid,
                trace_id=trace_id,
                span_id=span_id,
            )
        except Exception:
            # Metrics must never break runtime
            pass

        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "client_ip": client_ip,
                "uid": uid,
                "trace_id": trace_id or "-",
                "span_id": span_id or "-",
            },
        )


app.include_router(health_router)
app.include_router(assignments_router)
app.include_router(duplicates_router)
app.include_router(admin_router)
app.include_router(user_router)
app.include_router(analytics_router)
app.include_router(telegram_router)
