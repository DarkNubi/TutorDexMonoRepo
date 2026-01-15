from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Counters:
    scanned: int = 0
    written: int = 0
    errors: int = 0
    last_message_id: Optional[str] = None
    last_message_date_iso: Optional[str] = None

