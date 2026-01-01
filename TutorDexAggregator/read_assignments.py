# read_assignments.py
# Long-running Telethon reader that processes messages from configured channels
# and forwards extracted assignment JSON to a broadcast function.

import broadcast_assignments
from extract_key_info import extract_assignment_with_model, process_parsed_payload
from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SlowModeWaitError, FloodError
import os
import asyncio
import json
import logging
from pathlib import Path
from typing import Optional, Callable, Any
import re
import time
import random
import json
import requests

from supabase_env import resolve_supabase_url
from logging_setup import (
    bind_log_context,
    log_event,
    run_in_thread,
    set_step,
    setup_logging,
    timed,
)
from schema_validation import validate_parsed_assignment

# Optional: Supabase persistence (best-effort)
_optional_import_errors: list[str] = []
try:
    from supabase_persist import persist_assignment_to_supabase
except Exception as e:
    _optional_import_errors.append(f"supabase_persist_import_failed: {e}")
    persist_assignment_to_supabase = None

# Optional: Bot 2 (DM) sending (best-effort)
try:
    from dm_assignments import send_dms
except Exception as e:
    _optional_import_errors.append(f"dm_assignments_import_failed: {e}")
    send_dms = None

# Load .env if present (use python-dotenv if available, and fallback to simple parser)
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / '.env'
_env_parse_error: Optional[str] = None
if ENV_PATH.exists():
    if load_dotenv:
        load_dotenv(dotenv_path=ENV_PATH)
    # manual fallback parser to support KEY: VALUE or KEY=VALUE and quoted values
    try:
        raw = ENV_PATH.read_text(encoding='utf8')
        for ln in raw.splitlines():
            line = ln.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                k, v = line.split('=', 1)
            elif ':' in line:
                k, v = line.split(':', 1)
            else:
                continue
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            # remove surrounding [ ] for list-like values
            if v.startswith('[') and v.endswith(']'):
                v = v
            if k and k not in os.environ:
                os.environ[k] = v
    except Exception as e:
        _env_parse_error = str(e)

try:
    # StringSession is optional; used when SESSION_STRING provided
    from telethon.sessions import StringSession
except Exception:
    StringSession = None

# local extractor and broadcaster (must exist in workspace)

# Configuration via environment (support TELEGRAM_* and legacy TG_* names)
#
# Required:
#   TELEGRAM_API_ID (or TG_API_ID, API_ID): Telegram API ID
#   TELEGRAM_API_HASH (or TG_API_HASH, API_HASH): Telegram API hash
#   CHANNEL_LIST (or CHANNELS): JSON array or comma-separated list of channels to monitor
#
# Optional Rate Limiting (to prevent IP bans):
#   TELEGRAM_MAX_RETRIES: Maximum retry attempts for rate-limited requests (default: 5)
#   TELEGRAM_INITIAL_RETRY_DELAY: Initial delay in seconds for exponential backoff (default: 1.0)
#   TELEGRAM_MAX_RETRY_DELAY: Maximum delay in seconds (default: 300.0 = 5 minutes)
#   TELEGRAM_BACKOFF_MULTIPLIER: Multiplier for exponential backoff (default: 2.0)
#
API_ID = int(os.environ.get('TELEGRAM_API_ID') or os.environ.get('TG_API_ID') or os.environ.get('API_ID') or 0)
API_HASH = os.environ.get('TELEGRAM_API_HASH') or os.environ.get('TG_API_HASH') or os.environ.get('API_HASH') or ''
SESSION_STRING = os.environ.get('SESSION_STRING') or os.environ.get('TG_SESSION_STRING') or os.environ.get('SESSION')
SESSION_NAME = os.environ.get('TG_SESSION') or 'tutordex.session'

# Channels: support CHANNEL_LIST as JSON array or CHANNELS comma-separated
_channel_list_raw = os.environ.get('CHANNEL_LIST') or os.environ.get('CHANNELS') or os.environ.get('CHANNELS_LIST') or ''
CHANNELS = []
if _channel_list_raw:
    s = _channel_list_raw.strip()
    if s.startswith('[') and s.endswith(']'):
        try:
            CHANNELS = json.loads(s)
        except Exception:
            # try to strip quotes and split
            CHANNELS = [x.strip().strip('"').strip("'") for x in s[1:-1].split(',') if x.strip()]
    else:
        CHANNELS = [x.strip() for x in s.split(',') if x.strip()]

HISTORIC_FETCH = int(os.environ.get('HISTORIC_FETCH', '3'))  # messages per channel to backfill on start
_default_processed_store = str(HERE / 'processed_ids.json')
PROCESSED_STORE = Path(os.environ.get('PROCESSED_STORE', _default_processed_store))

if not API_ID or not API_HASH or not CHANNELS:
    raise SystemExit('Set TELEGRAM_API_ID, TELEGRAM_API_HASH and CHANNEL_LIST (or CHANNELS) in .env or environment')

setup_logging()
logger = logging.getLogger('read_assignments')
if _env_parse_error:
    log_event(logger, logging.WARNING, "env_parse_failed", env_path=str(ENV_PATH), error=_env_parse_error)
for err in _optional_import_errors:
    log_event(logger, logging.DEBUG, "optional_import_failed", error=err)

# Lightweight heartbeat file for monitoring/alerting.
# Updated on every processed message (ok/skipped/error) so an external monitor can detect stalls.
HEARTBEAT_PATH = HERE / os.environ.get("HEARTBEAT_FILE", "monitoring/heartbeat.json")
_METRICS: dict[str, Any] = {
    "start_ts": int(time.time()),
    "seen": 0,
    "ok": 0,
    "skipped": 0,
    "error": 0,
    "skipped_reasons": {},
    "channels": {},
}


