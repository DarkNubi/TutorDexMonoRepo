"""
Circuit breaker pattern for LLM API calls.

Prevents queue burn when LLM API is down by opening the circuit after N consecutive failures.
Circuit automatically closes after a timeout period to allow recovery.
"""

import time
import logging
from typing import Any, Callable, TypeVar

logger = logging.getLogger("circuit_breaker")

T = TypeVar('T')


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open (too many failures)."""
    pass


class CircuitBreaker:
    """
    Circuit breaker for LLM API calls.
    
    Tracks consecutive failures and opens the circuit when threshold is exceeded.
    Circuit remains open for timeout_seconds, then automatically resets.
    
    Args:
        failure_threshold: Number of consecutive failures before opening circuit (default: 5)
        timeout_seconds: How long circuit stays open before attempting reset (default: 60)
    """

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        self.failure_count = 0
        self.failure_threshold = max(1, failure_threshold)
        self.timeout_seconds = max(1, timeout_seconds)
        self.opened_at: float | None = None
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute function through circuit breaker.
        
        Raises:
            CircuitBreakerOpenError: If circuit is open (too many recent failures)
        """
        if self.is_open():
            self.total_calls += 1
            logger.warning(
                "circuit_breaker_open",
                extra={
                    "failure_count": self.failure_count,
                    "opened_at": self.opened_at,
                    "timeout_seconds": self.timeout_seconds,
                    "time_remaining": self._time_remaining(),
                }
            )
            raise CircuitBreakerOpenError(
                f"Circuit breaker open after {self.failure_count} consecutive failures. "
                f"Retry in {self._time_remaining():.0f}s"
            )

        self.total_calls += 1
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception:
            self.on_failure()
            raise

    def is_open(self) -> bool:
        """Check if circuit is currently open."""
        if self.opened_at is None:
            return False

        # Check if timeout has elapsed
        if time.time() - self.opened_at > self.timeout_seconds:
            logger.info(
                "circuit_breaker_timeout_elapsed",
                extra={
                    "opened_at": self.opened_at,
                    "timeout_seconds": self.timeout_seconds,
                    "resetting": True,
                }
            )
            self.opened_at = None
            self.failure_count = 0
            return False

        return True

    def on_success(self) -> None:
        """Record successful call."""
        self.total_successes += 1
        if self.failure_count > 0:
            logger.info(
                "circuit_breaker_recovered",
                extra={
                    "previous_failures": self.failure_count,
                    "total_calls": self.total_calls,
                }
            )
        self.failure_count = 0
        self.opened_at = None

    def on_failure(self) -> None:
        """Record failed call and open circuit if threshold exceeded."""
        self.failure_count += 1
        self.total_failures += 1

        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.time()
            logger.error(
                "circuit_breaker_opened",
                extra={
                    "failure_count": self.failure_count,
                    "failure_threshold": self.failure_threshold,
                    "timeout_seconds": self.timeout_seconds,
                    "total_calls": self.total_calls,
                    "total_failures": self.total_failures,
                }
            )

    def _time_remaining(self) -> float:
        """Calculate time remaining until circuit closes."""
        if self.opened_at is None:
            return 0.0
        elapsed = time.time() - self.opened_at
        return max(0.0, self.timeout_seconds - elapsed)

    def get_stats(self) -> dict:
        """Get circuit breaker statistics."""
        return {
            "is_open": self.is_open(),
            "failure_count": self.failure_count,
            "total_calls": self.total_calls,
            "total_successes": self.total_successes,
            "total_failures": self.total_failures,
            "opened_at": self.opened_at,
            "time_remaining": self._time_remaining() if self.is_open() else None,
        }
