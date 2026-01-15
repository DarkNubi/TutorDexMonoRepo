"""
Compatibility shim for older imports.

The collector implementation lives under `TutorDexAggregator/collection/`.
"""

from __future__ import annotations

from collection.backfill import run_backfill  # noqa: F401
from collection.enqueue_from_raw import run_enqueue_from_raw  # noqa: F401
from collection.live import run_live  # noqa: F401
from collection.status import run_status  # noqa: F401
from collection.tail import run_tail  # noqa: F401

from collection.cli import main  # noqa: F401


__all__ = [
    "main",
    "run_backfill",
    "run_tail",
    "run_live",
    "run_enqueue_from_raw",
    "run_status",
]

