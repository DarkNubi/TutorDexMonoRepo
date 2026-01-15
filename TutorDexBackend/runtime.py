"""
Runtime singletons for TutorDexBackend.

This module centralizes initialization so route modules can import shared state
without circular imports against `app.py`.
"""

from __future__ import annotations

import logging

from TutorDexBackend.logging_setup import setup_logging
from TutorDexBackend.otel import setup_otel
from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.sentry_init import setup_sentry
from TutorDexBackend.services.analytics_service import AnalyticsService
from TutorDexBackend.services.auth_service import AuthService
from TutorDexBackend.services.cache_service import CacheService
from TutorDexBackend.services.health_service import HealthService
from TutorDexBackend.services.telegram_service import TelegramService
from TutorDexBackend.supabase_store import SupabaseStore
from shared.config import load_backend_config

setup_logging()
logger = logging.getLogger("tutordex_backend")
setup_sentry(service_name="tutordex-backend")
setup_otel()

cfg = load_backend_config()
store = TutorStore()
sb = SupabaseStore()

auth_service = AuthService()
health_service = HealthService(store, sb)
cache_service = CacheService(store)
telegram_service = TelegramService(store)
analytics_service = AnalyticsService(sb, store)

