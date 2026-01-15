from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from workers.extract_worker_types import VersionInfo


@dataclass(frozen=True)
class CollectorContext:
    cfg: Any
    logger: logging.Logger
    version: VersionInfo
    here: Path

