from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter
from fastapi.responses import Response

from TutorDexBackend.metrics import metrics_payload
from TutorDexBackend.runtime import health_service
from TutorDexBackend.utils.config_utils import get_bot_token_for_edits

router = APIRouter()


@router.get("/metrics")
def metrics() -> Response:
    data, content_type = metrics_payload()
    return Response(content=data, media_type=content_type)


@router.get("/health")
def health() -> Dict[str, Any]:
    return health_service.basic_health()


@router.get("/health/redis")
def health_redis() -> Dict[str, Any]:
    return health_service.redis_health()


@router.get("/health/supabase")
def health_supabase() -> Dict[str, Any]:
    return health_service.supabase_health()


@router.get("/health/full")
def health_full() -> Dict[str, Any]:
    return health_service.full_health()


@router.get("/health/collector")
def health_collector() -> Dict[str, Any]:
    return health_service.collector_health()


@router.get("/health/worker")
def health_worker() -> Dict[str, Any]:
    return health_service.worker_health()


@router.get("/health/dependencies")
def health_dependencies() -> Dict[str, Any]:
    return health_service.dependencies_health()


@router.get("/health/webhook")
def health_webhook() -> Dict[str, Any]:
    bot_token = get_bot_token_for_edits()
    return health_service.webhook_health(bot_token)


@router.get("/contracts/assignment-row.schema.json")
def assignment_row_contract() -> Response:
    path = (Path(__file__).resolve().parents[1] / "contracts" / "assignment_row.schema.json").resolve()
    body = path.read_text(encoding="utf8")
    return Response(content=body, media_type="application/schema+json")

