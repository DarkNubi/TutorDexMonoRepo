"""
Shared exception handler for TutorDex.

Provides observable, intention-revealing patterns for exception handling.
Use this instead of silent `except: pass` to ensure all exceptions are logged and counted.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("tutordex.exceptions")

_LOGRECORD_RESERVED_KEYS = set(
    logging.LogRecord(
        name="",
        level=0,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__.keys()
)
# Common computed/reserved attributes that aren't always present in __dict__ at construction time.
_LOGRECORD_RESERVED_KEYS.update({"message", "asctime"})


def swallow_exception(
    exc: Exception,
    *,
    context: str,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Log and count a swallowed exception with context.

    Use this function when an exception needs to be suppressed but should still
    be observable through logs and metrics. This is appropriate for:
    - Best-effort operations (parsing, enrichment, optional metadata)
    - Cleanup/teardown operations
    - Metrics collection that must not break the runtime

    DO NOT use this for core logic paths - those should fail fast.

    Args:
        exc: The exception that was caught
        context: Short, stable, meaningful context string (used in metrics labels)
        extra: Additional context to include in logs

    Example:
        try:
            optional_enrichment()
        except Exception as e:
            swallow_exception(
                e,
                context="enrichment_geocoding",
                extra={"postal_code": postal_code, "module": __name__},
            )
    """
    # Extract exception type name once - needed for both logging and metrics
    # This is intentional: we always log/count exceptions here, so the computation
    # is not wasted
    exc_type_name = type(exc).__name__

    log_extra: Dict[str, Any] = {"context": context, "exception_type": exc_type_name}
    for key, value in (extra or {}).items():
        # Python logging forbids overwriting LogRecord attributes (e.g. "module"),
        # so we sanitize to prevent runtime failures in "best-effort" paths.
        if key in _LOGRECORD_RESERVED_KEYS or key in log_extra:
            log_extra[f"extra_{key}"] = value
        else:
            log_extra[key] = value

    logger.exception(
        "Swallowed exception",
        extra=log_extra,
    )

    # Increment metrics counter (best-effort - must never break runtime)
    try:
        # Import here to avoid circular dependencies.
        # We try Aggregator first, then Backend, since most usage is in Aggregator.
        # This pattern is intentionally hardcoded (not registry-based) to:
        # 1. Minimize dependencies - shared/ module has minimal imports
        # 2. Work across module boundaries without additional configuration
        # 3. Gracefully degrade when metrics aren't available (scripts, tests)
        try:
            # Try Aggregator metrics first
            from TutorDexAggregator.observability_metrics import swallowed_exceptions_total
            swallowed_exceptions_total.labels(context=context, exception_type=exc_type_name).inc()
        except ImportError:
            # Fall back to Backend metrics if available
            try:
                from TutorDexBackend.metrics import swallowed_exceptions_total
                swallowed_exceptions_total.labels(context=context, exception_type=exc_type_name).inc()
            except (ImportError, AttributeError):
                # No metrics available - continue without metrics
                pass
    except Exception:
        # Metrics must never break the runtime
        pass
