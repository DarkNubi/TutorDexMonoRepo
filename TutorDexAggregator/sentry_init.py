from __future__ import annotations

import os
import logging
from typing import Optional


logger = logging.getLogger("tutordex_aggregator.sentry_init")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def setup_sentry(*, service_name: str = "tutordex-aggregator") -> None:
    """
    Optional Sentry error tracking hook.

    - No hard dependency: if sentry_sdk isn't installed, this is a no-op.
    - Enable with `SENTRY_DSN` environment variable.
    - Configure environment, release, and sampling via environment variables.
    """
    dsn = os.environ.get("SENTRY_DSN", "").strip()
    
    if not dsn:
        logger.info("sentry_disabled_no_dsn")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import LoggingIntegration
    except ImportError:
        logger.info("sentry_disabled_missing_package")
        return

    environment = os.environ.get("SENTRY_ENVIRONMENT", os.environ.get("APP_ENV", "development")).strip()
    release = os.environ.get("SENTRY_RELEASE", "").strip() or None
    traces_sample_rate = float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    profiles_sample_rate = float(os.environ.get("SENTRY_PROFILES_SAMPLE_RATE", "0.1"))

    # Configure integrations
    integrations = [
        LoggingIntegration(
            level=logging.INFO,  # Capture info and above as breadcrumbs
            event_level=logging.ERROR  # Send errors as events
        ),
    ]

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            profiles_sample_rate=profiles_sample_rate,
            integrations=integrations,
            send_default_pii=False,  # Don't send PII by default
            attach_stacktrace=True,
            before_send=_before_send,
        )
        logger.info(
            "sentry_enabled",
            extra={
                "service_name": service_name,
                "environment": environment,
                "release": release or "unknown",
                "traces_sample_rate": traces_sample_rate,
            }
        )
    except Exception:
        logger.exception("sentry_setup_failed")


def _before_send(event, hint):
    """
    Filter or modify events before sending to Sentry.
    
    Use this to:
    - Remove sensitive data
    - Filter out known errors
    - Add custom context
    """
    # Example: Don't send specific errors
    # if 'exc_info' in hint:
    #     exc_type, exc_value, tb = hint['exc_info']
    #     if isinstance(exc_value, SomeKnownError):
    #         return None
    
    return event
