"""
Mode 4 — Drain extraction queue without side effects (manual).

Click-run this file in VS Code.
It imports the real extraction worker and runs it with "no side effects" env flags.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional


# Optional: override pipeline version to process.
PIPELINE_VERSION_OVERRIDE: Optional[str] = None

# Stop once the queue is empty (recommended for manual runs).
ONESHOT: bool = True

# Optional: stop after processing N jobs (0/None means unlimited).
MAX_JOBS: Optional[int] = None

# No side effects:
ENABLE_BROADCAST: bool = False
ENABLE_DMS: bool = False


def _import_worker():
    aggregator_dir = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(aggregator_dir))
    from workers import extract_worker  # type: ignore

    return extract_worker


def main() -> int:
    if PIPELINE_VERSION_OVERRIDE:
        os.environ["EXTRACTION_PIPELINE_VERSION"] = PIPELINE_VERSION_OVERRIDE

    os.environ["EXTRACTION_WORKER_BROADCAST"] = "1" if ENABLE_BROADCAST else "0"
    os.environ["EXTRACTION_WORKER_DMS"] = "1" if ENABLE_DMS else "0"
    os.environ["EXTRACTION_WORKER_ONESHOT"] = "1" if ONESHOT else "0"
    if MAX_JOBS is not None:
        os.environ["EXTRACTION_WORKER_MAX_JOBS"] = str(int(MAX_JOBS))

    worker = _import_worker()
    worker.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

