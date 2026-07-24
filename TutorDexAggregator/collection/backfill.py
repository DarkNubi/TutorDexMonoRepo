from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from telethon import TelegramClient

from collection.backoff import retry_with_backoff
from collection.channels import channel_link_from_entity, normalize_channel_ref, parse_channels_arg, parse_channels_from_env
from collection.config import MissingTelegramCredentials, build_client, enqueue_enabled, pipeline_version
from collection.counters import Counters
from collection.enqueue import enqueue_extraction_jobs
from collection.types import CollectorContext
from collection.utils import iso, parse_iso_dt, truthy, utc_now
from logging_setup import bind_log_context, log_event, timed
from observability_http import start_observability_http_server
from observability_metrics import (
    collector_last_message_timestamp_seconds,
    collector_messages_seen_total,
    collector_messages_upserted_total,
)
from supabase_raw_persist import SupabaseRawStore, build_raw_row
from shared.observability.exception_handler import swallow_exception


DEFAULT_MESSAGE_TIMEOUT_SECONDS = 180.0
DEFAULT_CHANNEL_RETRIES = 3
DEFAULT_RETRY_DELAY_SECONDS = 5.0


async def iter_messages_with_timeout(*, client: TelegramClient, entity: Any, until: Optional[datetime], timeout_seconds: float):
    """Yield Telegram messages while bounding each Telethon request.

    Telethon can leave an async iterator awaiting forever after a broken MTProto
    connection. A per-request timeout lets the caller disconnect/rebuild the
    client and retry the current channel without killing the whole replay.
    """
    iterator = client.iter_messages(entity, reverse=False, offset_date=until)
    while True:
        fetch_task = asyncio.create_task(iterator.__anext__())
        done, _pending = await asyncio.wait({fetch_task}, timeout=timeout_seconds)
        if not done:
            fetch_task.cancel()
            try:
                await client.disconnect()
            except Exception:
                pass
            try:
                await asyncio.wait_for(fetch_task, timeout=5.0)
            except BaseException:
                pass
            raise RuntimeError(f"Telegram message fetch timed out after {timeout_seconds:.1f}s")
        try:
            yield fetch_task.result()
        except StopAsyncIteration:
            return
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            raise RuntimeError("Telethon cancelled a Telegram message fetch")


