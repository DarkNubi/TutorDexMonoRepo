from __future__ import annotations

import argparse
import logging
from urllib.parse import quote

from collection.channels import normalize_channel_ref, parse_channels_arg, parse_channels_from_env
from collection.config import pipeline_version
from collection.types import CollectorContext
from collection.utils import iso, parse_iso_dt, utc_now
from logging_setup import bind_log_context, log_event, timed
from supabase_raw_persist import SupabaseRawStore


async def run_enqueue_from_raw(ctx: CollectorContext, args: argparse.Namespace) -> int:
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

    channels = parse_channels_arg(getattr(args, "channels", None)) or [normalize_channel_ref(x) for x in parse_channels_from_env(ctx.cfg)]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    since = parse_iso_dt(getattr(args, "since", None)) if getattr(args, "since", None) else None
    until = parse_iso_dt(getattr(args, "until", None)) if getattr(args, "until", None) else None
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
        "pipeline_version": pipeline_version(ctx.cfg),
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
                        f"channel_link=eq.{quote(normalize_channel_ref(ch), safe='')}",
                        "message_id=not.is.null",
                        "deleted_at=is.null",
                    ]
                    if since is not None:
                        parts.append(f"message_date=gte.{quote(iso(since), safe='')}")
                    if until is not None:
                        parts.append(f"message_date=lt.{quote(iso(until), safe='')}")
                    parts.append("order=message_date.asc,message_id.asc")
                    parts.append(f"limit={int(min(page_size, max_messages - scanned))}" if max_messages else f"limit={int(page_size)}")
                    parts.append(f"offset={int(offset)}")
                    q = f"{table}?" + "&".join(parts)

                    resp = store.client.get(q, timeout=30)
                    if resp.status_code >= 400:
                        log_event(ctx.logger, logging.WARNING, "enqueue_raw_query_failed", status_code=resp.status_code, body=resp.text[:250], channel=ch)
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
                        store.enqueue_extractions(channel_link=normalize_channel_ref(ch), message_ids=ids, pipeline_version=pipeline_version(ctx.cfg), force=force)
                        enqueued += len(ids)
                        total_enqueued += len(ids)

                    offset += len(rows)
                    if len(rows) < page_size:
                        break

            store.upsert_progress(
                run_id=run_id,
                channel_link=normalize_channel_ref(ch),
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
                "finished_at": utc_now().isoformat(),
                "total_scanned": total_scanned,
                "total_enqueued": total_enqueued,
                "total_ms": round((timed() - t0) * 1000.0, 2),
            }
        )
        store.finish_run(run_id=run_id, status="ok", meta_patch=final_meta)
        log_event(ctx.logger, logging.INFO, "enqueue_done", run_id=run_id, total_scanned=total_scanned, total_enqueued=total_enqueued)
        return 0
    except Exception as e:
        err_meta = dict(base_meta)
        err_meta.update({"error": str(e), "finished_at": utc_now().isoformat()})
        store.finish_run(run_id=run_id, status="error", meta_patch=err_meta)
        raise
