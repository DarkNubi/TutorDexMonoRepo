from __future__ import annotations

import logging
import random
import time
from typing import Any, Dict, Optional

import requests

from delivery.config import BOT_API_URL, ENABLE_BROADCAST_TRACKING, _CFG, logger
from delivery.format_tracking import build_inline_keyboard
from logging_setup import log_event, timed
from observability_metrics import broadcast_fail_reason_total, broadcast_fail_total, broadcast_sent_total

def _classify_broadcast_error(*, status_code: Optional[int], error: Optional[str]) -> str:
    msg = str(error or "").lower()
    if status_code == 429 or "too many requests" in msg or "retry_after" in msg:
        return "rate_limited"
    if status_code is not None and status_code >= 500:
        return "telegram_5xx"
    if status_code is not None and status_code >= 400:
        return "telegram_4xx"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if "connection" in msg or "connection refused" in msg:
        return "connection"
    return "error"

def _send_to_single_chat(chat_id: Any, text: str, payload: Dict[str, Any], *, pv: str, sv: str) -> Dict[str, Any]:
    """Send broadcast to a single chat. Returns result dict."""
    body = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True,
        'disable_notification': False,
    }
    try:
        reply_markup = build_inline_keyboard(payload)
        if reply_markup:
            body['reply_markup'] = reply_markup
    except Exception:
        logger.exception('callback_reply_markup_error')

    try:
        max_attempts = max(1, int(_CFG.broadcast_max_attempts))
        base_sleep_s = float(_CFG.broadcast_retry_base_seconds)
        max_sleep_s = float(_CFG.broadcast_retry_max_sleep_seconds)

        def _sleep(s: float) -> None:
            s = max(0.0, float(s))
            jitter = random.uniform(0.0, min(1.0, s * 0.1))
            time.sleep(min(max_sleep_s, s + jitter))

        resp = None
        j: Any = None
        send_ms = None

        for attempt in range(1, max_attempts + 1):
            t_send = timed()
            try:
                resp = requests.post(BOT_API_URL, json=body, timeout=15)
                send_ms = round((timed() - t_send) * 1000.0, 2)
            except requests.RequestException as e:
                if attempt >= max_attempts:
                    raise
                wait_s = min(max_sleep_s, base_sleep_s * (2 ** (attempt - 1)))
                log_event(logger, logging.WARNING, "broadcast_retry", attempt=attempt,
                          wait_s=wait_s, reason="request_exception", error=str(e), chat_id=chat_id)
                _sleep(wait_s)
                continue

            try:
                j = resp.json()
            except Exception:
                j = {'status_code': resp.status_code, 'text': resp.text[:500]}

            if resp.status_code == 429:
                # Telegram rate limit. If we can, retry after the requested delay.
                retry_after = 0
                if isinstance(j, dict):
                    try:
                        retry_after = int((j.get("parameters") or {}).get("retry_after") or 0)
                    except Exception:
                        retry_after = 0
                retry_after = max(1, min(int(max_sleep_s), retry_after or 2))
                log_event(logger, logging.WARNING, "broadcast_rate_limited", attempt=attempt, retry_after_s=retry_after, chat_id=chat_id)
                if attempt >= max_attempts:
                    break
                _sleep(float(retry_after))
                continue

            if resp.status_code >= 500:
                # Transient Telegram / network issues; retry with exponential backoff.
                if attempt >= max_attempts:
                    break
                wait_s = min(max_sleep_s, base_sleep_s * (2 ** (attempt - 1)))
                log_event(logger, logging.WARNING, "broadcast_retry", attempt=attempt,
                          wait_s=wait_s, reason="server_error", status_code=resp.status_code, chat_id=chat_id)
                _sleep(wait_s)
                continue

            # Success or non-retryable 4xx.
            break

        if resp.status_code >= 400:
            log_event(
                logger,
                logging.WARNING,
                "broadcast_send_failed",
                chat_id=chat_id,
                status_code=resp.status_code,
                send_ms=send_ms,
                telegram_ok=bool(j.get("ok")) if isinstance(j, dict) else None,
                telegram_error_code=j.get("error_code") if isinstance(j, dict) else None,
                telegram_description=j.get("description")[:300] if isinstance(j, dict) and isinstance(j.get("description"), str) else None,
            )
            try:
                broadcast_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass  # Metrics must never break runtime
            try:
                broadcast_fail_reason_total.labels(
                    reason=_classify_broadcast_error(status_code=int(resp.status_code), error=(
                        j.get("description") if isinstance(j, dict) else None)),
                    pipeline_version=pv,
                    schema_version=sv,
                ).inc()
            except Exception:
                pass  # Metrics must never break runtime
            return {'ok': False, 'status_code': resp.status_code, 'response': j, 'chat_id': chat_id}
        else:
            log_event(logger, logging.INFO, "broadcast_sent", chat_id=chat_id, status_code=resp.status_code, send_ms=send_ms)
            try:
                broadcast_sent_total.labels(pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass  # Metrics must never break runtime
            # Store broadcast message mapping for tracking/reconciliation
            if ENABLE_BROADCAST_TRACKING:
                try:
                    if isinstance(j, dict) and isinstance(j.get("result"), dict):
                        sent_message_id = j["result"].get("message_id")
                        sent_chat_id = (j["result"].get("chat") or {}).get("id") if isinstance(j["result"].get("chat"), dict) else None
                        if sent_chat_id is not None and sent_message_id is not None:
                            from click_tracking_store import upsert_broadcast_message  # local import
                            upsert_broadcast_message(payload=payload, sent_chat_id=int(sent_chat_id),
                                                     sent_message_id=int(sent_message_id), message_html=text)
                except Exception:
                    logger.debug("broadcast_tracking_upsert_failed", exc_info=True, chat_id=chat_id)
            return {'ok': True, 'status_code': resp.status_code, 'response': j, 'chat_id': chat_id,
                    'sent_message_id': j.get("result", {}).get("message_id") if isinstance(j, dict) else None}
    except Exception as e:
        logger.exception('Broadcast send error chat_id=%s error=%s', chat_id, e)
        try:
            broadcast_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
        except Exception:
            pass  # Metrics must never break runtime
        try:
            broadcast_fail_reason_total.labels(
                reason=_classify_broadcast_error(status_code=None, error=str(e)),
                pipeline_version=pv,
                schema_version=sv,
            ).inc()
        except Exception:
            pass  # Metrics must never break runtime
        return {'ok': False, 'error': str(e), 'chat_id': chat_id}

