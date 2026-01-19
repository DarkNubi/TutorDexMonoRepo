"""
Simple manual test for circuit breaker (no pytest required).
Run with: python tests/manual_test_circuit_breaker.py
"""

import time
import sys
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from TutorDexAggregator.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError


def test_basic_success():
    """Test that successful calls pass through."""
    print("Test 1: Basic success...")
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    def mock_func(x):
        return x * 2

    result = cb.call(mock_func, 5)
    assert result == 10, f"Expected 10, got {result}"
    assert cb.failure_count == 0, f"Expected 0 failures, got {cb.failure_count}"
    assert not cb.is_open(), "Circuit should not be open"
    print("✓ PASS")


def test_opens_after_threshold():
    """Test that circuit opens after threshold failures."""
    print("\nTest 2: Opens after threshold...")
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    def failing_func():
        raise ValueError("Simulated failure")

    # First 2 failures don't open circuit
    for i in range(2):
        try:
            cb.call(failing_func)
        except ValueError:
            pass
        assert not cb.is_open(), f"Circuit should not be open after {i+1} failures"

    # 3rd failure opens circuit
    try:
        cb.call(failing_func)
    except ValueError:
        pass
    assert cb.is_open(), "Circuit should be open after threshold failures"

    # Further calls fail fast with CircuitBreakerOpenError
    try:
        cb.call(failing_func)
        assert False, "Should have raised CircuitBreakerOpenError"
    except CircuitBreakerOpenError:
        pass  # Expected

    print("✓ PASS")


def test_closes_after_timeout():
    """Test that circuit closes after timeout period."""
    print("\nTest 3: Closes after timeout...")
    cb = CircuitBreaker(failure_threshold=2, timeout_seconds=1)

    def failing_func():
        raise ValueError("Simulated failure")

    # Open the circuit
    for i in range(2):
        try:
            cb.call(failing_func)
        except ValueError:
            pass

    assert cb.is_open(), "Circuit should be open"
    print("  Circuit opened, waiting 1.1s for timeout...")

    # Wait for timeout
    time.sleep(1.1)

    # Circuit should auto-close
    assert not cb.is_open(), "Circuit should close after timeout"

    # Should allow calls again
    def success_func():
        return "success"

    result = cb.call(success_func)
    assert result == "success", f"Expected 'success', got {result}"
    print("✓ PASS")


def test_resets_on_success():
    """Test that failure count resets on successful call."""
    print("\nTest 4: Resets on success...")
    cb = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

    def failing_func():
        raise ValueError("Simulated failure")

    def success_func():
        return "success"

    # Accumulate some failures
    for i in range(2):
        try:
            cb.call(failing_func)
        except ValueError:
            pass

    assert cb.failure_count == 2, f"Expected 2 failures, got {cb.failure_count}"

    # Successful call resets failure count
    result = cb.call(success_func)
    assert result == "success", f"Expected 'success', got {result}"
    assert cb.failure_count == 0, f"Expected 0 failures after success, got {cb.failure_count}"
    print("✓ PASS")


def test_stats():
    """Test that statistics are tracked correctly."""
    print("\nTest 5: Statistics tracking...")
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
    assert stats["total_calls"] == 3, f"Expected 3 total calls, got {stats['total_calls']}"
    assert stats["total_successes"] == 2, f"Expected 2 successes, got {stats['total_successes']}"
    assert stats["total_failures"] == 1, f"Expected 1 failure, got {stats['total_failures']}"
    assert stats["failure_count"] == 1, f"Expected 1 in failure count, got {stats['failure_count']}"
    assert not stats["is_open"], "Circuit should not be open"
    print("✓ PASS")


if __name__ == "__main__":
    print("="*60)
    print("Circuit Breaker Manual Tests")
    print("="*60)

    try:
        test_basic_success()
        test_opens_after_threshold()
        test_closes_after_timeout()
        test_resets_on_success()
        test_stats()

        print("\n" + "="*60)
        print("✓ ALL TESTS PASSED")
        print("="*60)
    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