def _write_heartbeat(
    *,
    status: str,
    cid: str,
    channel_link: str,
    message_id: Any,
    reason: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
) -> None:
    try:
        HEARTBEAT_PATH.parent.mkdir(parents=True, exist_ok=True)
        now = int(time.time())

        if status in {"ok", "skipped", "error"}:
            _METRICS["seen"] = int(_METRICS.get("seen") or 0) + 1
            if status == "ok":
                _METRICS["ok"] = int(_METRICS.get("ok") or 0) + 1
            elif status == "skipped":
                _METRICS["skipped"] = int(_METRICS.get("skipped") or 0) + 1
                if reason:
                    sr = _METRICS.get("skipped_reasons") or {}
                    sr[reason] = int(sr.get(reason) or 0) + 1
                    _METRICS["skipped_reasons"] = sr
            else:
                _METRICS["error"] = int(_METRICS.get("error") or 0) + 1

        if channel_link:
            ch = _METRICS.get("channels") or {}
            ch[channel_link] = int(ch.get(channel_link) or 0) + 1
            _METRICS["channels"] = ch

        payload = {
            "ts": now,
            "status": status,
            "cid": cid,
            "channel": channel_link,
            "message_id": message_id,
            "reason": reason,
            "details": details or None,
            "metrics": _METRICS,
        }

        tmp = HEARTBEAT_PATH.with_suffix(HEARTBEAT_PATH.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(str(tmp), str(HEARTBEAT_PATH))
    except Exception:
        # Heartbeat must never break the ingestion pipeline.
        logger.debug("heartbeat_write_failed", exc_info=True)


async def _heartbeat_tick_loop(*, interval_s: int = 60) -> None:
    while True:
        try:
            _write_heartbeat(status="idle", cid="-", channel_link="-", message_id=None, reason="tick")
        except Exception:
            pass
        await asyncio.sleep(max(5, int(interval_s)))

# Rate limiting and retry configuration
MAX_RETRIES = int(os.environ.get('TELEGRAM_MAX_RETRIES', '5'))
INITIAL_RETRY_DELAY = float(os.environ.get('TELEGRAM_INITIAL_RETRY_DELAY', '1.0'))
MAX_RETRY_DELAY = float(os.environ.get('TELEGRAM_MAX_RETRY_DELAY', '300.0'))  # 5 minutes max
BACKOFF_MULTIPLIER = float(os.environ.get('TELEGRAM_BACKOFF_MULTIPLIER', '2.0'))


async def retry_with_backoff(
    func: Callable,
    *args,
    max_retries: int = MAX_RETRIES,
    initial_delay: float = INITIAL_RETRY_DELAY,
    max_delay: float = MAX_RETRY_DELAY,
    backoff_multiplier: float = BACKOFF_MULTIPLIER,
    **kwargs
) -> Any:
    """
    Retry an async function with exponential backoff and jitter.

    Handles Telegram rate limiting errors (FloodWaitError, SlowModeWaitError, FloodError)
    and implements exponential backoff with jitter to prevent IP bans.

    Args:
        func: The async function to retry
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds (cap for exponential backoff)
        backoff_multiplier: Multiplier for exponential backoff
        *args, **kwargs: Arguments to pass to the function

    Returns:
        The result of the function call

    Raises:
        The last exception if all retries are exhausted
    """
    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except FloodWaitError as e:
            # Telegram tells us exactly how long to wait
            wait_time = e.seconds
            last_exception = e

            if attempt >= max_retries:
                logger.error(f'FloodWaitError: Max retries ({max_retries}) reached. Last wait time: {wait_time}s')
                raise

            # Add small jitter to avoid thundering herd
            jitter = random.uniform(0, min(5, wait_time * 0.1))
            total_wait = wait_time + jitter

            logger.warning(
                "FloodWaitError: rate limit hit",
                extra={"wait_seconds": total_wait, "attempt": attempt}
            )

            await asyncio.sleep(total_wait)

        except SlowModeWaitError as e:
            # Similar to FloodWaitError but for slow mode
            wait_time = e.seconds
            last_exception = e

            if attempt >= max_retries:
                logger.error(f'SlowModeWaitError: Max retries ({max_retries}) reached. Last wait time: {wait_time}s')
                raise

            jitter = random.uniform(0, min(2, wait_time * 0.1))
            total_wait = wait_time + jitter

            logger.warning(f'SlowModeWaitError: Slow mode active. Waiting {total_wait:.1f}s (attempt {attempt + 1}/{max_retries})')
            await asyncio.sleep(total_wait)

        except FloodError as e:
            # Generic flood error without specific wait time
            last_exception = e

            if attempt >= max_retries:
                logger.error(f'FloodError: Max retries ({max_retries}) reached')
                raise

            # Use exponential backoff for generic flood errors
            delay = min(initial_delay * (backoff_multiplier ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.2)  # 20% jitter
            total_wait = delay + jitter

            logger.warning(f'FloodError: Rate limit hit. Waiting {total_wait:.1f}s (attempt {attempt + 1}/{max_retries})')
            await asyncio.sleep(total_wait)

        except Exception as e:
            # For non-rate-limit errors, use exponential backoff but with fewer retries
            last_exception = e

            # Don't retry certain errors
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['auth', 'permission', 'forbidden', 'not found', 'invalid']):
                logger.error(f'Non-retryable error: {type(e).__name__}: {e}')
                raise

            if attempt >= max_retries:
                logger.error(f'{type(e).__name__}: Max retries ({max_retries}) reached')
                raise

            # Exponential backoff with jitter
            delay = min(initial_delay * (backoff_multiplier ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.3)  # 30% jitter
            total_wait = delay + jitter

            logger.warning(f'{type(e).__name__}: {e}. Retrying in {total_wait:.1f}s (attempt {attempt + 1}/{max_retries})')
            await asyncio.sleep(total_wait)

    # Should never reach here, but just in case
    if last_exception:
        raise last_exception


def load_processed():
    if PROCESSED_STORE.exists():
        try:
            return json.loads(PROCESSED_STORE.read_text(encoding='utf8'))
        except Exception:
            return {}
    return {}


def save_processed(d):
    try:
        PROCESSED_STORE.write_text(json.dumps(d), encoding='utf8')
    except Exception as e:
        logger.warning('Failed to persist processed ids to %s: %s', PROCESSED_STORE, e)


def build_message_link(entity, msg_id: int) -> Optional[str]:
    # Try username first (public channels): https://t.me/username/message_id
    uname = getattr(entity, 'username', None)
    if uname:
        u = str(uname).strip()
        # normalize if something upstream passed a link-like username
        if u.startswith('http://') or u.startswith('https://'):
            u = u.rstrip('/').split('/')[-1]
        elif u.startswith('t.me/'):
            u = u.split('/')[-1]
        return f'https://t.me/{u}/{msg_id}'
    # Fallback for private channels/supergroups: t.me/c/{channel_id}/{msg_id}
    cid = getattr(entity, 'id', None)
    if cid is None:
        return None
    return f'https://t.me/c/{abs(int(cid))}/{msg_id}'


# compilation detection configuration
COMPILATION_THRESH = {
    'code_hits': int(os.environ.get('COMP_CODE_HITS', '3')),
    'label_hits': int(os.environ.get('COMP_LABEL_HITS', '5')),
    'postal_hits': int(os.environ.get('COMP_POSTAL_HITS', '3')),
    'url_hits': int(os.environ.get('COMP_URL_HITS', '3')),
    'block_count': int(os.environ.get('COMP_BLOCK_COUNT', '12')),
}

LABEL_RE = re.compile(r'(^|\n)\s*(Subject|Rate|Address|Location):', re.I)
CODE_RE = re.compile(r'(code|assignment|job|id)\s*[:#]\s*\w+', re.I)
POSTAL_RE = re.compile(r'\b\d{6}\b')
URL_RE = re.compile(r'https?://|t\.me/|www\.')

COMPILATION_STORE = HERE / os.environ.get('COMPILATION_FILE', 'compilations.jsonl')
COMPILATION_BUMP_ENABLED = str(os.environ.get("COMPILATION_BUMP_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "y", "on"}
FORWARDED_BUMP_ENABLED = str(os.environ.get("FORWARDED_BUMP_ENABLED", "true")).strip().lower() in {"1", "true", "yes", "y", "on"}

_COMP_CODE_HINT_RE = re.compile(
    r"(?i)\b(?:code\s*id|assignment\s*code|assignment|job|code|id)\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9_-]{2,24})"
)
_COMP_HASHTAG_CODE_RE = re.compile(r"#([A-Za-z]\d{3,10}[A-Za-z0-9]{0,6})\b")
_COMP_TOKEN_CODE_RE = re.compile(r"\b([A-Za-z]\d{3,10}[A-Za-z0-9]{0,6})\b")


def _extract_assignment_codes_from_compilation(text: str) -> list[str]:
    """
    Best-effort extraction of assignment codes from a compilation message.
    Avoid common false positives like 6-digit postal codes.
    """
    if not text:
        return []

    candidates: list[str] = []
    candidates.extend(_COMP_CODE_HINT_RE.findall(text))
    candidates.extend(_COMP_HASHTAG_CODE_RE.findall(text))
    candidates.extend(_COMP_TOKEN_CODE_RE.findall(text))

    out: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        s = str(c).strip().strip(",.()[]{}<>\"'")
        if not s:
            continue
        if s.isdigit() and len(s) == 6:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _load_supabase_bump_config() -> dict[str, Any]:
    url = resolve_supabase_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    enabled = bool(str(os.environ.get("SUPABASE_ENABLED", "")).strip().lower() in {"1", "true", "yes", "y", "on"} and url and key)
    return {
        "enabled": enabled,
        "url": url,
        "key": key,
        "assignments_table": (os.environ.get("SUPABASE_ASSIGNMENTS_TABLE") or "assignments").strip(),
    }


def _supabase_headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
    }


def _bump_assignments_from_compilation(
    *,
    channel_link: str,
    compilation_text: str,
    last_seen_iso: Optional[str],
    cid: str,
) -> dict[str, Any]:
    """
    When a compilation post is detected (and skipped for extraction), bump matching assignments in Supabase.

    This is best-effort and should never break the ingestion pipeline.
    """
    if not COMPILATION_BUMP_ENABLED:
        return {"ok": False, "skipped": True, "reason": "disabled"}

    cfg = _load_supabase_bump_config()
    if not cfg.get("enabled"):
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    codes = _extract_assignment_codes_from_compilation(compilation_text or "")
    if not codes:
        return {"ok": True, "bumped": 0, "codes": 0, "skipped": True, "reason": "no_codes_found"}

    base = f"{cfg['url']}/rest/v1"
    headers = _supabase_headers(str(cfg["key"]))
    table = str(cfg["assignments_table"])

    last_seen_iso = last_seen_iso or datetime.now(timezone.utc).isoformat()

    bumped = 0
    not_found = 0
    errors = 0

    with bind_log_context(cid=cid, channel=channel_link, step="compilation_bump"):
        for code in codes:
            try:
                q = (
                    f"{base}/{table}"
                    f"?select=id,bump_count"
                    f"&agency_link=eq.{requests.utils.quote(channel_link, safe='')}"
                    f"&external_id=eq.{requests.utils.quote(code, safe='')}"
                    f"&limit=1"
                )
                r = requests.get(q, headers=headers, timeout=20)
                if r.status_code >= 400:
                    errors += 1
                    log_event(logger, logging.DEBUG, "compilation_bump_lookup_failed", status_code=r.status_code, code=code)
                    continue
                data = r.json()
                if not isinstance(data, list) or not data:
                    not_found += 1
                    continue
                row = data[0]
                aid = row.get("id")
                old = row.get("bump_count")
                try:
                    old_i = int(old) if old is not None else 0
                except Exception:
                    old_i = 0
                new_i = old_i + 1

                patch_url = f"{base}/{table}?id=eq.{requests.utils.quote(str(aid), safe='')}"
                pr = requests.patch(patch_url, headers={**headers, "prefer": "return=minimal"},
                                    json={"bump_count": new_i, "last_seen": last_seen_iso}, timeout=20)
                if pr.status_code < 400:
                    bumped += 1
                else:
                    errors += 1
                    log_event(logger, logging.DEBUG, "compilation_bump_patch_failed", status_code=pr.status_code, code=code, assignment_id=aid)
            except Exception as e:
                errors += 1
                log_event(logger, logging.DEBUG, "compilation_bump_exception", code=code, error=str(e))

        log_event(logger, logging.INFO, "compilation_bump_summary", codes=len(codes), bumped=bumped, not_found=not_found, errors=errors)

    return {"ok": errors == 0, "bumped": bumped, "codes": len(codes), "not_found": not_found, "errors": errors}


def _bump_assignments_by_external_id(
    *,
    external_id: str,
    last_seen_iso: Optional[str],
    cid: str,
    agency_link: Optional[str] = None,
) -> dict[str, Any]:
    """
    Best-effort bump for a single assignment external_id (e.g. assignment_code).

    For forwarded messages, the posting channel may not match the assignment's original agency.

    If `agency_link` is provided (e.g. derived from Telegram forward metadata), the bump will be
    constrained to that agency/source. Otherwise, it bumps by `external_id` across all agencies.
    """
    if not FORWARDED_BUMP_ENABLED:
        return {"ok": False, "skipped": True, "reason": "disabled"}

    cfg = _load_supabase_bump_config()
    if not cfg.get("enabled"):
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    ext = str(external_id or "").strip()
    if not ext:
        return {"ok": True, "bumped": 0, "skipped": True, "reason": "missing_external_id"}

    base = f"{cfg['url']}/rest/v1"
    headers = _supabase_headers(str(cfg["key"]))
    table = str(cfg["assignments_table"])

    last_seen_iso = last_seen_iso or datetime.now(timezone.utc).isoformat()

    bumped = 0
    not_found = 0
    errors = 0

    with bind_log_context(cid=cid, step="forwarded_bump"):
        try:
            q = (
                f"{base}/{table}?select=id,bump_count"
                + (f"&agency_link=eq.{requests.utils.quote(str(agency_link), safe='')}" if agency_link else "")
                + f"&external_id=eq.{requests.utils.quote(ext, safe='')}&limit=25"
            )
            r = requests.get(q, headers=headers, timeout=20)
            if r.status_code >= 400:
                return {"ok": False, "bumped": 0, "errors": 1, "status_code": r.status_code}
            data = r.json()
            if not isinstance(data, list) or not data:
                not_found = 1
                return {"ok": True, "bumped": 0, "not_found": not_found}

            for row in data:
                try:
                    aid = row.get("id")
                    old = row.get("bump_count")
                    try:
                        old_i = int(old) if old is not None else 0
                    except Exception:
                        old_i = 0
                    new_i = old_i + 1

                    patch_url = f"{base}/{table}?id=eq.{requests.utils.quote(str(aid), safe='')}"
                    pr = requests.patch(
                        patch_url,
                        headers={**headers, "prefer": "return=minimal"},
                        json={"bump_count": new_i, "last_seen": last_seen_iso},
                        timeout=20,
                    )
                    if pr.status_code < 400:
                        bumped += 1
                    else:
                        errors += 1
                        log_event(
                            logger,
                            logging.DEBUG,
                            "forwarded_bump_patch_failed",
                            status_code=pr.status_code,
                            external_id=ext,
                            assignment_id=aid,
                        )
                except Exception as e:
                    errors += 1
                    log_event(logger, logging.DEBUG, "forwarded_bump_patch_exception", external_id=ext, error=str(e))
        except Exception as e:
            errors += 1
            log_event(logger, logging.DEBUG, "forwarded_bump_exception", external_id=ext, error=str(e))

        log_event(logger, logging.INFO, "forwarded_bump_summary", external_id=ext, bumped=bumped, not_found=not_found, errors=errors)

    return {"ok": errors == 0, "bumped": bumped, "not_found": not_found, "errors": errors}


async def _try_get_forwarded_source_channel_link(client, msg) -> Optional[str]:
    """
    Best-effort: derive a `t.me/<username>` from Telethon forward metadata.

    Returns None when we can't determine a public username.
    """
    fwd = getattr(msg, "fwd_from", None) or getattr(msg, "forward", None)
    if not fwd:
        return None

    candidates: list[Any] = []
    for attr in ("from_id", "saved_from_peer", "saved_from_id"):
        peer = getattr(fwd, attr, None)
        if peer is not None:
            candidates.append(peer)

    channel_id = getattr(fwd, "channel_id", None)
    if channel_id is not None:
        candidates.append(channel_id)

    for peer in candidates:
        try:
            ent = await retry_with_backoff(client.get_entity, peer)
            uname = getattr(ent, "username", None)
            if uname:
                return f"t.me/{str(uname).strip()}"
        except Exception:
            continue

    return None


def is_compilation(text: str) -> tuple[bool, list[str]]:
    """
    Check if text appears to be a compilation message.

    Returns:
        tuple: (is_compilation: bool, triggered_checks: list[str])
    """
    if not text:
        return False, []

    code_hits = len(CODE_RE.findall(text))
    label_hits = len(LABEL_RE.findall(text))
    postal_codes = {c.strip() for c in POSTAL_RE.findall(text) if str(c).strip()}
    postal_hits = len(postal_codes)
    url_hits = len(URL_RE.findall(text))
    # count blocks separated by two or more newlines
    blocks = [b for b in re.split(r'\n{2,}', text) if b.strip()]
    block_count = len(blocks)

    triggered = []

    if code_hits >= COMPILATION_THRESH['code_hits']:
        triggered.append(f"Multiple assignment codes detected ({code_hits} codes found, threshold: {COMPILATION_THRESH['code_hits']})")
    if label_hits >= COMPILATION_THRESH['label_hits'] and block_count >= 2:
        triggered.append(
            f"Multiple labeled sections ({label_hits} labels found, threshold: {COMPILATION_THRESH['label_hits']}, {block_count} blocks)")
    if postal_hits >= COMPILATION_THRESH['postal_hits']:
        triggered.append(
            f"Multiple unique postal codes detected ({postal_hits} unique postal codes found, threshold: {COMPILATION_THRESH['postal_hits']})"
        )
    if url_hits >= COMPILATION_THRESH['url_hits']:
        triggered.append(f"Multiple URLs detected ({url_hits} URLs found, threshold: {COMPILATION_THRESH['url_hits']})")
    if block_count >= COMPILATION_THRESH['block_count'] and label_hits >= 1:
        triggered.append(
            f"Multiple content blocks ({block_count} blocks found, threshold: {COMPILATION_THRESH['block_count']}, with {label_hits} labels)")

    return len(triggered) > 0, triggered


def log_compilation(entity, msg, raw_text: str, reason: str = ''):
    try:
        msg_id = getattr(msg, 'id', None)
        entry = {
            'ts': int(time.time()),
            'channel_id': getattr(entity, 'id', None),
            'channel_username': getattr(entity, 'username', None),
            'channel_title': getattr(entity, 'title', None),
            'message_id': msg_id,
            'message_link': build_message_link(entity, msg_id) if (entity is not None and msg_id is not None) else None,
            'reason': reason,
            'excerpt': (raw_text[:800] + '...') if raw_text and len(raw_text) > 800 else raw_text,
        }
        with open(COMPILATION_STORE, 'a', encoding='utf8') as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + '\n')
        logger.info('Logged compilation message %s to %s', msg_id or '<no-id>', COMPILATION_STORE)
    except Exception:
        logger.exception('Failed to log compilation')


def _get_skipped_target():
    chat = os.environ.get('SKIPPED_MESSAGES_CHAT_ID')
    thread = os.environ.get('SKIPPED_MESSAGES_THREAD_ID')
    if not chat:
        return None, None
    try:
        chat_id = int(chat)
        # Convert to Telethon format: channels/supergroups need -100 prefix
        # If the ID is positive and looks like a channel ID, convert it
        if chat_id > 0:
            # Telegram channel IDs in Telethon are stored as -100{channel_id}
            chat_id = -1000000000000 - chat_id
    except Exception:
        chat_id = chat
    try:
        thread_id = int(thread) if thread is not None else None
    except Exception:
        thread_id = None
    return chat_id, thread_id


async def forward_skipped_message(client, msg, from_entity, reason: str = '', details: Optional[list[str]] = None):
    """Forward or resend the skipped message to the configured moderation group.

    Attempts to use Telethon's forward_messages to preserve media and authorship; falls back
    to send_message/send_file if forwarding is not supported.

    After forwarding, sends a follow-up explanation message with the skip reason.

    Uses retry_with_backoff to handle Telegram rate limits.

    Note: message_thread_id is not supported for forwarding messages.

    Args:
        client: Telethon client
        msg: The message to forward
        from_entity: The entity the message came from
        reason: Short reason code (e.g., 'forwarded', 'compilation_detected')
        details: Optional list of detailed reasons (used for compilation checks)
    """
    target_chat, thread_id = _get_skipped_target()
    if not target_chat:
        logger.debug('No SKIPPED_MESSAGES_CHAT_ID configured; not forwarding skipped message')
        return

    forwarded_successfully = False

    try:
        # Resolve the target to a proper entity before attempting to forward/send.
        # If resolution fails (e.g., not accessible), fall back to the original value.
        try:
            resolved_target = await retry_with_backoff(client.get_entity, target_chat)
        except Exception:
            resolved_target = target_chat

        # Try to forward preserving original sender with retry logic
        from_peer = from_entity if from_entity is not None else None
        try:
            await retry_with_backoff(
                client.forward_messages,
                entity=resolved_target,
                messages=[msg.id],
                from_peer=from_peer
            )
            logger.info('Forwarded skipped message %s to %s (reason=%s)', getattr(msg, 'id', '<no-id>'), target_chat, reason)
            forwarded_successfully = True
        except TypeError:
            # some Telethon versions may not accept list; try with single message
            try:
                await retry_with_backoff(
                    client.forward_messages,
                    entity=resolved_target,
                    messages=msg.id,
                    from_peer=from_peer
                )
                logger.info('Forwarded skipped message %s to %s (reason=%s)', getattr(msg, 'id', '<no-id>'), target_chat, reason)
                forwarded_successfully = True
            except Exception:
                pass
        except Exception:
            # try fallback below
            pass

        # Fallback: resend text and media with retry logic
        if not forwarded_successfully:
            text = getattr(msg, 'message', '') or ''
            media = getattr(msg, 'media', None)
            if media is not None:
                try:
                    await retry_with_backoff(
                        client.send_file,
                        resolved_target,
                        media,
                        caption=text
                    )
                    logger.info('Resent skipped media message %s to %s (reason=%s)', getattr(msg, 'id', '<no-id>'), target_chat, reason)
                    forwarded_successfully = True
                except Exception:
                    logger.exception('Failed to resend media for skipped message; will try send_message')

            # plain text fallback with retry logic
            if not forwarded_successfully:
                try:
                    await retry_with_backoff(
                        client.send_message,
                        resolved_target,
                        text or '(no text)'
                    )
                    logger.info('Sent skipped message text %s to %s (reason=%s)', getattr(msg, 'id', '<no-id>'), target_chat, reason)
                    forwarded_successfully = True
                except Exception:
                    logger.exception('Failed to send skipped message to moderation channel')

        # Send follow-up explanation message with retry logic
        if forwarded_successfully:
            try:
                reason_map = {
                    'forwarded': '⚠️ **Skipped: Forwarded Message**\nThis message was skipped because it is a forwarded message from another channel.',
                    'compilation_detected': '⚠️ **Skipped: Compilation Detected**\nThis message appears to contain multiple assignments (compilation post) and was not processed individually.',
                    'validation_failed': '⚠️ **Skipped: Validation Failed**\nThis message failed validation because required fields were missing or malformed (see details).',
                }
                explanation = reason_map.get(reason, f'⚠️ **Skipped: {reason}**\nThis message was skipped during processing.')

                # Add detailed compilation/validation checks if provided
                if details and len(details) > 0:
                    explanation += '\n\n**Triggered Checks / Context:**'
                    for detail in details:
                        explanation += f'\n• {detail}'

                # Add message link if available
                msg_id = getattr(msg, 'id', None)
                if msg_id is not None:
                    msg_link = build_message_link(from_entity, msg_id)
                    if msg_link:
                        explanation += f'\n\n🔗 Original message: {msg_link}'

                # Telegram messages have size limits; large compilation details can exceed it.
                # Send in chunks to preserve all details without failing the send.
                max_len = 3500
                if len(explanation) <= max_len:
                    await retry_with_backoff(client.send_message, resolved_target, explanation)
                else:
                    lines = explanation.splitlines()
                    buf = ""
                    part = 0
                    for ln in lines:
                        candidate = (buf + "\n" + ln) if buf else ln
                        if len(candidate) > max_len and buf:
                            part += 1
                            await retry_with_backoff(
                                client.send_message,
                                resolved_target,
                                (buf if part == 1 else f"(cont.)\n{buf}"),
                            )
                            buf = ln
                        else:
                            buf = candidate
                    if buf:
                        part += 1
                        await retry_with_backoff(
                            client.send_message,
                            resolved_target,
                            (buf if part == 1 else f"(cont.)\n{buf}"),
                        )
                logger.info('Sent skip reason explanation for message %s', getattr(msg, 'id', '<no-id>'))
            except Exception:
                logger.exception('Failed to send skip reason explanation')

    except Exception:
        logger.exception('Unexpected error forwarding skipped message')


async def process_message(client, msg, entity, processed):
    try:
        # prepare raw text early (some messages may have forwarding metadata but still contain text)
        raw = (getattr(msg, 'message', None) or '')
        if raw is None:
            raw = ''
        raw = raw.strip()

        channel_id = str(getattr(entity, 'id', 'unknown'))
        msg_id = getattr(msg, 'id', None)
        cid = f'{channel_id}:{msg_id}'
        channel_username = getattr(entity, 'username', None)
        channel_link = f"t.me/{channel_username}" if channel_username else ""

        with bind_log_context(cid=cid, message_id=msg_id, channel=channel_link):
            overall_start = timed()
            step_ms: dict[str, float] = {}
            step_ok: dict[str, Any] = {}

            set_step("filter")

            # ignore forwarded messages
            try:
                if getattr(msg, 'fwd_from', None) or getattr(msg, 'forward', None) or (
                    hasattr(msg, 'forwarded_from') and getattr(msg, 'forwarded_from', None)
                ):
                    set_step("forwarded.extract_for_bump")
                    date_obj = getattr(msg, 'date', None)
                    last_seen_iso = date_obj.isoformat() if date_obj else None

                    assignment_code = None
                    forwarded_source_link = None
                    try:
                        t0 = timed()
                        parsed = await run_in_thread(extract_assignment_with_model, raw, channel_link, cid=cid)
                        step_ms["extract_ms"] = round((timed() - t0) * 1000.0, 2)
                        assignment_code = (parsed or {}).get("assignment_code") if isinstance(parsed, dict) else None
                        try:
                            forwarded_source_link = await _try_get_forwarded_source_channel_link(client, msg)
                        except Exception:
                            forwarded_source_link = None
                    except Exception as e:
                        step_ms["extract_ms"] = round((timed() - t0) * 1000.0, 2) if "t0" in locals() else 0.0
                        logger.debug("Forwarded extract failed (non-fatal)", exc_info=True)
                        assignment_code = None

                    bump_res = None
                    if assignment_code:
                        try:
                            set_step("forwarded.bump")
                            bump_res = _bump_assignments_by_external_id(
                                external_id=str(assignment_code),
                                last_seen_iso=last_seen_iso,
                                cid=cid,
                                agency_link=forwarded_source_link,
                            )
                        except Exception:
                            logger.debug("Forwarded bump failed (non-fatal)", exc_info=True)
                            bump_res = {"ok": False, "error": "exception"}

                    log_event(
                        logger,
                        logging.INFO,
                        "message_skipped",
                        reason="forwarded_bumped",
                        assignment_code=assignment_code,
                        forwarded_source=forwarded_source_link,
                        bump=bump_res,
                    )
                    _write_heartbeat(
                        status="skipped",
                        cid=cid,
                        channel_link=channel_link,
                        message_id=msg_id,
                        reason="forwarded_bumped",
                        details={"assignment_code": assignment_code, "forwarded_source": forwarded_source_link, "bump": bump_res},
                    )
                    try:
                        await forward_skipped_message(client, msg, entity, reason='forwarded')
                    except Exception:
                        logger.exception('Failed to forward forwarded message to moderation chat')

                    processed.add(cid)
                    if len(processed) % 50 == 0:
                        save_processed(list(processed))

                    step_ok["skipped"] = "forwarded_bumped"
                    step_ok["assignment_code"] = assignment_code
                    step_ok["bump"] = bump_res
                    step_ms["total_ms"] = round((timed() - overall_start) * 1000.0, 2)
                    log_event(logger, logging.INFO, "pipeline_summary", ok=False, skipped="forwarded_bumped", ms=step_ms)
                    return
            except Exception:
                logger.debug("Forwarded detection failed; continuing", exc_info=True)

        # capture date early for downstream use (e.g., compilation bump)
            date_obj = getattr(msg, 'date', None)

        # detect compilations (multi-assignment posts)
            set_step("filter.compilation")
            try:
                is_comp, comp_details = is_compilation(raw)
                if is_comp:
                    set_step("skip.compilation")
                    log_event(logger, logging.INFO, "message_skipped", reason="compilation_detected", checks=len(comp_details))
                    _write_heartbeat(
                        status="skipped",
                        cid=cid,
                        channel_link=channel_link,
                        message_id=msg_id,
                        reason="compilation_detected",
                        details={"checks": len(comp_details)},
                    )
                    log_compilation(entity, msg, raw, reason='compilation_detected')

                    codes = _extract_assignment_codes_from_compilation(raw or "")
                    forward_details = list(comp_details or [])
                    if codes:
                        # Do not cap: include all codes, but chunk into multiple lines to avoid overly long messages.
                        forward_details.append(f"Detected assignment codes ({len(codes)}):")
                        chunk: list[str] = []
                        chunk_len = 0
                        for code in codes:
                            s = str(code)
                            add_len = len(s) + (2 if chunk else 0)  # ", " separator
                            if chunk and (chunk_len + add_len) > 800:
                                forward_details.append(", ".join(chunk))
                                chunk = []
                                chunk_len = 0
                            chunk.append(s)
                            chunk_len += add_len
                        if chunk:
                            forward_details.append(", ".join(chunk))
                    else:
                        forward_details.append("Detected assignment codes: <none found>")

                    # Best-effort: use compilation post to bump assignments.last_seen/bump_count in Supabase.
                    try:
                        bump_res = _bump_assignments_from_compilation(
                            channel_link=channel_link,
                            compilation_text=raw,
                            last_seen_iso=(date_obj.isoformat() if date_obj else None),
                            cid=cid,
                        )
                        log_event(logger, logging.INFO, "compilation_bump_result", **bump_res)
                    except Exception:
                        logger.debug("Compilation bump failed (non-fatal)", exc_info=True)
                    try:
                        await forward_skipped_message(client, msg, entity, reason='compilation_detected', details=forward_details)
                    except Exception:
                        logger.exception('Failed to forward skipped compilation message')
                    step_ok["skipped"] = "compilation_detected"
                    step_ms["total_ms"] = round((timed() - overall_start) * 1000.0, 2)
                    log_event(logger, logging.INFO, "pipeline_summary", ok=False, skipped="compilation_detected", ms=step_ms)
                    return
            except Exception:
                logger.exception('Compilation detection failed, continuing')

            if not raw:
                log_event(logger, logging.DEBUG, "message_skipped", reason="empty_text")
                _write_heartbeat(status="skipped", cid=cid, channel_link=channel_link, message_id=msg_id, reason="empty_text")
                return
            msg_key = cid
            if msg_key in processed:
                log_event(logger, logging.DEBUG, "message_skipped", reason="already_processed")
                _write_heartbeat(status="skipped", cid=cid, channel_link=channel_link, message_id=msg_id, reason="already_processed")
                return

            set_step("start")
            log_event(
                logger,
                logging.INFO,
                "message_processing_start",
                channel_title=getattr(entity, 'title', None),
                channel_id=channel_id,
            )

        # call extractor (run in thread if it's synchronous)
            set_step("extract")
            try:
                t0 = timed()
                parsed = await run_in_thread(extract_assignment_with_model, raw, channel_link, cid=cid)
                step_ms["extract_ms"] = round((timed() - t0) * 1000.0, 2)
                step_ok["extract_ok"] = True
            except Exception as e:
                step_ms["extract_ms"] = round((timed() - t0) * 1000.0, 2) if "t0" in locals() else 0.0
                step_ok["extract_ok"] = False
                logger.exception('Extractor failed error=%s', e)
                parsed = {'error': 'extract_failed', 'error_detail': str(e)}

        # Check if validation failed (missing required fields)
            if isinstance(parsed, dict) and parsed.get('error') == 'validation_failed':
                set_step("skip.validation")
                validation_errors = parsed.get('validation_errors', [])
                log_event(logger, logging.INFO, "message_skipped", reason="validation_failed", errors=validation_errors)
                _write_heartbeat(
                    status="skipped",
                    cid=cid,
                    channel_link=channel_link,
                    message_id=msg_id,
                    reason="validation_failed",
                    details={"errors": len(validation_errors) if isinstance(validation_errors, list) else None},
                )
                try:
                    details = [f"Validation error: {err.replace('_', ' ')}" for err in validation_errors]
                    await forward_skipped_message(client, msg, entity, reason='validation_failed', details=details)
                except Exception:
                    logger.exception('Failed to forward skipped validation failure message')

                step_ok["skipped"] = "validation_failed"
                step_ok["validation_errors"] = validation_errors
                step_ms["total_ms"] = round((timed() - overall_start) * 1000.0, 2)
                log_event(
                    logger,
                    logging.INFO,
                    "pipeline_summary",
                    ok=False,
                    skipped="validation_failed",
                    errors=validation_errors,
                    ms=step_ms,
                )
                return

        # enrich with metadata
            payload = {
                'cid': cid,
                'channel_id': getattr(entity, 'id', None),
                'channel_username': channel_username,
                'channel_title': getattr(entity, 'title', None),
                'channel_link': channel_link,
                'message_id': msg.id,
                'message_link': build_message_link(entity, msg.id),
                'raw_text': raw,
                'date': date_obj.isoformat() if date_obj else None,
                'parsed': parsed,
            }

        # Best-effort enrichment (postal code estimation etc.) before broadcast
            set_step("enrich")
            try:
                t0 = timed()
                payload = await run_in_thread(process_parsed_payload, payload, False)
                step_ms["enrich_ms"] = round((timed() - t0) * 1000.0, 2)
                step_ok["enrich_ok"] = True
            except Exception as e:
                step_ok["enrich_ok"] = False
                step_ms["enrich_ms"] = round((timed() - t0) * 1000.0, 2) if "t0" in locals() else 0.0
                logger.exception('Enrichment failed error=%s', e)

        # Contract validation before persistence/broadcast
            set_step("validate.schema")
            ok_schema, schema_errors = await run_in_thread(validate_parsed_assignment, payload.get("parsed") or {})
        if not ok_schema:
            log_event(logger, logging.INFO, "message_skipped", reason="schema_validation_failed", errors=schema_errors)
            _write_heartbeat(
                status="skipped",
                cid=cid,
                channel_link=channel_link,
                message_id=msg_id,
                reason="schema_validation_failed",
                details={"errors": schema_errors},
            )
            try:
                details = [f"Schema error: {err.replace('_', ' ')}" for err in schema_errors]
                try:
                    parsed_json = json.dumps(payload.get("parsed") or {}, ensure_ascii=False, indent=2)
                    if len(parsed_json) > 1800:
                        parsed_json = parsed_json[:1800] + "... (truncated)"
                    details.append(f"LLM parsed JSON:\n```json\n{parsed_json}\n```")
                except Exception:
                    details.append("LLM parsed JSON: <unserializable>")
                await forward_skipped_message(client, msg, entity, reason='validation_failed', details=details)
            except Exception:
                logger.exception('Failed to forward skipped schema validation failure message')

            step_ok["skipped"] = "schema_validation_failed"
            step_ok["schema_errors"] = schema_errors
            step_ms["total_ms"] = round((timed() - overall_start) * 1000.0, 2)
            log_event(
                logger,
                logging.INFO,
                "pipeline_summary",
                ok=False,
                skipped="schema_validation_failed",
                errors=schema_errors,
                ms=step_ms,
            )
            return

        # Best-effort persistence to Supabase (optional)
            set_step("supabase")
            if persist_assignment_to_supabase is not None:
                try:
                    t0 = timed()
                    persist_res = await run_in_thread(persist_assignment_to_supabase, payload)
                    step_ms["supabase_ms"] = round((timed() - t0) * 1000.0, 2)
                    if persist_res and persist_res.get("skipped"):
                        step_ok["supabase"] = {"skipped": True, "reason": persist_res.get("reason")}
                        log_event(logger, logging.DEBUG, "supabase_persist_skipped", reason=persist_res.get("reason"))
                    elif persist_res:
                        step_ok["supabase"] = {"ok": persist_res.get("ok"), "action": persist_res.get("action")}
                        log_event(
                            logger,
                            logging.INFO,
                            "supabase_persist_result",
                            ok=persist_res.get("ok"),
                            action=persist_res.get("action"),
                            status_code=persist_res.get("status_code"),
                        )
                except Exception as e:
                    step_ok["supabase"] = {"ok": False, "error": str(e)}
                    step_ms["supabase_ms"] = round((timed() - t0) * 1000.0, 2) if "t0" in locals() else 0.0
                    logger.exception("Supabase persist failed error=%s", e)

        # forward to broadcaster (sync function via thread)
            set_step("broadcast")
            try:
                t0 = timed()
                await run_in_thread(broadcast_assignments.send_broadcast, payload)
                step_ms["broadcast_ms"] = round((timed() - t0) * 1000.0, 2)
                step_ok["broadcast_ok"] = True
            except Exception as e:
                step_ok["broadcast_ok"] = False
                step_ms["broadcast_ms"] = round((timed() - t0) * 1000.0, 2) if "t0" in locals() else 0.0
                logger.exception('Broadcast failed error=%s', e)

        # Bot 2: DM matching tutors (optional)
            set_step("dm")
            if send_dms is not None:
                try:
                    t0 = timed()
                    dm_res = await run_in_thread(send_dms, payload)
                    step_ms["dm_ms"] = round((timed() - t0) * 1000.0, 2)
                    if dm_res and dm_res.get("skipped"):
                        step_ok["dm"] = {"skipped": True, "reason": dm_res.get("reason")}
                        log_event(logger, logging.DEBUG, "dm_skipped", reason=dm_res.get("reason"))
                    elif dm_res:
                        step_ok["dm"] = {
                            "ok": dm_res.get("ok"),
                            "matched": dm_res.get("matched"),
                            "sent": dm_res.get("sent"),
                            "failures": dm_res.get("failures"),
                        }
                        log_event(
                            logger,
                            logging.INFO,
                            "dm_result",
                            ok=dm_res.get("ok"),
                            matched=dm_res.get("matched"),
                            sent=dm_res.get("sent"),
                            failures=dm_res.get("failures"),
                        )
                except Exception as e:
                    step_ok["dm"] = {"ok": False, "error": str(e)}
                    step_ms["dm_ms"] = round((timed() - t0) * 1000.0, 2) if "t0" in locals() else 0.0
                    logger.exception("DM failed error=%s", e)

        # mark processed
            processed.add(msg_key)
        # persist periodically
            if len(processed) % 50 == 0:
                save_processed(list(processed))

            set_step("summary")
            step_ms["total_ms"] = round((timed() - overall_start) * 1000.0, 2)
            assignment_code = None
            try:
                assignment_code = (payload.get("parsed") or {}).get("assignment_code")
            except Exception:
                logger.debug("Failed to read assignment_code for summary", exc_info=True)
                assignment_code = None
            log_event(
                logger,
                logging.INFO,
                "pipeline_summary",
                ok=True,
                assignment_code=assignment_code,
                steps=step_ok,
                ms=step_ms,
            )
            _write_heartbeat(
                status="ok",
                cid=cid,
                channel_link=channel_link,
                message_id=msg_id,
                details={"assignment_code": assignment_code},
            )

    except Exception:
        logger.exception('Unhandled error in process_message')
        try:
            _write_heartbeat(
                status="error",
                cid=str(locals().get("cid") or "-"),
                channel_link=str(locals().get("channel_link") or "-"),
                message_id=locals().get("msg_id"),
                reason="unhandled_exception",
            )
        except Exception:
            pass


async def main():
    processed_raw = load_processed()
    # normalize to set for quick membership checks
    if isinstance(processed_raw, list):
        processed = set(processed_raw)
    elif isinstance(processed_raw, dict):
        # older shape support
        processed = set(processed_raw.get('processed', []))
    else:
        processed = set()

    # ensure channels is a list of strings
    channels = CHANNELS

    # choose session: prefer StringSession if provided
    if SESSION_STRING and StringSession is not None:
        client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
    else:
        client = TelegramClient(SESSION_NAME, API_ID, API_HASH)

    # connect (use connect to avoid a static typechecker warning about await)
    await client.connect()
    log_event(
        logger,
        logging.INFO,
        "telegram_connected",
        session_type='StringSession' if (SESSION_STRING and StringSession is not None) else SESSION_NAME,
    )

    # Monitoring heartbeat tick (prevents false "down" alerts during quiet periods).
    try:
        tick_s = int(os.environ.get("HEARTBEAT_TICK_SECONDS") or 60)
    except Exception:
        tick_s = 60
    asyncio.create_task(_heartbeat_tick_loop(interval_s=tick_s))

    # resolve entities with retry logic
    entities = []
    for ch in channels:
        try:
            ent = await retry_with_backoff(client.get_entity, ch)
            entities.append(ent)
            log_event(
                logger,
                logging.INFO,
                "watching_channel",
                channel_title=getattr(ent, 'title', None),
                channel_username=getattr(ent, 'username', None),
                channel_id=getattr(ent, 'id', None),
            )
        except Exception as e:
            logger.exception('Failed to resolve channel %s: %s', ch, e)

    # backfill recent messages for each channel with rate limit handling
    for ent in entities:
        try:
            # iter_messages is an async iterator, so we handle rate limits per message
            message_count = 0
            async for msg in client.iter_messages(ent, limit=HISTORIC_FETCH):
                try:
                    await process_message(client, msg, ent, processed)
                    message_count += 1

                    # Add small delay between messages to avoid rate limits during backfill
                    if message_count % 10 == 0:
                        await asyncio.sleep(0.5)  # 500ms pause every 10 messages

                except FloodWaitError as e:
                    logger.warning(f'FloodWaitError during backfill. Waiting {e.seconds}s')
                    await asyncio.sleep(e.seconds + 1)
                    # Continue processing after wait
                    await process_message(client, msg, ent, processed)
                except Exception as e:
                    logger.exception(f'Error processing message during backfill: {e}')
                    # Continue with next message
                    continue

        except FloodWaitError as e:
            logger.warning(f'FloodWaitError on iter_messages for {getattr(ent, "id", None)}. Waiting {e.seconds}s')
            await asyncio.sleep(e.seconds + 1)
        except Exception as e:
            logger.exception('Backfill failed for %s: %s', getattr(ent, 'id', None), e)

    # event handler for new messages
    @client.on(events.NewMessage(chats=entities))
    async def new_message_handler(event):
        try:
            ent = event.chat if getattr(event, 'chat', None) else await event.get_chat()
        except Exception:
            ent = None
        await process_message(client, event.message, ent or event.message.peer_id, processed)

    # run until cancelled
    log_event(logger, logging.INFO, "listening_for_messages", historic_fetch=HISTORIC_FETCH)
    try:
        _res = client.run_until_disconnected()
        # run_until_disconnected may return a coroutine (awaitable) or None depending on Telethon version.
        if asyncio.iscoroutine(_res):
            await _res
        else:
            # If it's a blocking call that returns None, run it in a thread to avoid blocking the event loop.
            try:
                await asyncio.to_thread(lambda: _res)
            except Exception:
                logger.debug("run_until_disconnected thread wrapper failed", exc_info=True)
    finally:
        # persist processed set on shutdown
        save_processed(list(processed))


if __name__ == '__main__':
    asyncio.run(main())
