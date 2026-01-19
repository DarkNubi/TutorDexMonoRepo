"""
Shared exception handler for TutorDex.

Provides observable, intention-revealing patterns for exception handling.
Use this instead of silent `except: pass` to ensure all exceptions are logged and counted.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("tutordex.exceptions")


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
    exc_type_name = type(exc).__name__
    logger.exception(
        "Swallowed exception",
        extra={
            "context": context,
            "exception_type": exc_type_name,
            **(extra or {}),
        },
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
