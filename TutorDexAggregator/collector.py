"""
collector.py

Raw Telegram collector for TutorDex.

Why this exists:
- The production pipeline is "collector -> extraction queue -> workers/extract_worker.py".
- This collector persists a lossless raw history (including forwards/compilations) to support reprocessing, dedupe improvements, and analytics.

Commands:
- backfill: iterate historical messages and upsert into `telegram_messages_raw`
- tail: subscribe to new messages/edits/deletes and upsert/update rows
"""

import argparse
import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError, SlowModeWaitError, FloodError

from logging_setup import bind_log_context, log_event, setup_logging, timed
from observability_http import start_observability_http_server
from otel import setup_otel
from sentry_init import setup_sentry
from observability_metrics import (
    collector_errors_total,
    collector_last_message_timestamp_seconds,
    collector_messages_seen_total,
    collector_messages_upserted_total,
    set_version_metrics,
)
from supabase_raw_persist import SupabaseRawStore, build_raw_row

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

setup_logging()
logger = logging.getLogger("collector")
_V = set_version_metrics(component="collector")
setup_sentry(service_name=os.environ.get("SENTRY_SERVICE_NAME") or "tutordex-collector")
setup_otel(service_name=os.environ.get("OTEL_SERVICE_NAME") or "tutordex-collector")
_DEFAULT_LOG_CTX = bind_log_context(component="collector", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version)
_DEFAULT_LOG_CTX.__enter__()

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"
if ENV_PATH.exists():
    if load_dotenv:
        load_dotenv(dotenv_path=ENV_PATH)
    else:
        try:
            raw = ENV_PATH.read_text(encoding="utf8")
            for ln in raw.splitlines():
                line = ln.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                elif ":" in line:
                    k, v = line.split(":", 1)
                else:
                    continue
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
        except Exception:
            pass

try:
    from telethon.sessions import StringSession
except Exception:
    StringSession = None


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _parse_channels_from_env() -> List[str]:
    raw = (os.environ.get("CHANNEL_LIST") or os.environ.get("CHANNELS") or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip().strip('"').strip("'") for x in items if str(x).strip()]
        except Exception:
            inner = raw[1:-1]
            return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _normalize_channel_ref(ch: str) -> str:
    s = str(ch or "").strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://"):
        s = s.rstrip("/")
        if "t.me/" in s:
            return "t.me/" + s.split("t.me/")[-1]
        return s
    if s.startswith("t.me/"):
        return s.rstrip("/")
    if s.startswith("@"):
        return "t.me/" + s[1:]
    return "t.me/" + s


def _enqueue_enabled() -> bool:
    # Default to enabled; allow explicit opt-out via env.
    v = os.environ.get("EXTRACTION_QUEUE_ENABLED")
    return _truthy(v) if v is not None else True


def _pipeline_version() -> str:
    return (os.environ.get("EXTRACTION_PIPELINE_VERSION") or "2026-01-02_det_time_v1").strip() or "2026-01-02_det_time_v1"


def _enqueue_extraction_jobs(store: SupabaseRawStore, *, channel_link: str, message_ids: List[str], force: bool = False) -> None:
    """
    Best-effort enqueue into `telegram_extractions` via RPC.

    Requires applying `supabase sqls/2025-12-22_extraction_queue_rpc.sql` first.
    """
    if not store.client or not message_ids or not _enqueue_enabled():
        return

    ids = [str(x).strip() for x in message_ids if str(x).strip()]
    if not ids:
        return
    try:
        resp = store.client.post(
            "rpc/enqueue_telegram_extractions",
            {
                "p_pipeline_version": _pipeline_version(),
                "p_channel_link": channel_link,
                "p_message_ids": ids,
                "p_force": bool(force),
            },
            timeout=20,
        )
        if resp.status_code >= 400:
            log_event(logger, logging.WARNING, "enqueue_rpc_status", status_code=resp.status_code, body=resp.text[:200], channel=channel_link, message_count=len(ids))
            return

        # RPC returns an integer count (rows inserted/updated).
        count = None
        try:
            count = resp.json()
        except Exception:
            count = None
        log_event(logger, logging.INFO, "enqueue_rpc_ok", channel=channel_link, message_count=len(ids), enqueued=count, force=bool(force), pipeline_version=_pipeline_version())
    except Exception as e:
        log_event(logger, logging.WARNING, "enqueue_rpc_failed", error=str(e), channel=channel_link, message_count=len(ids))


