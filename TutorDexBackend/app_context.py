"""
Application context (dependency injection container) for TutorDexBackend.

This centralizes initialization so routes can depend on a context object instead
of importing module-level singletons (which can create fragile import graphs).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache

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


@dataclass(frozen=True)
class AppContext:
    logger: logging.Logger
    cfg: object
    store: TutorStore
    sb: SupabaseStore
    auth_service: AuthService
    health_service: HealthService
    cache_service: CacheService
    telegram_service: TelegramService
    analytics_service: AnalyticsService


@lru_cache(maxsize=1)
def get_app_context() -> AppContext:
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

    return AppContext(
        logger=logger,
        cfg=cfg,
        store=store,
        sb=sb,
        auth_service=auth_service,
        health_service=health_service,
        cache_service=cache_service,
        telegram_service=telegram_service,
        analytics_service=analytics_service,
    )

