"""
Compatibility shim for broadcast helpers.

The broadcast implementation lives under `TutorDexAggregator/delivery/`.
"""

from __future__ import annotations

from delivery.formatting import build_inline_keyboard, build_message_text  # noqa: F401
from delivery.send import broadcast_single_assignment, send_broadcast  # noqa: F401

__all__ = [
    "send_broadcast",
    "broadcast_single_assignment",
    "build_message_text",
    "build_inline_keyboard",
]

