"""
Runtime singletons for TutorDexBackend.

This module centralizes initialization so route modules can import shared state
without circular imports against `app.py`.
"""

from __future__ import annotations

import warnings

from TutorDexBackend.app_context import get_app_context

warnings.warn(
    "TutorDexBackend.runtime is deprecated. Use TutorDexBackend.app_context instead.",
    DeprecationWarning,
    stacklevel=2,
)

_ctx = get_app_context()

logger = _ctx.logger
cfg = _ctx.cfg
store = _ctx.store
sb = _ctx.sb
auth_service = _ctx.auth_service
health_service = _ctx.health_service
cache_service = _ctx.cache_service
telegram_service = _ctx.telegram_service
analytics_service = _ctx.analytics_service
