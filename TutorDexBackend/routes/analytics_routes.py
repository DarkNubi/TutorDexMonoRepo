from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request

from TutorDexBackend.models import AnalyticsEventRequest, ClickTrackRequest
from TutorDexBackend.app_context import AppContext, get_app_context

router = APIRouter()


@router.post("/track")
async def track_click(request: Request, req: ClickTrackRequest) -> Dict[str, Any]:
    return {
        "ok": True,
        "tracked": False,
        "clicks": None,
        "external_id": (req.assignment_external_id or "").strip() or None,
    }


@router.post("/analytics/event")
def analytics_event(request: Request, req: AnalyticsEventRequest, ctx: AppContext = Depends(get_app_context)) -> Dict[str, Any]:
    uid = ctx.auth_service.require_uid(request)
    if not ctx.sb.enabled():
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    user_id = ctx.sb.upsert_user(firebase_uid=uid, email=None, name=None)
    assignment_id = None
    if req.assignment_external_id:
        assignment_id = ctx.sb.resolve_assignment_id(external_id=req.assignment_external_id, agency_name=req.agency_name)

    ctx.analytics_service.insert_analytics_event(
        user_id=user_id,
        assignment_id=assignment_id,
        event_type=req.event_type,
        meta=req.meta or {"external_id": req.assignment_external_id, "agency_name": req.agency_name},
    )
    return {"ok": True}