async def backfill_channel(
    *,
    ctx: CollectorContext,
    client: TelegramClient,
    store: SupabaseRawStore,
    run_id: Optional[int],
    channel_ref: str,
    since: Optional[datetime],
    until: Optional[datetime],
    batch_size: int,
    max_messages: Optional[int],
    force_enqueue: bool = False,
    message_timeout_seconds: float = DEFAULT_MESSAGE_TIMEOUT_SECONDS,
) -> Counters:
    counters = Counters()

    entity = await retry_with_backoff(client.get_entity, channel_ref)
    channel_id = str(getattr(entity, "id", "") or "") or None
    channel_link = channel_link_from_entity(entity, normalize_channel_ref(channel_ref))
    title = getattr(entity, "title", None) or None

    store.upsert_channel(
        channel_link=channel_link,
        channel_id=channel_id,
        agency_telegram_channel_name=str(title) if title else None,
    )

    rows: List[Dict[str, Any]] = []
    t0 = timed()

    async for msg in iter_messages_with_timeout(
        client=client,
        entity=entity,
        until=until,
        timeout_seconds=max(1.0, float(message_timeout_seconds)),
    ):
        if msg is None:
            continue
        dt = getattr(msg, "date", None)
        if dt is None:
            continue

        try:
            dt_utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
            dt_utc = dt_utc.astimezone(timezone.utc)
        except Exception as e:
            swallow_exception(e, context="backfill_timezone_conversion", extra={"module": __name__})
            dt_utc = None

        if until is not None and dt_utc is not None and dt_utc > until:
            continue

        if since is not None and dt_utc is not None and dt_utc < since:
            break

        try:
            collector_messages_seen_total.labels(channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version).inc()
            if isinstance(dt_utc, datetime):
                collector_last_message_timestamp_seconds.labels(
                    channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                ).set(dt_utc.timestamp())
        except Exception:
            # Metrics must never break runtime
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
                    collector_messages_upserted_total.labels(
                        channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                    ).inc(ok_rows)
            except Exception:
                # Metrics must never break runtime
                pass
            if ok_rows:
                msg_ids = [str(r.get("message_id") or "").strip() for r in rows if str(r.get("message_id") or "").strip()]
                enqueue_extraction_jobs(store, cfg=ctx.cfg, channel_link=channel_link, message_ids=msg_ids, force=bool(force_enqueue))
            rows = []

        counters.last_message_id = str(getattr(msg, "id", "") or "") or counters.last_message_id
        counters.last_message_date_iso = iso(dt_utc) if isinstance(dt_utc, datetime) else counters.last_message_date_iso

        if counters.scanned % 200 == 0:
            log_event(
                ctx.logger,
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
                collector_messages_upserted_total.labels(channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version).inc(
                    ok_rows
                )
        except Exception:
            # Metrics must never break runtime
            pass
        if ok_rows:
            msg_ids = [str(r.get("message_id") or "").strip() for r in rows if str(r.get("message_id") or "").strip()]
            enqueue_extraction_jobs(store, cfg=ctx.cfg, channel_link=channel_link, message_ids=msg_ids, force=bool(force_enqueue))

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


async def backfill_channel_with_retries(
    *,
    ctx: CollectorContext,
    client: TelegramClient,
    store: SupabaseRawStore,
    run_id: int,
    channel_ref: str,
    since: Optional[datetime],
    until: Optional[datetime],
    batch_size: int,
    max_messages: Optional[int],
    force_enqueue: bool,
    message_timeout_seconds: float,
    channel_retries: int,
    retry_delay_seconds: float,
) -> tuple[TelegramClient, Counters]:
    """Run one channel with fresh-client retries after Telethon stalls/fails."""
    active_client = client
    last_error: Optional[BaseException] = None
    attempts = max(1, int(channel_retries))
    for attempt in range(1, attempts + 1):
        try:
            result = await backfill_channel(
                ctx=ctx,
                client=active_client,
                store=store,
                run_id=run_id,
                channel_ref=channel_ref,
                since=since,
                until=until,
                batch_size=batch_size,
                max_messages=max_messages,
                force_enqueue=force_enqueue,
                message_timeout_seconds=message_timeout_seconds,
            )
            return active_client, result
        except asyncio.CancelledError:
            task = asyncio.current_task()
            if task is not None and task.cancelling():
                raise
            last_error = RuntimeError("Telethon cancelled a message fetch")
        except Exception as exc:
            last_error = exc

        log_event(
            ctx.logger,
            logging.WARNING,
            "raw_backfill_channel_retry",
            run_id=run_id,
            channel=channel_ref,
            attempt=attempt,
            max_attempts=attempts,
            error=str(last_error),
        )
        try:
            await active_client.disconnect()
        except Exception:
            pass
        if attempt < attempts:
            await asyncio.sleep(max(0.0, float(retry_delay_seconds)))
            active_client = build_client(ctx.cfg)
            await active_client.connect()

    assert last_error is not None
    raise last_error


async def run_backfill(ctx: CollectorContext, args: argparse.Namespace) -> int:
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
            "/health/collector": lambda: (True, {"pipeline_version": ctx.version.pipeline_version, "schema_version": ctx.version.schema_version}),
            "/health/dependencies": _dep_health,
        },
    )

    channels = parse_channels_arg(args.channels) or [normalize_channel_ref(x) for x in parse_channels_from_env(ctx.cfg)]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    since = parse_iso_dt(args.since) if args.since else None
    until = parse_iso_dt(args.until) if args.until else None
    batch_size = int(args.batch_size or 200)
    batch_size = max(20, min(1000, batch_size))
    max_messages = int(args.max_messages) if args.max_messages else None
    message_timeout_seconds = max(1.0, float(getattr(args, "message_timeout_seconds", DEFAULT_MESSAGE_TIMEOUT_SECONDS) or DEFAULT_MESSAGE_TIMEOUT_SECONDS))
    channel_retries = max(1, int(getattr(args, "channel_retries", DEFAULT_CHANNEL_RETRIES) or DEFAULT_CHANNEL_RETRIES))
    retry_delay_seconds = DEFAULT_RETRY_DELAY_SECONDS

    base_meta = {
        "since": args.since,
        "until": args.until,
        "batch_size": batch_size,
        "max_messages": max_messages,
        "supabase_enabled": store.enabled(),
        "extraction_queue_enabled": enqueue_enabled(ctx.cfg),
        "pipeline_version": pipeline_version(ctx.cfg),
        "queue_rpc_sql": "supabase sqls/2025-12-22_extraction_queue_rpc.sql",
        "force_enqueue": bool(getattr(args, "force_enqueue", False)),
        "message_timeout_seconds": message_timeout_seconds,
        "channel_retries": channel_retries,
        "retry_delay_seconds": retry_delay_seconds,
    }
    t0 = timed()
    while True:
        try:
            client = build_client(ctx.cfg)
            break
        except MissingTelegramCredentials as e:
            if truthy(os.getenv("COLLECTOR_WAIT_FOR_TELEGRAM_CREDS")):
                log_event(ctx.logger, logging.ERROR, "collector_missing_telegram_credentials", error=str(e), sleep_seconds=60)
                await asyncio.sleep(60)
                continue
            raise SystemExit(str(e))

    run_id = store.create_run(run_type="backfill", channels=channels, meta=base_meta)
    await client.connect()
    try:
        total_scanned = 0
        total_written = 0
        for ch in channels:
            with bind_log_context(
                step="raw.backfill",
                channel=ch,
                component="collector",
                pipeline_version=ctx.version.pipeline_version,
                schema_version=ctx.version.schema_version,
            ):
                log_event(ctx.logger, logging.INFO, "raw_backfill_channel_start", channel=ch, run_id=run_id)
                client, res = await backfill_channel_with_retries(
                    ctx=ctx,
                    client=client,
                    store=store,
                    run_id=run_id,
                    channel_ref=ch,
                    since=since,
                    until=until,
                    batch_size=batch_size,
                    max_messages=max_messages,
                    force_enqueue=bool(getattr(args, "force_enqueue", False)),
                    message_timeout_seconds=message_timeout_seconds,
                    channel_retries=channel_retries,
                    retry_delay_seconds=retry_delay_seconds,
                )
                log_event(
                    ctx.logger,
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
                "finished_at": utc_now().isoformat(),
                "total_scanned": total_scanned,
                "total_written": total_written,
                "total_ms": round((timed() - t0) * 1000.0, 2),
            }
        )
        store.finish_run(run_id=run_id, status="ok", meta_patch=final_meta)
        return 0
    except asyncio.CancelledError:
        # Python 3.11+ CancelledError inherits BaseException, so it does not
        # reach the generic Exception handler. Persist a terminal run state
        # before re-raising so an interrupted Telethon run is not left falsely
        # marked as running forever.
        err_meta = dict(base_meta)
        err_meta.update(
            {
                "error": "asyncio.CancelledError",
                "cancelled": True,
                "finished_at": utc_now().isoformat(),
            }
        )
        store.finish_run(run_id=run_id, status="error", meta_patch=err_meta)
        raise
    except Exception as e:
        err_meta = dict(base_meta)
        err_meta.update({"error": str(e), "finished_at": utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="error", meta_patch=err_meta)
        raise
    finally:
        await client.disconnect()