def _parse_channels_arg(channels_arg: Optional[str]) -> List[str]:
    if not channels_arg:
        return []
    s = channels_arg.strip()
    if s.startswith("[") and s.endswith("]"):
        try:
            items = json.loads(s)
            if isinstance(items, list):
                return [_normalize_channel_ref(x) for x in items if str(x).strip()]
        except Exception:
            pass
    return [_normalize_channel_ref(x) for x in s.split(",") if x.strip()]


def _channel_link_from_entity(entity: Any, fallback: str) -> str:
    username = getattr(entity, "username", None)
    if username:
        return f"t.me/{username}"
    # If no username, keep stable synthetic link.
    cid = getattr(entity, "id", None)
    if cid is not None:
        return f"tg:{cid}"
    return fallback


def _get_telegram_config() -> Tuple[int, str, str, str]:
    api_id = int(os.environ.get("TELEGRAM_API_ID") or os.environ.get("TG_API_ID") or os.environ.get("API_ID") or 0)
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or os.environ.get("TG_API_HASH") or os.environ.get("API_HASH") or "").strip()
    session_string = (os.environ.get("SESSION_STRING") or os.environ.get("TG_SESSION_STRING") or os.environ.get("SESSION") or "").strip()
    session_name = (os.environ.get("TG_SESSION") or "tutordex.session").strip()
    if not api_id or not api_hash:
        raise SystemExit("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in TutorDexAggregator/.env or environment.")
    return api_id, api_hash, session_string, session_name


def _build_client() -> TelegramClient:
    api_id, api_hash, session_string, session_name = _get_telegram_config()
    if session_string and StringSession is not None:
        return TelegramClient(StringSession(session_string), api_id, api_hash)
    return TelegramClient(session_name, api_id, api_hash)


# Rate limiting and retry configuration (shared with the queue worker pipeline)
MAX_RETRIES = int(os.environ.get("TELEGRAM_MAX_RETRIES", "5"))
INITIAL_RETRY_DELAY = float(os.environ.get("TELEGRAM_INITIAL_RETRY_DELAY", "1.0"))
MAX_RETRY_DELAY = float(os.environ.get("TELEGRAM_MAX_RETRY_DELAY", "300.0"))
BACKOFF_MULTIPLIER = float(os.environ.get("TELEGRAM_BACKOFF_MULTIPLIER", "2.0"))


async def _retry_with_backoff(func, *args, **kwargs):
    last_exception = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            return await func(*args, **kwargs)
        except FloodWaitError as e:
            last_exception = e
            wait_s = float(e.seconds or 1)
            if attempt >= MAX_RETRIES:
                raise
            jitter = min(5.0, wait_s * 0.1) * (0.5 + (time.time() % 1))
            await asyncio.sleep(wait_s + jitter)
        except SlowModeWaitError as e:
            last_exception = e
            wait_s = float(e.seconds or 1)
            if attempt >= MAX_RETRIES:
                raise
            await asyncio.sleep(wait_s + 0.5)
        except FloodError as e:
            last_exception = e
            if attempt >= MAX_RETRIES:
                raise
            delay = min(INITIAL_RETRY_DELAY * (BACKOFF_MULTIPLIER**attempt), MAX_RETRY_DELAY)
            await asyncio.sleep(delay)
        except Exception as e:
            last_exception = e
            if attempt >= MAX_RETRIES:
                raise
            delay = min(INITIAL_RETRY_DELAY * (BACKOFF_MULTIPLIER**attempt), MAX_RETRY_DELAY)
            await asyncio.sleep(delay)
    if last_exception:
        raise last_exception


@dataclass
class Counters:
    scanned: int = 0
    written: int = 0
    errors: int = 0
    last_message_id: Optional[str] = None
    last_message_date_iso: Optional[str] = None


