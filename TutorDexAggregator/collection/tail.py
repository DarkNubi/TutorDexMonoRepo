from __future__ import annotations

import argparse
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from telethon import events

from collection.backoff import retry_with_backoff
from collection.channels import channel_link_from_entity, normalize_channel_ref, parse_channels_arg, parse_channels_from_env
from collection.config import MissingTelegramCredentials, build_client, enqueue_enabled, pipeline_version
from collection.counters import Counters
from collection.enqueue import enqueue_extraction_jobs
from collection.types import CollectorContext
from collection.utils import iso, truthy, utc_now
from logging_setup import bind_log_context, log_event
from observability_http import start_observability_http_server
from observability_metrics import (
    collector_errors_total,
    collector_last_message_timestamp_seconds,
    collector_messages_seen_total,
    collector_messages_upserted_total,
)
from supabase_raw_persist import SupabaseRawStore, build_raw_row


async def run_tail(ctx: CollectorContext, args: argparse.Namespace) -> int:
    store = SupabaseRawStore()
    channels = parse_channels_arg(args.channels) or [normalize_channel_ref(x) for x in parse_channels_from_env(ctx.cfg)]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

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

    base_meta = {"supabase_enabled": store.enabled()}
    run_id = store.create_run(run_type="tail", channels=channels, meta=base_meta)
    await client.connect()
    entities: List[Any] = []
    for ch in channels:
        entity = await retry_with_backoff(client.get_entity, ch)
        entities.append(entity)
        channel_id = str(getattr(entity, "id", "") or "") or None
        channel_link = channel_link_from_entity(entity, normalize_channel_ref(ch))
        title = getattr(entity, "title", None) or None
        store.upsert_channel(
            channel_link=channel_link,
            channel_id=channel_id,
            agency_telegram_channel_name=str(title) if title else None,
        )

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
        channel_link = channel_link_from_entity(entity, "tg:unknown")
        counter = _get_counter(channel_link)

        with bind_log_context(
            step="raw.tail.new",
            channel=channel_link,
            message_id=getattr(msg, "id", None),
            component="collector",
            pipeline_version=ctx.version.pipeline_version,
            schema_version=ctx.version.schema_version,
        ):
            try:
                counter.scanned += 1
                try:
                    collector_messages_seen_total.labels(
                        channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                    ).inc()
                    dt = getattr(msg, "date", None)
                    if isinstance(dt, datetime):
                        dt_utc = dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
                        dt_utc = dt_utc.astimezone(timezone.utc)
                        collector_last_message_timestamp_seconds.labels(
                            channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                        ).set(dt_utc.timestamp())
                except Exception:
                    # Metrics must never break runtime
                    pass
                row = build_raw_row(channel_link=channel_link, channel_id=channel_id, msg=msg)
                if row:
                    _, ok_rows = store.upsert_messages_batch(rows=[row])
                    counter.written += ok_rows
                    if ok_rows:
                        try:
                            collector_messages_upserted_total.labels(
                                channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                            ).inc(ok_rows)
                        except Exception:
                            # Metrics must never break runtime
                            pass
                        enqueue_extraction_jobs(store, cfg=ctx.cfg, channel_link=channel_link, message_ids=[str(getattr(msg, "id", ""))], force=False)
                    dt = getattr(msg, "date", None)
                    if isinstance(dt, datetime):
                        counter.last_message_date_iso = iso(dt)
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
                    collector_errors_total.labels(
                        channel=channel_link, reason="raw_tail_new_failed", pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                    ).inc()
                except Exception:
                    # Metrics must never break runtime
                    pass
                log_event(ctx.logger, logging.WARNING, "raw_tail_new_failed", run_id=run_id, error=str(e))

    @client.on(events.MessageEdited(chats=entities))
    async def _on_edit(event) -> None:
        msg = event.message
        entity = await event.get_chat()
        channel_id = str(getattr(entity, "id", "") or "") or None
        channel_link = channel_link_from_entity(entity, "tg:unknown")
        counter = _get_counter(channel_link)

        with bind_log_context(
            step="raw.tail.edit",
            channel=channel_link,
            message_id=getattr(msg, "id", None),
            component="collector",
            pipeline_version=ctx.version.pipeline_version,
            schema_version=ctx.version.schema_version,
        ):
            try:
                row = build_raw_row(channel_link=channel_link, channel_id=channel_id, msg=msg)
                if row:
                    _, ok_rows = store.upsert_messages_batch(rows=[row])
                    counter.written += ok_rows
                    if ok_rows:
                        try:
                            collector_messages_upserted_total.labels(
                                channel=channel_link, pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                            ).inc(ok_rows)
                        except Exception:
                            # Metrics must never break runtime
                            pass
                        enqueue_extraction_jobs(store, cfg=ctx.cfg, channel_link=channel_link, message_ids=[str(getattr(msg, "id", ""))], force=True)
                log_event(ctx.logger, logging.DEBUG, "raw_tail_edit_ok")
            except Exception as e:
                counter.errors += 1
                try:
                    collector_errors_total.labels(
                        channel=channel_link, reason="raw_tail_edit_failed", pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                    ).inc()
                except Exception:
                    # Metrics must never break runtime
                    pass
                log_event(ctx.logger, logging.WARNING, "raw_tail_edit_failed", run_id=run_id, error=str(e))

    @client.on(events.MessageDeleted(chats=entities))
    async def _on_delete(event) -> None:
        entity = await event.get_chat()
        channel_link = channel_link_from_entity(entity, "tg:unknown")
        ids = [str(x) for x in (event.deleted_ids or [])]
        with bind_log_context(
            step="raw.tail.delete",
            channel=channel_link,
            component="collector",
            pipeline_version=ctx.version.pipeline_version,
            schema_version=ctx.version.schema_version,
        ):
            try:
                patched = store.mark_deleted(channel_link=channel_link, message_ids=ids)
                log_event(ctx.logger, logging.DEBUG, "raw_tail_delete_ok", ids=len(ids), patched=patched)
            except Exception as e:
                try:
                    collector_errors_total.labels(
                        channel=channel_link, reason="raw_tail_delete_failed", pipeline_version=ctx.version.pipeline_version, schema_version=ctx.version.schema_version
                    ).inc()
                except Exception:
                    # Metrics must never break runtime
                    pass
                log_event(ctx.logger, logging.WARNING, "raw_tail_delete_failed", run_id=run_id, error=str(e))

    log_event(
        ctx.logger,
        logging.INFO,
        "raw_tail_start",
        run_id=run_id,
        channels=channels,
        supabase_enabled=store.enabled(),
        extraction_queue_enabled=enqueue_enabled(ctx.cfg),
        pipeline_version=pipeline_version(ctx.cfg),
        queue_rpc_sql="supabase sqls/2025-12-22_extraction_queue_rpc.sql",
    )
    try:
        await client.run_until_disconnected()
        return 0
    finally:
        meta = dict(base_meta)
        meta.update({"stopped_at": utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="cancelled", meta_patch=meta)
        await client.disconnect()
