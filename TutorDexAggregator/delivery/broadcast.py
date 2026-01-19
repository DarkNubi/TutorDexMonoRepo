from __future__ import annotations

import argparse
import json
import os
from typing import Any, Dict, Optional

from delivery.broadcast_client import _send_to_single_chat
from delivery.config import BOT_API_URL, FALLBACK_FILE, TARGET_CHAT, TARGET_CHATS, _CFG, logger
from delivery.formatting import _flatten_text_list, _join_text, _derive_external_id_for_tracking, build_message_text
from logging_setup import bind_log_context, log_event, timed
from observability_metrics import broadcast_fail_reason_total, broadcast_fail_total, versions as _obs_versions

def _validate_broadcast_safety() -> None:
    """Validate broadcast configuration before sending messages."""
    app_env = str(getattr(_CFG, "app_env", "dev")).strip().lower()
    channel_id = str(getattr(_CFG, "aggregator_channel_id", "") or "").strip()
    enable_broadcast = getattr(_CFG, "enable_broadcast", False)
    
    if not enable_broadcast:
        return  # Broadcast disabled, no check needed
    
    if not channel_id:
        raise RuntimeError(
            "BROADCAST ERROR: ENABLE_BROADCAST=true but AGGREGATOR_CHANNEL_ID is empty"
        )
    
    # Convention: staging channels should have "_test" or "_staging" in ID
    if app_env == "staging":
        if not any(marker in channel_id.lower() for marker in ["test", "staging", "dev"]):
            raise RuntimeError(
                f"BROADCAST SAFETY ERROR:\n"
                f"APP_ENV=staging but AGGREGATOR_CHANNEL_ID does not contain 'test', 'staging', or 'dev'\n"
                f"Channel ID: {channel_id}\n"
                f"This may be a production channel.\n"
                f"Fix: Use a test channel ID or add '_test' suffix to confirm it's a test channel"
            )
        
        logger.warning(
            "Staging environment broadcasting to Telegram. Ensure this is intentional.",
            extra={"channel_id": channel_id}
        )

