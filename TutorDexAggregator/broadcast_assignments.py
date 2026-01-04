# broadcast_assignments.py
# Send extracted assignment JSON to a target Telegram channel using Bot API.

import os
import json
import logging
import random
import time
from typing import Any, Dict, Optional
from pathlib import Path
from datetime import datetime, timezone

import requests
import html

from logging_setup import bind_log_context, log_event, setup_logging, timed
from agency_registry import get_agency_display_name
from observability_metrics import broadcast_fail_reason_total, broadcast_fail_total, broadcast_sent_total, versions as _obs_versions

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

# Load .env located next to this script, if present
HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / '.env'
if load_dotenv and ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)

setup_logging()
logger = logging.getLogger('broadcast_assignments')

# Configuration: support new env names from your .env
# Prefer explicit BOT_API_URL, otherwise build from available tokens.
BOT_API_URL = os.environ.get('BOT_API_URL') or os.environ.get('TG_BOT_API_URL')
# tokens provided in .env: DM_BOT_TOKEN, GROUP_BOT_TOKEN
BOT_TOKEN = os.environ.get('GROUP_BOT_TOKEN')
# target channel: prefer explicit AGGREGATOR_CHANNEL_ID (Telegram numeric chat id)
TARGET_CHAT = os.environ.get('AGGREGATOR_CHANNEL_ID')
_default_fallback_file = str(HERE / 'outgoing_broadcasts.jsonl')
FALLBACK_FILE = os.environ.get('BROADCAST_FALLBACK_FILE', _default_fallback_file)

# normalize TARGET_CHAT: convert t.me/username or https://t.me/username to @username


def _normalize_target_chat(chat: Optional[Any]) -> Optional[Any]:
    if chat is None:
        return None
    # preserve ints coming from env or upstream
    if isinstance(chat, int):
        return chat

    t = str(chat).strip()
    if not t:
        return None

    # Telegram chat ids (channels/groups) are ints, often starting with -100
    if t.lstrip('-').isdigit():
        try:
            return int(t)
        except ValueError:
            return t

    l = t.lower()
    if l.startswith('https://') or l.startswith('http://'):
        try:
            t = t.rstrip('/').split('/')[-1]
        except Exception:
            pass
    elif l.startswith('t.me/'):
        t = t.split('/')[-1]

    if not t.startswith('@'):
        t = f'@{t}'
    return t


TARGET_CHAT = _normalize_target_chat(TARGET_CHAT)

if not BOT_API_URL and not BOT_TOKEN:
    logger.warning('No BOT_API_URL or BOT_TOKEN set - broadcaster will write to %s instead of sending', FALLBACK_FILE)

if not BOT_API_URL and BOT_TOKEN:
    BOT_API_URL = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'


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

def _escape(text: Optional[str]) -> str:
    if not text:
        return ''
    return html.escape(str(text))


def _coerce_hours_env(name: str, default: int) -> int:
    try:
        v = int(str(os.environ.get(name, "")).strip() or default)
    except Exception:
        v = default
    return max(1, v)


def _parse_payload_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Accept ISO strings; normalize "Z" to "+00:00" for fromisoformat.
        s2 = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s2)
        except Exception:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _freshness_emoji(payload: Dict[str, Any]) -> str:
    dt = _parse_payload_date(payload.get("date"))
    if not dt:
        return ""
    age_h = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)

    green_h = _coerce_hours_env("FRESHNESS_GREEN_HOURS", 24)
    yellow_h = _coerce_hours_env("FRESHNESS_YELLOW_HOURS", 36)
    orange_h = _coerce_hours_env("FRESHNESS_ORANGE_HOURS", 48)
    red_h = _coerce_hours_env("FRESHNESS_RED_HOURS", 72)

    if age_h < green_h:
        return "🟢"
    if age_h < yellow_h:
        return "🟡"
    if age_h < orange_h:
        return "🟠"
    if age_h < red_h:
        return "🔴"
    return "🔴"


