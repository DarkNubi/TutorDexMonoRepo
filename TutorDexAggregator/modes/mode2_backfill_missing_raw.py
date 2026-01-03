"""
Mode 2 — Backfill missing raw data (manual).

Click-run this file in VS Code.
It imports the real collector implementation and runs `collector.run_backfill(...)`.
"""

from __future__ import annotations

import asyncio
import sys
from argparse import Namespace
from pathlib import Path
from typing import Optional


CHANNELS: Optional[str] = None
SINCE_ISO: Optional[str] = None
UNTIL_ISO: Optional[str] = None
MAX_MESSAGES_PER_CHANNEL: Optional[int] = None
BATCH_SIZE: int = 200

# For recovery, default is NOT to force-reparse already-ok extractions.
FORCE_ENQUEUE: bool = False


def _import_collector():
    aggregator_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(aggregator_dir))
    import collector  # type: ignore

    return collector


def main() -> int:
    collector = _import_collector()
    args = Namespace(
        channels=CHANNELS,
        since=SINCE_ISO,
        until=UNTIL_ISO,
        batch_size=BATCH_SIZE,
        max_messages=MAX_MESSAGES_PER_CHANNEL,
        force_enqueue=FORCE_ENQUEUE,
    )
    return int(asyncio.run(collector.run_backfill(args)))


if __name__ == "__main__":
    raise SystemExit(main())

