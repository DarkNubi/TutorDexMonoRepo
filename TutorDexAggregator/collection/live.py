from __future__ import annotations

import argparse
import asyncio
import logging

from collection.channels import normalize_channel_ref, parse_channels_arg, parse_channels_from_env
from collection.types import CollectorContext
from logging_setup import log_event
from supabase_raw_persist import SupabaseRawStore

from collection.tail import run_tail


async def run_live(ctx: CollectorContext, args: argparse.Namespace) -> int:
    """
    Run tail + automated catchup recovery (recommended for production).

    - Tail handles new messages/edits/deletes in real-time.
    - Catchup heals gaps after outages by backfilling historical windows from Telegram,
      throttled by extraction queue backlog ("run when the queue is drained/low").
    """
    channels = parse_channels_arg(args.channels) or [normalize_channel_ref(x) for x in parse_channels_from_env(ctx.cfg)]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided. Set CHANNEL_LIST in .env or pass --channels.")

    tail_task = asyncio.create_task(run_tail(ctx, args))

    try:
        from recovery.catchup import load_catchup_config, run_catchup_until_target  # type: ignore

        store = SupabaseRawStore()
        catchup_cfg = load_catchup_config(agg_dir=ctx.here)
        catchup_task = asyncio.create_task(
            run_catchup_until_target(
                agg_dir=ctx.here,
                channels=channels,
                store=store,
                config=catchup_cfg,
            )
        )
        await catchup_task
    except Exception as e:
        log_event(ctx.logger, logging.WARNING, "live_mode_catchup_init_failed", error=str(e))

    return int(await tail_task)