def _flatten_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_text_list(item))
        return out
    s = str(value).strip()
    return [s] if s else []


def _join_text(value: Any, sep: str = ", ") -> str:
    parts = _flatten_text_list(value)
    # de-dup while preserving order
    seen = set()
    uniq: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return sep.join(uniq)


def _format_day_key(day: str) -> str:
    d = (day or '').strip().lower()
    mapping = {
        'monday': 'Mon',
        'tuesday': 'Tue',
        'wednesday': 'Wed',
        'thursday': 'Thu',
        'friday': 'Fri',
        'saturday': 'Sat',
        'sunday': 'Sun',
    }
    return mapping.get(d, day)


def _format_time_slots_value(value: Any) -> str:
    if not value:
        return ''

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        parts = []
        for day, slots in value.items():
            if not slots:
                continue
            if isinstance(slots, (list, tuple)):
                slots_str = ', '.join(str(s).strip() for s in slots if str(s).strip())
            else:
                slots_str = str(slots).strip()
            if slots_str:
                parts.append(f"{_format_day_key(str(day))}: {slots_str}")
        return '; '.join(parts)

    return str(value).strip()


def _truncate_middle(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ''
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return text[:head] + '...' + text[-tail:]


def _derive_external_id_for_tracking(payload: Dict[str, Any]) -> str:
    parsed = payload.get("parsed") or {}
    assignment_code = _join_text(parsed.get("assignment_code"))
    if assignment_code:
        if str(payload.get("source_type") or "").strip().lower() == "tutorcity_api":
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            signals_meta = meta.get("signals") if isinstance(meta.get("signals"), dict) else None
            signals_obj = None
            if signals_meta and signals_meta.get("ok") is True and isinstance(signals_meta.get("signals"), dict):
                signals_obj = signals_meta.get("signals")
            subs = signals_obj.get("subjects") if isinstance(signals_obj, dict) else None
            if isinstance(subs, (list, tuple)) and subs:
                parts = sorted({str(s).strip() for s in subs if str(s).strip()})
                if parts:
                    return f"{assignment_code}:{'+'.join(parts)}"
        return assignment_code
    channel_id = payload.get("channel_id")
    message_id = payload.get("message_id")
    if channel_id is not None and message_id is not None:
        return f"tg:{channel_id}:{message_id}"
    message_link = payload.get("message_link")
    if message_link:
        return str(message_link)
    cid = payload.get("cid")
    if cid:
        return str(cid)
    return "unknown"


def _build_message_link_from_payload(payload: Dict[str, Any]) -> str:
    """Best-effort reconstruction of a Telegram message link.

    Many payloads already include message_link; for those that do not, try to
    derive a usable URL from channel identifiers and message_id.
    """

    try:
        message_link = str(payload.get("message_link") or "").strip()
    except Exception:
        message_link = ""
    if message_link:
        return message_link

    try:
        msg_id = int(payload.get("message_id"))
    except Exception:
        msg_id = None

    try:
        channel_link = str(payload.get("channel_link") or "").strip()
    except Exception:
        channel_link = ""

    if channel_link:
        link = channel_link.rstrip('/')
        lower = link.lower()
        if lower.startswith("http://") or lower.startswith("https://"):
            return f"{link}/{msg_id}" if msg_id is not None else link
        if lower.startswith("t.me/"):
            base = link.split('t.me/', 1)[-1].lstrip('/')
            if base:
                return f"https://t.me/{base}/{msg_id}" if msg_id is not None else f"https://t.me/{base}"
        if channel_link.startswith("@"):
            uname = channel_link.lstrip("@")
            return f"https://t.me/{uname}/{msg_id}" if msg_id is not None else f"https://t.me/{uname}"
        # If it's a bare username, treat it as such.
        return f"https://t.me/{channel_link}/{msg_id}" if msg_id is not None else f"https://t.me/{channel_link}"

    try:
        channel_username = str(payload.get("channel_username") or "").strip()
    except Exception:
        channel_username = ""
    if channel_username:
        uname = channel_username
        if uname.startswith("http://") or uname.startswith("https://"):
            uname = uname.rstrip('/').split('/')[-1]
        if uname.startswith("t.me/"):
            uname = uname.split('/')[-1]
        uname = uname.lstrip("@")
        if uname:
            return f"https://t.me/{uname}/{msg_id}" if msg_id is not None else f"https://t.me/{uname}"

    try:
        channel_id = int(payload.get("channel_id"))
    except Exception:
        channel_id = None
    if channel_id is not None and msg_id is not None:
        return f"https://t.me/c/{abs(channel_id)}/{msg_id}"

    return ""


def build_inline_keyboard(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Build a simple inline keyboard to surface the source message."""
    message_link = _build_message_link_from_payload(payload)
    if not message_link:
        return None

    button: Dict[str, Any] = {"text": "Open original post", "url": message_link}
    return {"inline_keyboard": [[button]]}


def build_message_text(
    payload: Dict[str, Any],
    *,
    include_clicks: bool = True,
    clicks: int = 0,
    distance_km: Optional[float] = None,
) -> str:
    parsed = payload.get('parsed') or {}
    academic_raw = _escape(_join_text(parsed.get("academic_display_text")))
    assignment_code = _escape(_join_text(parsed.get('assignment_code')))
    address = _escape(_join_text(parsed.get('address')))
    nearest_mrt = _escape(_join_text(parsed.get('nearest_mrt')))
    postal = _escape(_join_text(parsed.get("postal_code")))
    postal_estimated = _escape(_join_text(parsed.get("postal_code_estimated")))

    # v2 schema: lesson_schedule is an optional list of raw schedule snippets (authoritative-as-listed).
    lesson_schedule_lines: list[str] = []
    if isinstance(parsed.get("lesson_schedule"), list):
        for item in parsed.get("lesson_schedule") or []:
            if isinstance(item, str) and item.strip():
                lesson_schedule_lines.append(_escape(item.strip()))

    start_date = _escape(_join_text(parsed.get("start_date")))

    time_note_lines: list[str] = []
    if isinstance(parsed.get("time_availability"), dict):
        note = (parsed.get("time_availability") or {}).get("note")
        if isinstance(note, str) and note.strip():
            for ln in note.splitlines():
                s = ln.strip()
                if s:
                    time_note_lines.append(_escape(s))

    rate_line = ""
    if isinstance(parsed.get("rate"), dict):
        r = parsed.get("rate") or {}
        raw_rate = r.get("raw_text")
        if isinstance(raw_rate, str) and raw_rate.strip():
            rate_line = _escape(raw_rate.strip())
        else:
            rmin = r.get("min")
            rmax = r.get("max")
            try:
                if rmin is not None or rmax is not None:
                    if rmin is None:
                        rate_line = f"{float(rmax):.0f}"
                    elif rmax is None:
                        rate_line = f"{float(rmin):.0f}"
                    else:
                        rate_line = f"{float(rmin):.0f}-{float(rmax):.0f}"
            except Exception:
                rate_line = ""
    remarks = _escape(parsed.get('additional_remarks'))

    max_remarks = int(os.environ.get('BROADCAST_MAX_REMARKS_LEN', '700'))
    if remarks and len(remarks) > max_remarks:
        remarks = _escape(_truncate_middle(html.unescape(remarks), max_remarks))

    lines = []

    # Prefer a curated display name by channel ref; fall back to channel_title for non-Telegram sources.
    chat_ref = payload.get("channel_link") or payload.get("channel_username") or ""
    agency = get_agency_display_name(chat_ref, default="")
    if not agency:
        agency = str(payload.get("channel_title") or "").strip() or "Agency"
    # Header
    emoji = _freshness_emoji(payload)
    prefix = f"{emoji} " if emoji else ""
    header = f'{prefix}⭐️<b>{agency}</b>⭐️'
    if academic_raw:
        header += f"\n<b>{academic_raw}</b>"
    else:
        header += "\n<b>Tuition Assignment</b>"
    lines.append(header)

    # Assignment metadata
    if assignment_code:
        lines.append(f"🆔 {assignment_code}")

    # Location
    if address:
        lines.append(f"📍 {address}")
    if nearest_mrt:
        lines.append(f"🚇 {nearest_mrt}")
    if postal:
        lines.append(f"Postal: {postal}")
    if (not address and not nearest_mrt and not postal) and postal_estimated:
        lines.append(f"Postal (estimated): {postal_estimated}")

    if distance_km is not None:
        try:
            km = float(distance_km)
        except Exception:
            km = None
        lm = parsed.get("learning_mode")
        if isinstance(lm, dict):
            learning_mode = str(lm.get("mode") or lm.get("raw_text") or "").strip().lower()
        else:
            learning_mode = str(lm or "").strip().lower()
        if km is not None and km >= 0 and learning_mode != "online":
            lines.append(f"📏 Distance: ~{km:.1f} km")

    # Start date
    if start_date:
        lines.append(f"🗓️ {start_date}")

    # Lesson schedule (raw snippets)
    for item in lesson_schedule_lines:
        lines.append(f"📆 {item}")

    # Time availability note (multi-line)
    for item in time_note_lines:
        lines.append(f"🕒 {item}")

    # Rate
    if rate_line:
        lines.append(f"💰 {rate_line}")

    # Remarks
    if remarks:
        lines.append(f"📝 {remarks}")

    # Metadata
    channel = _escape(payload.get('channel_title') or payload.get('channel_username') or payload.get('channel_id'))
    if channel:
        if remarks:
            lines.append("")
        lines.append(f"🏷️ Source: {channel}")

    # Do not include raw text excerpt or message id in the broadcast

    # Links + CTA hint
    footer_lines: list[str] = []
    footer = "\n".join(footer_lines).strip()

    max_len = int(os.environ.get('BROADCAST_MAX_MESSAGE_LEN', '3900'))

    # Try to keep within Telegram limits without breaking HTML tags.
    prunable_prefixes = ('📝 ', '🏷️ Source: ', '🕒 ', '📆 ', '🗓️ ', '💰 ')
    while True:
        candidate = '\n'.join(lines + ([footer] if footer else []))
        if len(candidate) <= max_len:
            return candidate

        removed = False
        for idx in range(len(lines) - 1, -1, -1):
            if lines[idx].startswith(prunable_prefixes):
                lines.pop(idx)
                removed = True
                break
        if removed:
            continue

        # If we still exceed, drop footer first, then hard truncate the plain text part.
        if footer:
            footer = ''
            continue

        hard = '\n'.join(lines)
        if len(hard) <= max_len:
            return hard
        return _truncate_middle(hard, max_len)


def send_broadcast(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send a broadcast to the configured Telegram channel via Bot API.

    If no bot configuration is present, write the payload to a local file for manual handling.
    Returns a dict with result info.
    """
    cid = payload.get('cid') or '<no-cid>'
    msg_id = payload.get('message_id')
    channel_link = payload.get('channel_link') or payload.get('channel_username') or ''
    chat_id = TARGET_CHAT or payload.get('target_chat')

    v = _obs_versions()
    pv = str(payload.get("pipeline_version") or "").strip() or v.pipeline_version
    sv = str(payload.get("schema_version") or "").strip() or v.schema_version
    assignment_id = _derive_external_id_for_tracking(payload)

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

        if BOT_API_URL and chat_id:
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
                max_attempts = max(1, int(os.environ.get("BROADCAST_MAX_ATTEMPTS", "4") or 4))
                base_sleep_s = float(os.environ.get("BROADCAST_RETRY_BASE_SECONDS", "2.0") or 2.0)
                max_sleep_s = float(os.environ.get("BROADCAST_RETRY_MAX_SLEEP_SECONDS", "60.0") or 60.0)

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
                        log_event(logger, logging.WARNING, "broadcast_retry", attempt=attempt, wait_s=wait_s, reason="request_exception", error=str(e))
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
                        log_event(logger, logging.WARNING, "broadcast_rate_limited", attempt=attempt, retry_after_s=retry_after)
                        if attempt >= max_attempts:
                            break
                        _sleep(float(retry_after))
                        continue

                    if resp.status_code >= 500:
                        # Transient Telegram / network issues; retry with exponential backoff.
                        if attempt >= max_attempts:
                            break
                        wait_s = min(max_sleep_s, base_sleep_s * (2 ** (attempt - 1)))
                        log_event(logger, logging.WARNING, "broadcast_retry", attempt=attempt, wait_s=wait_s, reason="server_error", status_code=resp.status_code)
                        _sleep(wait_s)
                        continue

                    # Success or non-retryable 4xx.
                    break

                if resp.status_code >= 400:
                    log_event(
                        logger,
                        logging.WARNING,
                        "broadcast_send_failed",
                        status_code=resp.status_code,
                        send_ms=send_ms,
                        telegram_ok=bool(j.get("ok")) if isinstance(j, dict) else None,
                        telegram_error_code=j.get("error_code") if isinstance(j, dict) else None,
                        telegram_description=j.get("description")[:300] if isinstance(j, dict) and isinstance(j.get("description"), str) else None,
                    )
                    try:
                        broadcast_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                    try:
                        broadcast_fail_reason_total.labels(
                            reason=_classify_broadcast_error(status_code=int(resp.status_code), error=(j.get("description") if isinstance(j, dict) else None)),
                            pipeline_version=pv,
                            schema_version=sv,
                        ).inc()
                    except Exception:
                        pass
                else:
                    log_event(logger, logging.INFO, "broadcast_sent", status_code=resp.status_code, send_ms=send_ms)
                    try:
                        broadcast_sent_total.labels(pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                    # Best-effort: store broadcast message mapping for click tracking edits.
                    try:
                        if isinstance(j, dict) and isinstance(j.get("result"), dict):
                            sent_message_id = j["result"].get("message_id")
                            sent_chat_id = (j["result"].get("chat") or {}).get("id") if isinstance(j["result"].get("chat"), dict) else None
                            if sent_chat_id is not None and sent_message_id is not None:
                                from click_tracking_store import upsert_broadcast_message  # local import
                                upsert_broadcast_message(payload=payload, sent_chat_id=int(sent_chat_id), sent_message_id=int(sent_message_id), message_html=text)
                    except Exception:
                        logger.debug("click_tracking_upsert_failed", exc_info=True)
                return {'ok': resp.status_code < 400, 'response': j}
            except Exception as e:
                logger.exception('Broadcast send error error=%s', e)
                try:
                    broadcast_fail_total.labels(pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
                try:
                    broadcast_fail_reason_total.labels(
                        reason=_classify_broadcast_error(status_code=None, error=str(e)),
                        pipeline_version=pv,
                        schema_version=sv,
                    ).inc()
                except Exception:
                    pass
                return {'ok': False, 'error': str(e)}

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


if __name__ == '__main__':
    # simple CLI test: read payload from stdin or sample file
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
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
                    'explicit': {d: [] for d in ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')},
                    'estimated': {d: [] for d in ('monday','tuesday','wednesday','thursday','friday','saturday','sunday')},
                    'note': 'Weekdays evenings'
                },
                'rate': {'min': 40, 'max': 40, 'raw_text': '$40/hr'},
                'additional_remarks': None,
            }
        }
        print(send_broadcast(sample))
    else:
        print('Import this module and call send_broadcast(payload)')
