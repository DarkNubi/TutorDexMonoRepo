"""
Test circuit breaker functionality.
"""

import time
import pytest
from TutorDexAggregator.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


def test_circuit_breaker_basic_success():
    """Test that successful calls pass through."""
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    def mock_func(x):
        return x * 2

    result = cb.call(mock_func, 5)
    assert result == 10
    assert cb.failure_count == 0
    assert not cb.is_open()


def test_circuit_breaker_opens_after_threshold():
    """Test that circuit opens after threshold failures."""
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    def failing_func():
        raise ValueError("Simulated failure")

    # First 2 failures don't open circuit
    for i in range(2):
        with pytest.raises(ValueError):
            cb.call(failing_func)
        assert not cb.is_open(), f"Circuit should not be open after {i+1} failures"

    # 3rd failure opens circuit
    with pytest.raises(ValueError):
        cb.call(failing_func)
    assert cb.is_open(), "Circuit should be open after threshold failures"

    # Further calls fail fast with CircuitBreakerOpenError
    with pytest.raises(CircuitBreakerOpenError):
        cb.call(failing_func)


def test_circuit_breaker_closes_after_timeout():
    """Test that circuit closes after timeout period."""
    cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1)

    def failing_func():
        raise ValueError("Simulated failure")

    # Open the circuit
    for i in range(2):
        with pytest.raises(ValueError):
            cb.call(failing_func)

    assert cb.is_open(), "Circuit should be open"

    # Wait for timeout
    time.sleep(1.1)

    # Circuit should auto-close
    assert not cb.is_open(), "Circuit should close after timeout"

    # Should allow calls again
    def success_func():
        return "success"

    result = cb.call(success_func)
    assert result == "success"


def test_circuit_breaker_resets_on_success():
    """Test that failure count resets on successful call."""
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    def failing_func():
        raise ValueError("Simulated failure")

    def success_func():
        return "success"

    # Accumulate some failures
    for i in range(2):
        with pytest.raises(ValueError):
            cb.call(failing_func)

    assert cb.failure_count == 2

    # Successful call resets failure count
    result = cb.call(success_func)
    assert result == "success"
    assert cb.failure_count == 0


def test_circuit_breaker_stats():
    """Test that statistics are tracked correctly."""
    cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1)

    def success_func():
        return "ok"

    def failing_func():
        raise ValueError("fail")

    # Make some calls
    cb.call(success_func)
    cb.call(success_func)

    try:
        cb.call(failing_func)
    except ValueError:
        pass

    stats = cb.get_stats()
    assert stats["total_calls"] == 3
    assert stats["total_successes"] == 2
    assert stats["total_failures"] == 1
    assert stats["failure_count"] == 1
    assert not stats["is_open"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
