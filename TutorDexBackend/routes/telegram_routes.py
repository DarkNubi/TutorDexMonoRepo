from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from TutorDexBackend.models import TelegramClaimRequest, TelegramLinkCodeRequest
from TutorDexBackend.app_context import AppContext, get_app_context

router = APIRouter()


@router.post("/telegram/link-code")
def telegram_link_code(request: Request, req: TelegramLinkCodeRequest, ctx: AppContext = Depends(get_app_context)) -> Dict[str, Any]:
    ctx.auth_service.require_admin(request)
    ttl = max(60, min(3600, int(req.ttl_seconds or 600)))
    return ctx.store.create_telegram_link_code(req.tutor_id, ttl_seconds=ttl)


@router.post("/telegram/claim")
def telegram_claim(request: Request, req: TelegramClaimRequest, ctx: AppContext = Depends(get_app_context)) -> Dict[str, Any]:
    ctx.auth_service.require_admin(request)
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")
    tutor_id = ctx.store.consume_telegram_link_code(code)
    if not tutor_id:
        raise HTTPException(status_code=404, detail="invalid_or_expired_code")

    username = (req.telegram_username or "").strip() or None
    return ctx.store.set_chat_id(tutor_id, req.chat_id, telegram_username=username)


@router.post("/telegram/callback")
async def telegram_callback(request: Request) -> Dict[str, Any]:
    return {"ok": True, "external_id": None, "has_url": False, "disabled": True}