def send_broadcast(payload: Dict[str, Any], *, target_chats: Optional[list] = None) -> Dict[str, Any]:
    """Send a broadcast to the configured Telegram channel(s) via Bot API.

    If no bot configuration is present, write the payload to a local file for manual handling.
    
    Duplicate Filtering:
    - Controlled by BROADCAST_DUPLICATE_MODE environment variable
    - Modes: 'all' (default), 'primary_only', 'primary_with_note'
    - 'primary_only': Only broadcast primary assignment from duplicate groups
    - 'primary_with_note': Broadcast primary with note about other agencies
    
    Args:
        payload: Assignment payload to broadcast
        target_chats: Optional list of chat IDs to override TARGET_CHATS.
                     Precedence: target_chats > TARGET_CHATS > TARGET_CHAT > payload['target_chat']
    
    Returns:
        Dict with result info. Structure varies by scenario:
        
        Multi-channel success:
            {'ok': bool, 'results': List[Dict], 'chats': List, 'sent_count': int, 'failed_count': int}
        
        Single-channel success (legacy):
            {'ok': bool, 'response': Dict, 'status_code': int, 'chat_id': Any}
        
        Fallback (no bot config):
            {'ok': bool, 'saved_to_file': str} on success
            {'ok': False, 'error': str} on failure
    """
    _validate_broadcast_safety()
    cid = payload.get('cid') or '<no-cid>'
    msg_id = payload.get('message_id')
    channel_link = payload.get('channel_link') or payload.get('channel_username') or ''
    
    # Determine target chat IDs with clear precedence order:
    # 1. Explicit parameter override (target_chats)
    # 2. Configured multiple channels (TARGET_CHATS)
    # 3. Configured single channel (TARGET_CHAT) 
    # 4. Payload-specific override (payload['target_chat'])
    chats = target_chats if target_chats is not None else TARGET_CHATS
    if not chats and TARGET_CHAT:
        chats = [TARGET_CHAT]
    if not chats and payload.get('target_chat'):
        chats = [payload.get('target_chat')]

    v = _obs_versions()
    pv = str(payload.get("pipeline_version") or "").strip() or v.pipeline_version
    sv = str(payload.get("schema_version") or "").strip() or v.schema_version
    assignment_id = _derive_external_id_for_tracking(payload)
    
    # Check duplicate filtering mode
    duplicate_mode = str(_CFG.broadcast_duplicate_mode or "all").strip().lower()
    if duplicate_mode in ("primary_only", "primary_with_note"):
        parsed = payload.get("parsed") or {}
        is_primary = parsed.get("is_primary_in_group", True)
        
        if not is_primary:
            # Skip broadcasting non-primary duplicates
            logger.info(
                f"Skipping broadcast for non-primary duplicate (mode={duplicate_mode})",
                extra={
                    "assignment_id": assignment_id,
                    "duplicate_group_id": parsed.get("duplicate_group_id"),
                    "duplicate_mode": duplicate_mode
                }
            )
            try:
                from observability_metrics import broadcast_skipped_duplicate_total
                broadcast_skipped_duplicate_total.inc()
            except Exception:
                pass
            return {"ok": True, "skipped": True, "reason": "non_primary_duplicate", "mode": duplicate_mode}

    with bind_log_context(
        cid=cid,
        message_id=msg_id,
        channel=str(channel_link) if channel_link else None,
        assignment_id=assignment_id,
        step="broadcast",
        component="broadcast",
        pipeline_version=pv,
        schema_version=sv,
    ):
        t_build = timed()
        text = build_message_text(payload, include_clicks=True, clicks=0)
        build_ms = round((timed() - t_build) * 1000.0, 2)

        try:
            parsed = payload.get("parsed") or {}
            academic_display_text = _join_text(parsed.get("academic_display_text"))
            addresses = _flatten_text_list(parsed.get("address"))
            postals = _flatten_text_list(parsed.get("postal_code"))
            postals_est = _flatten_text_list(parsed.get("postal_code_estimated"))
            rate_text = ""
            if isinstance(parsed.get("rate"), dict):
                rate_text = _join_text((parsed.get("rate") or {}).get("raw_text"))
            time_note = ""
            if isinstance(parsed.get("time_availability"), dict):
                time_note = _join_text((parsed.get("time_availability") or {}).get("note"))
            log_event(
                logger,
                logging.DEBUG,
                "broadcast_built",
                text_len=len(text),
                build_ms=build_ms,
                has_academic_display_text=bool(academic_display_text),
                has_any_location=bool(addresses or postals or postals_est),
                has_rate=bool(rate_text),
                has_time_note=bool(time_note),
            )
            if not academic_display_text:
                log_event(logger, logging.WARNING, "broadcast_missing_fields", missing_academic_display_text=True)
        except Exception:
            logger.exception("Failed to build broadcast summary")

        if BOT_API_URL and chats:
            # Send to all configured chat IDs
            results = []
            for chat_id in chats:
                try:
                    result = _send_to_single_chat(chat_id, text, payload, pv=pv, sv=sv)
                    results.append(result)
                except Exception as e:
                    logger.exception('Failed to send to chat_id=%s error=%s', chat_id, e)
                    results.append({'ok': False, 'error': str(e), 'chat_id': chat_id})
            
            # Return aggregated results
            all_ok = all(r.get('ok') for r in results)
            return {
                'ok': all_ok,
                'results': results,
                'chats': chats,
                'sent_count': sum(1 for r in results if r.get('ok')),
                'failed_count': sum(1 for r in results if not r.get('ok')),
            }

        # Fallback: append to local file as JSON lines
        try:
            with open(FALLBACK_FILE, 'a', encoding='utf8') as fh:
                fh.write(json.dumps({'payload': payload, 'text': text}, ensure_ascii=False) + '\n')
            log_event(logger, logging.INFO, "broadcast_fallback_written", path=str(FALLBACK_FILE))
            try:
                broadcast_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass
            try:
                broadcast_fail_reason_total.labels(reason="fallback_written", pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass
            return {'ok': True, 'saved_to_file': FALLBACK_FILE}
        except Exception as e:
            logger.exception('Failed to write fallback broadcast error=%s', e)
            try:
                broadcast_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass
            try:
                broadcast_fail_reason_total.labels(reason="fallback_write_failed", pipeline_version=pv, schema_version=sv).inc()
            except Exception:
                pass
            return {'ok': False, 'error': str(e)}



def broadcast_single_assignment(payload: Dict[str, Any]) -> Dict[str, Any]:
    return send_broadcast(payload)


def main(argv: Optional[list[str]] = None) -> None:
    p = argparse.ArgumentParser(description='Broadcast one assignment payload (debug tool).')
    p.add_argument('--test', '--test-mode', action='store_true', help='Send a built-in sample payload')
    args = p.parse_args(argv)

    if args.test:
        sample = {
            'channel_title': 'SampleChannel',
            'channel_username': 'samplechan',
            'channel_id': -1002742584213,
            'message_id': 999,
            'message_link': 'https://t.me/samplechan/999',
            'raw_text': 'Sample assignment: P5 Math near Woodlands Ring Road, $40/hr',
            'parsed': {
                'assignment_code': 'A1',
                'academic_display_text': 'P5 Maths',
                'learning_mode': {'mode': 'Face-to-Face', 'raw_text': 'near Woodlands Ring Road'},
                'address': ['Woodlands Ring Road'],
                'postal_code': None,
                'nearest_mrt': None,
                'lesson_schedule': ['1x a week, 1.5 hours'],
                'start_date': 'ASAP',
                'time_availability': {
                    'explicit': {d: [] for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')},
                    'estimated': {d: [] for d in ('monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday')},
                    'note': 'Weekdays evenings'
                },
                'rate': {'min': 40, 'max': 40, 'raw_text': '$40/hr'},
                'additional_remarks': None,
            }
        }
        print(send_broadcast(sample))
        return

    raise SystemExit('Import this module and call send_broadcast(payload), or run with --test.')
