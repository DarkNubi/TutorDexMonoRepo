from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote

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
                res = await backfill_channel(
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
    except Exception as e:
        err_meta = dict(base_meta)
        err_meta.update({"error": str(e), "finished_at": utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="error", meta_patch=err_meta)
        raise
    finally:
        await client.disconnect()
