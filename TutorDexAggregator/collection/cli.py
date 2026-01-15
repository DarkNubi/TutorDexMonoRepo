from __future__ import annotations

import argparse
import asyncio

from collection.backfill import run_backfill
from collection.bootstrap import bootstrap_collector
from collection.enqueue_from_raw import run_enqueue_from_raw
from collection.live import run_live
from collection.status import run_status
from collection.tail import run_tail


def main() -> None:
    ctx = bootstrap_collector()

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
        asyncio.run(run_backfill(ctx, args))
        return
    if args.cmd == "tail":
        asyncio.run(run_tail(ctx, args))
        return
    if args.cmd == "live":
        asyncio.run(run_live(ctx, args))
        return
    if args.cmd == "enqueue":
        asyncio.run(run_enqueue_from_raw(ctx, args))
        return
    if args.cmd == "status":
        raise SystemExit(run_status(ctx, args))
    raise SystemExit("Unknown command.")

