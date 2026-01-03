"""
Mode 3 — Reparse / re-enqueue from raw (manual).

Click-run this file in VS Code.
It imports the real collector implementation and runs `collector.run_enqueue_from_raw(...)`.
"""

from __future__ import annotations

import asyncio
import os
import sys
from argparse import Namespace
from pathlib import Path
from typing import Optional


CHANNELS: Optional[str] = None
SINCE_ISO: Optional[str] = "2025-12-01T00:00:00+00:00"
UNTIL_ISO: Optional[str] = "2026-01-02T00:00:00+00:00"
MAX_MESSAGES_PER_CHANNEL: Optional[int] = None
PAGE_SIZE: int = 500

# Recommended: set a new pipeline version when you change prompt/schema/model.
PIPELINE_VERSION_OVERRIDE: Optional[str] = "2026-01-02_det_time_v1"

# If you keep the same pipeline version, set FORCE=True to reprocess already-ok jobs.
FORCE: bool = True


def _import_collector():
    aggregator_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(aggregator_dir))
    import collector  # type: ignore

    return collector


def main() -> int:
    if PIPELINE_VERSION_OVERRIDE:
        os.environ["EXTRACTION_PIPELINE_VERSION"] = PIPELINE_VERSION_OVERRIDE

    collector = _import_collector()
    args = Namespace(
        channels=CHANNELS,
        since=SINCE_ISO,
        until=UNTIL_ISO,
        page_size=PAGE_SIZE,
        max_messages=MAX_MESSAGES_PER_CHANNEL,
        force=FORCE,
    )
    return int(asyncio.run(collector.run_enqueue_from_raw(args)))


if __name__ == "__main__":
    raise SystemExit(main())