async def backfill_channel(
    *,
    client: TelegramClient,
    store: SupabaseRawStore,
    run_id: Optional[int],
    channel_ref: str,
    since: Optional[datetime],
    until: Optional[datetime],
    batch_size: int,
    max_messages: Optional[int],
    force_enqueue: bool = False,
) -> Counters:
    counters = Counters()

    entity = await _retry_with_backoff(client.get_entity, channel_ref)
    channel_id = str(getattr(entity, "id", "") or "") or None
    channel_link = _channel_link_from_entity(entity, _normalize_channel_ref(channel_ref))
    title = getattr(entity, "title", None) or None

    store.upsert_channel(channel_link=channel_link, channel_id=channel_id, title=str(title) if title else None)

    rows: List[Dict[str, Any]] = []
    t0 = timed()

    # Iterate newest -> oldest so we can stop early once we reach `since`.
    # Telethon's `offset_date` semantics vary with `reverse`, so keep the logic explicit here.
    async for msg in client.iter_messages(entity, reverse=False, offset_date=until):
        if msg is None:
            continue
        dt = getattr(msg, "date", None)
        if dt is None:
            continue

        try:
            dt_utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            dt_utc = dt_utc.astimezone(timezone.utc)
        except Exception:
            dt_utc = None

        if until is not None and dt_utc is not None and dt_utc > until:
            # When iterating newest->oldest, we may see a few messages after `until`; skip them.
            continue

        if since is not None and dt_utc is not None and dt_utc < since:
            # Once we crossed the start boundary, everything else will be older.
            break

        try:
            collector_messages_seen_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
            if isinstance(dt_utc, datetime):
                collector_last_message_timestamp_seconds.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).set(dt_utc.timestamp())
        except Exception:
            pass

        counters.scanned += 1
        row = build_raw_row(channel_link=channel_link, channel_id=channel_id, msg=msg)
        if row:
            rows.append(row)

        if max_messages is not None and counters.scanned >= int(max_messages):
            break

        if len(rows) >= int(batch_size):
            attempted, ok_rows = store.upsert_messages_batch(rows=rows)
            counters.written += ok_rows
            try:
                if ok_rows:
                    collector_messages_upserted_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc(ok_rows)
            except Exception:
                pass
            if ok_rows:
                msg_ids = [str(r.get("message_id") or "").strip() for r in rows if str(r.get("message_id") or "").strip()]
                _enqueue_extraction_jobs(store, channel_link=channel_link, message_ids=msg_ids, force=bool(force_enqueue))
            rows = []

        counters.last_message_id = str(getattr(msg, "id", "") or "") or counters.last_message_id
        counters.last_message_date_iso = _iso(dt_utc) if isinstance(dt_utc, datetime) else counters.last_message_date_iso

        if counters.scanned % 200 == 0:
            log_event(
                logger,
                logging.INFO,
                "raw_backfill_progress",
                run_id=run_id,
                channel=channel_link,
                scanned=counters.scanned,
                written=counters.written,
                errors=counters.errors,
                last_message_id=counters.last_message_id,
                last_message_date=counters.last_message_date_iso,
                elapsed_s=round(timed() - t0, 2),
            )

    if rows:
        attempted, ok_rows = store.upsert_messages_batch(rows=rows)
        counters.written += ok_rows
        try:
            if ok_rows:
                collector_messages_upserted_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc(ok_rows)
        except Exception:
            pass
        if ok_rows:
            msg_ids = [str(r.get("message_id") or "").strip() for r in rows if str(r.get("message_id") or "").strip()]
            _enqueue_extraction_jobs(store, channel_link=channel_link, message_ids=msg_ids, force=bool(force_enqueue))

    store.upsert_progress(
        run_id=run_id,
        channel_link=channel_link,
        last_message_id=counters.last_message_id,
        last_message_date_iso=counters.last_message_date_iso,
        scanned=counters.scanned,
        inserted=0,
        updated=0,
        errors=counters.errors,
    )
    return counters


