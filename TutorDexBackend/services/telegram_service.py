"""
Telegram integration service.

Handles Telegram bot operations including link codes and webhooks.
"""
import os
import logging
import asyncio
from typing import Optional
from fastapi import Request
import requests
from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.utils.config_utils import get_bot_token_for_edits

logger = logging.getLogger("tutordex_backend")


class TelegramService:
    """Telegram bot integration logic."""
    
    def __init__(self, store: TutorStore):
        self.store = store
    
    def verify_webhook(self, request: Request) -> bool:
        """
        Verify Telegram webhook request using secret token.
        
        When a webhook is set with a secret_token, Telegram includes it in the
        X-Telegram-Bot-Api-Secret-Token header. We verify it matches our configured secret.
        
        Args:
            request: FastAPI request object
            
        Returns:
            True if verification passes or no secret is configured (permissive mode)
        """
        configured_secret = (os.environ.get("WEBHOOK_SECRET_TOKEN") or "").strip()
        if not configured_secret:
            # No secret configured - allow requests (backward compatible)
            return True
        
        # FastAPI converts headers to lowercase. Telegram sends this as
        # "X-Telegram-Bot-Api-Secret-Token" per their webhook documentation,
        # but we access it as lowercase per FastAPI's normalization.
        header_secret = (request.headers.get("x-telegram-bot-api-secret-token") or "").strip()
        
        return header_secret == configured_secret
    
    async def answer_callback_query(self, callback_query_id: str, url: Optional[str]) -> None:
        """
        Answer Telegram callback query.
        
        Args:
            callback_query_id: Telegram callback query ID
            url: Optional URL to open
        """
        token = get_bot_token_for_edits()
        if not token or not callback_query_id:
            return
        
        body = {"callback_query_id": callback_query_id}
        if url:
            body["url"] = url
        
        try:
            await asyncio.to_thread(
                lambda: requests.post(
                    f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                    json=body,
                    timeout=10
                )
            )
        except Exception:
            logger.exception("telegram_answer_callback_failed", extra={"callback_query_id": callback_query_id})
