from __future__ import annotations

import argparse

from collection.types import CollectorContext
from supabase_raw_persist import SupabaseRawStore


def run_status(ctx: CollectorContext, args: argparse.Namespace) -> int:
    store = SupabaseRawStore()
    if not store.enabled():
        print(
            "Supabase raw store is disabled (SUPABASE_URL_HOST/SUPABASE_URL_DOCKER/SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY missing or SUPABASE_RAW_ENABLED=false)."
        )
        return 2

    run_id = int(args.run_id) if args.run_id else None
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