async def run_backfill(args: argparse.Namespace) -> int:
    store = SupabaseRawStore()

    def _dep_health() -> tuple[bool, dict[str, Any]]:
        if not store.enabled() or not store.client:
            return False, {"reason": "supabase_disabled"}
        try:
            resp = store.client.get(f"{store.cfg.messages_table}?select=id&limit=1", timeout=5)
            return (resp.status_code < 400), {"status_code": resp.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    start_observability_http_server(
        port=9001,
        component="collector",
        health_handlers={
            "/health/collector": lambda: (True, {"pipeline_version": _V.pipeline_version, "schema_version": _V.schema_version}),
            "/health/dependencies": _dep_health,
        },
    )

    channels = _parse_channels_arg(args.channels) or [_normalize_channel_ref(x) for x in _parse_channels_from_env()]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    since = _parse_iso_dt(args.since) if args.since else None
    until = _parse_iso_dt(args.until) if args.until else None
    batch_size = int(args.batch_size or 200)
    batch_size = max(20, min(1000, batch_size))
    max_messages = int(args.max_messages) if args.max_messages else None

    base_meta = {
        "since": args.since,
        "until": args.until,
        "batch_size": batch_size,
        "max_messages": max_messages,
        "supabase_enabled": store.enabled(),
        "extraction_queue_enabled": _enqueue_enabled(),
        "pipeline_version": _pipeline_version(),
        "queue_rpc_sql": "supabase sqls/2025-12-22_extraction_queue_rpc.sql",
        "force_enqueue": bool(getattr(args, "force_enqueue", False)),
    }
    run_id = store.create_run(run_type="backfill", channels=channels, meta=base_meta)

    t0 = timed()
    client = _build_client()
    await client.connect()
    try:
        total_scanned = 0
        total_written = 0
        for ch in channels:
            with bind_log_context(step="raw.backfill", channel=ch, component="collector", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version):
                log_event(logger, logging.INFO, "raw_backfill_channel_start", channel=ch, run_id=run_id)
                res = await backfill_channel(
                    client=client,
                    store=store,
                    run_id=run_id,
                    channel_ref=ch,
                    since=since,
                    until=until,
                    batch_size=batch_size,
                    max_messages=max_messages,
                    force_enqueue=bool(getattr(args, "force_enqueue", False)),
                )
                log_event(
                    logger,
                    logging.INFO,
                    "raw_backfill_channel_done",
                    channel=ch,
                    run_id=run_id,
                    scanned=res.scanned,
                    written=res.written,
                    errors=res.errors,
                )
                total_scanned += res.scanned
                total_written += res.written

        final_meta = dict(base_meta)
        final_meta.update(
            {
                "finished_at": _utc_now().isoformat(),
                "total_scanned": total_scanned,
                "total_written": total_written,
                "total_ms": round((timed() - t0) * 1000.0, 2),
            }
        )
        store.finish_run(run_id=run_id, status="ok", meta_patch=final_meta)
        return 0
    except Exception as e:
        err_meta = dict(base_meta)
        err_meta.update({"error": str(e), "finished_at": _utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="error", meta_patch=err_meta)
        raise
    finally:
        await client.disconnect()


async def run_tail(args: argparse.Namespace) -> int:
    store = SupabaseRawStore()
    channels = _parse_channels_arg(args.channels) or [_normalize_channel_ref(x) for x in _parse_channels_from_env()]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    base_meta = {"supabase_enabled": store.enabled()}
    run_id = store.create_run(run_type="tail", channels=channels, meta=base_meta)

    def _dep_health() -> tuple[bool, dict[str, Any]]:
        if not store.enabled() or not store.client:
            return False, {"reason": "supabase_disabled"}
        try:
            resp = store.client.get(f"{store.cfg.messages_table}?select=id&limit=1", timeout=5)
            return (resp.status_code < 400), {"status_code": resp.status_code}
        except Exception as e:
            return False, {"error": str(e)}

    start_observability_http_server(
        port=9001,
        component="collector",
        health_handlers={
            "/health/collector": lambda: (True, {"pipeline_version": _V.pipeline_version, "schema_version": _V.schema_version}),
            "/health/dependencies": _dep_health,
        },
    )

    client = _build_client()
    await client.connect()
    entities: List[Any] = []
    for ch in channels:
        entity = await _retry_with_backoff(client.get_entity, ch)
        entities.append(entity)
        channel_id = str(getattr(entity, "id", "") or "") or None
        channel_link = _channel_link_from_entity(entity, _normalize_channel_ref(ch))
        title = getattr(entity, "title", None) or None
        store.upsert_channel(channel_link=channel_link, channel_id=channel_id, title=str(title) if title else None)

    counts: Dict[str, Counters] = {}

    def _get_counter(channel_link: str) -> Counters:
        c = counts.get(channel_link)
        if c is None:
            c = Counters()
            counts[channel_link] = c
        return c

    @client.on(events.NewMessage(chats=entities))
    async def _on_new_message(event) -> None:
        msg = event.message
        entity = await event.get_chat()
        channel_id = str(getattr(entity, "id", "") or "") or None
        channel_link = _channel_link_from_entity(entity, "tg:unknown")
        counter = _get_counter(channel_link)

        with bind_log_context(step="raw.tail.new", channel=channel_link, message_id=getattr(msg, "id", None), component="collector", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version):
            try:
                counter.scanned += 1
                try:
                    collector_messages_seen_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                    dt = getattr(msg, "date", None)
                    if isinstance(dt, datetime):
                        dt_utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
                        dt_utc = dt_utc.astimezone(timezone.utc)
                        collector_last_message_timestamp_seconds.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).set(dt_utc.timestamp())
                except Exception:
                    pass
                row = build_raw_row(channel_link=channel_link, channel_id=channel_id, msg=msg)
                if row:
                    _, ok_rows = store.upsert_messages_batch(rows=[row])
                    counter.written += ok_rows
                    if ok_rows:
                        try:
                            collector_messages_upserted_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc(ok_rows)
                        except Exception:
                            pass
                        _enqueue_extraction_jobs(store, channel_link=channel_link, message_ids=[str(getattr(msg, "id", ""))], force=False)
                    dt = getattr(msg, "date", None)
                    if isinstance(dt, datetime):
                        counter.last_message_date_iso = _iso(dt)
                    counter.last_message_id = str(getattr(msg, "id", "") or "") or counter.last_message_id

                store.upsert_progress(
                    run_id=run_id,
                    channel_link=channel_link,
                    last_message_id=counter.last_message_id,
                    last_message_date_iso=counter.last_message_date_iso,
                    scanned=counter.scanned,
                    inserted=0,
                    updated=0,
                    errors=counter.errors,
                )
            except Exception as e:
                counter.errors += 1
                try:
                    collector_errors_total.labels(channel=channel_link, reason="raw_tail_new_failed", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                except Exception:
                    pass
                log_event(logger, logging.WARNING, "raw_tail_new_failed", run_id=run_id, error=str(e))

    @client.on(events.MessageEdited(chats=entities))
    async def _on_edit(event) -> None:
        msg = event.message
        entity = await event.get_chat()
        channel_id = str(getattr(entity, "id", "") or "") or None
        channel_link = _channel_link_from_entity(entity, "tg:unknown")
        counter = _get_counter(channel_link)

        with bind_log_context(step="raw.tail.edit", channel=channel_link, message_id=getattr(msg, "id", None), component="collector", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version):
            try:
                row = build_raw_row(channel_link=channel_link, channel_id=channel_id, msg=msg)
                if row:
                    _, ok_rows = store.upsert_messages_batch(rows=[row])
                    counter.written += ok_rows
                    if ok_rows:
                        try:
                            collector_messages_upserted_total.labels(channel=channel_link, pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc(ok_rows)
                        except Exception:
                            pass
                        # Edits can change extraction output; request reprocess for this message.
                        _enqueue_extraction_jobs(store, channel_link=channel_link, message_ids=[str(getattr(msg, "id", ""))], force=True)
                log_event(logger, logging.DEBUG, "raw_tail_edit_ok")
            except Exception as e:
                counter.errors += 1
                try:
                    collector_errors_total.labels(channel=channel_link, reason="raw_tail_edit_failed", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                except Exception:
                    pass
                log_event(logger, logging.WARNING, "raw_tail_edit_failed", run_id=run_id, error=str(e))

    @client.on(events.MessageDeleted(chats=entities))
    async def _on_delete(event) -> None:
        entity = await event.get_chat()
        channel_link = _channel_link_from_entity(entity, "tg:unknown")
        ids = [str(x) for x in (event.deleted_ids or [])]
        with bind_log_context(step="raw.tail.delete", channel=channel_link, component="collector", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version):
            try:
                patched = store.mark_deleted(channel_link=channel_link, message_ids=ids)
                log_event(logger, logging.DEBUG, "raw_tail_delete_ok", ids=len(ids), patched=patched)
            except Exception as e:
                try:
                    collector_errors_total.labels(channel=channel_link, reason="raw_tail_delete_failed", pipeline_version=_V.pipeline_version, schema_version=_V.schema_version).inc()
                except Exception:
                    pass
                log_event(logger, logging.WARNING, "raw_tail_delete_failed", run_id=run_id, error=str(e))

    log_event(
        logger,
        logging.INFO,
        "raw_tail_start",
        run_id=run_id,
        channels=channels,
        supabase_enabled=store.enabled(),
        extraction_queue_enabled=_enqueue_enabled(),
        pipeline_version=_pipeline_version(),
        queue_rpc_sql="supabase sqls/2025-12-22_extraction_queue_rpc.sql",
    )
    try:
        await client.run_until_disconnected()
        return 0
    finally:
        meta = dict(base_meta)
        meta.update({"stopped_at": _utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="cancelled", meta_patch=meta)
        await client.disconnect()


async def run_live(args: argparse.Namespace) -> int:
    """
    Run tail + automated catchup recovery (recommended for production).

    - Tail handles new messages/edits/deletes in real-time.
    - Catchup heals gaps after outages by backfilling historical windows from Telegram,
      throttled by extraction queue backlog ("run when the queue is drained/low").
    """
    channels = _parse_channels_arg(args.channels) or [_normalize_channel_ref(x) for x in _parse_channels_from_env()]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    # Start tail immediately, then let catchup run alongside it.
    tail_task = asyncio.create_task(run_tail(args))

    try:
        from recovery.catchup import load_catchup_config, run_catchup_until_target  # type: ignore

        store = SupabaseRawStore()
        cfg = load_catchup_config(agg_dir=HERE)
        catchup_task = asyncio.create_task(
            run_catchup_until_target(
                agg_dir=HERE,
                channels=channels,
                store=store,
                config=cfg,
            )
        )
        await catchup_task
    except Exception as e:
        log_event(logger, logging.WARNING, "live_mode_catchup_init_failed", error=str(e))

    return int(await tail_task)


async def run_enqueue_from_raw(args: argparse.Namespace) -> int:
    """
    Enqueue extraction jobs from existing `telegram_messages_raw` rows.

    This is used for:
    - Reprocessing (new prompt/schema/model): set EXTRACTION_PIPELINE_VERSION and pass --force.
    - Recovery: enqueue a downtime window without re-reading Telegram.
    """
    store = SupabaseRawStore()
    if not store.enabled() or not store.client:
        raise SystemExit(
            "Supabase raw store is disabled/misconfigured. Set SUPABASE_SERVICE_ROLE_KEY and SUPABASE_RAW_ENABLED=1, and one of SUPABASE_URL_HOST / SUPABASE_URL_DOCKER / SUPABASE_URL."
        )

    channels = _parse_channels_arg(getattr(args, "channels", None)) or [_normalize_channel_ref(x) for x in _parse_channels_from_env()]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    since = _parse_iso_dt(getattr(args, "since", None)) if getattr(args, "since", None) else None
    until = _parse_iso_dt(getattr(args, "until", None)) if getattr(args, "until", None) else None
    page_size = int(getattr(args, "page_size", 500) or 500)
    page_size = max(50, min(5000, page_size))
    max_messages = int(getattr(args, "max_messages", 0) or 0)
    force = bool(getattr(args, "force", False))

    base_meta = {
        "since": getattr(args, "since", None),
        "until": getattr(args, "until", None),
        "page_size": page_size,
        "max_messages": max_messages or None,
        "supabase_enabled": store.enabled(),
        "pipeline_version": _pipeline_version(),
        "force": force,
        "queue_rpc_sql": "supabase sqls/2025-12-22_extraction_queue_rpc.sql",
        "note": "enqueue_from_raw",
    }
    run_id = store.create_run(run_type="enqueue", channels=channels, meta=base_meta)

    t0 = timed()
    total_scanned = 0
    total_enqueued = 0
    table = store.cfg.messages_table

    try:
        for ch in channels:
            offset = 0
            scanned = 0
            enqueued = 0
            with bind_log_context(step="raw.enqueue", channel=ch):
                while True:
                    if max_messages and scanned >= max_messages:
                        break

                    select = "message_id,message_date,deleted_at"
                    parts = [
                        f"select={select}",
                        f"channel_link=eq.{quote(_normalize_channel_ref(ch), safe='')}",
                        "message_id=not.is.null",
                        "deleted_at=is.null",
                    ]
                    if since is not None:
                        parts.append(f"message_date=gte.{quote(_iso(since), safe='')}")
                    if until is not None:
                        parts.append(f"message_date=lt.{quote(_iso(until), safe='')}")
                    parts.append("order=message_date.asc,message_id.asc")
                    parts.append(f"limit={int(min(page_size, max_messages - scanned))}" if max_messages else f"limit={int(page_size)}")
                    parts.append(f"offset={int(offset)}")
                    q = f"{table}?" + "&".join(parts)

                    resp = store.client.get(q, timeout=30)
                    if resp.status_code >= 400:
                        log_event(logger, logging.WARNING, "enqueue_raw_query_failed", status_code=resp.status_code, body=resp.text[:250], channel=ch)
                        break
                    try:
                        rows = resp.json()
                    except Exception:
                        rows = []
                    if not isinstance(rows, list) or not rows:
                        break

                    ids = [str(r.get("message_id") or "").strip() for r in rows if str(r.get("message_id") or "").strip()]
                    scanned += len(ids)
                    total_scanned += len(ids)
                    if ids:
                        _enqueue_extraction_jobs(store, channel_link=_normalize_channel_ref(ch), message_ids=ids, force=force)
                        enqueued += len(ids)
                        total_enqueued += len(ids)

                    offset += len(rows)
                    if len(rows) < page_size:
                        break

            store.upsert_progress(
                run_id=run_id,
                channel_link=_normalize_channel_ref(ch),
                last_message_id=None,
                last_message_date_iso=None,
                scanned=scanned,
                inserted=0,
                updated=0,
                errors=0,
            )

        final_meta = dict(base_meta)
        final_meta.update(
            {
                "finished_at": _utc_now().isoformat(),
                "total_scanned": total_scanned,
                "total_enqueued": total_enqueued,
                "total_ms": round((timed() - t0) * 1000.0, 2),
            }
        )
        store.finish_run(run_id=run_id, status="ok", meta_patch=final_meta)
        log_event(logger, logging.INFO, "enqueue_done", run_id=run_id, total_scanned=total_scanned, total_enqueued=total_enqueued)
        return 0
    except Exception as e:
        err_meta = dict(base_meta)
        err_meta.update({"error": str(e), "finished_at": _utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="error", meta_patch=err_meta)
        raise

def run_status(args: argparse.Namespace) -> int:
    store = SupabaseRawStore()
    if not store.enabled():
        print(
            "Supabase raw store is disabled (SUPABASE_URL_HOST/SUPABASE_URL_DOCKER/SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY missing or SUPABASE_RAW_ENABLED=false)."
        )
        return 2

    run_id: Optional[int] = int(args.run_id) if args.run_id else None
    if run_id is None:
        run_id = store.get_latest_run_id(run_type=args.run_type or None)
    if run_id is None:
        print("No ingestion runs found.")
        return 1

    run = store.get_run(run_id=run_id)
    progress = store.list_progress(run_id=run_id)

    total_scanned = sum(int(p.get("scanned_count") or 0) for p in progress)
    total_errors = sum(int(p.get("error_count") or 0) for p in progress)

    print(f"run_id={run_id}")
    if run:
        print(f"run_type={run.get('run_type')} status={run.get('status')} started_at={run.get('started_at')} finished_at={run.get('finished_at')}")
        ch = run.get("channels")
        if isinstance(ch, list):
            print(f"channels={len(ch)}")

    print(f"progress_rows={len(progress)} total_scanned={total_scanned} total_errors={total_errors}")
    for p in progress:
        print(
            " - "
            + " ".join(
                [
                    f"channel={p.get('channel_link')}",
                    f"scanned={p.get('scanned_count')}",
                    f"errors={p.get('error_count')}",
                    f"last_id={p.get('last_message_id')}",
                    f"last_date={p.get('last_message_date')}",
                    f"updated_at={p.get('updated_at')}",
                ]
            )
        )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description="TutorDex raw Telegram collector (backfill + tail).")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_backfill = sub.add_parser("backfill", help="Backfill historical messages into telegram_messages_raw.")
    p_backfill.add_argument("--channels", help="Comma-separated channels or JSON array; defaults to CHANNEL_LIST env var.")
    p_backfill.add_argument("--since", help="ISO datetime (inclusive). Example: 2025-01-01T00:00:00+00:00")
    p_backfill.add_argument("--until", help="ISO datetime (exclusive-ish). Example: 2025-02-01T00:00:00+00:00")
    p_backfill.add_argument("--batch-size", type=int, default=200, help="Supabase batch size (default 200).")
    p_backfill.add_argument("--max-messages", type=int, help="Optional cap per channel (useful for dry smoke runs).")
    p_backfill.add_argument(
        "--force-enqueue",
        action="store_true",
        help="Force enqueue (reparse) even if extraction rows already exist for this pipeline version.",
    )

    p_tail = sub.add_parser("tail", help="Tail new messages/edits/deletes and upsert into telegram_messages_raw.")
    p_tail.add_argument("--channels", help="Comma-separated channels or JSON array; defaults to CHANNEL_LIST env var.")

    p_live = sub.add_parser("live", help="Tail + automated catchup recovery (recommended).")
    p_live.add_argument("--channels", help="Comma-separated channels or JSON array; defaults to CHANNEL_LIST env var.")

    p_enqueue = sub.add_parser("enqueue", help="Enqueue extraction jobs from existing telegram_messages_raw (no Telegram calls).")
    p_enqueue.add_argument("--channels", help="Comma-separated channels or JSON array; defaults to CHANNEL_LIST env var.")
    p_enqueue.add_argument("--since", help="ISO datetime (inclusive). Example: 2025-01-01T00:00:00+00:00")
    p_enqueue.add_argument("--until", help="ISO datetime (exclusive-ish). Example: 2025-02-01T00:00:00+00:00")
    p_enqueue.add_argument("--page-size", type=int, default=500, help="Supabase page size (default 500).")
    p_enqueue.add_argument("--max-messages", type=int, help="Optional cap total messages enqueued per channel.")
    p_enqueue.add_argument("--force", action="store_true", help="Force enqueue even if extraction rows already exist.")

    p_status = sub.add_parser("status", help="Show latest (or specific) ingestion run progress from Supabase.")
    p_status.add_argument("--run-id", help="Run id to inspect (defaults to latest).")
    p_status.add_argument("--run-type", choices=["backfill", "tail"], help="Filter latest run by type.")

    args = p.parse_args()

    if args.cmd == "backfill":
        asyncio.run(run_backfill(args))
        return
    if args.cmd == "tail":
        asyncio.run(run_tail(args))
        return
    if args.cmd == "live":
        asyncio.run(run_live(args))
        return
    if args.cmd == "enqueue":
        asyncio.run(run_enqueue_from_raw(args))
        return
    if args.cmd == "status":
        raise SystemExit(run_status(args))
    raise SystemExit("Unknown command.")


if __name__ == "__main__":
    main()
