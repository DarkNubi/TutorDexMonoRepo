"""
Unit tests for shared exception handler.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from shared.observability.exception_handler import swallow_exception


def test_swallow_exception_logs_error(caplog):
    """Test that swallow_exception logs the exception with context."""
    with caplog.at_level(logging.ERROR):
        exc = ValueError("test error")
        swallow_exception(exc, context="test_context")

    # Check that exception was logged
    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert "Swallowed exception" in record.message
    assert record.context == "test_context"
    assert record.exception_type == "ValueError"


def test_swallow_exception_with_extra_context(caplog):
    """Test that extra context is included in logs."""
    with caplog.at_level(logging.ERROR):
        exc = RuntimeError("test error")
        swallow_exception(
            exc,
            context="test_context",
            extra={"module": "test_module", "operation": "test_op"}
        )

    record = caplog.records[0]
    # "module" is a reserved LogRecord attribute and cannot be overwritten; it is sanitized.
    assert record.extra_module == "test_module"
    assert record.operation == "test_op"


def test_swallow_exception_increments_metric():
    """Test that swallow_exception increments the metrics counter."""
    # Mock the metrics counter
    mock_counter = MagicMock()
    mock_labels = MagicMock()
    mock_counter.labels.return_value = mock_labels

    with patch("TutorDexAggregator.observability_metrics.swallowed_exceptions_total", mock_counter):
        exc = ValueError("test error")
        swallow_exception(exc, context="test_metric_context")

    # Verify metric was incremented
    mock_counter.labels.assert_called_once_with(
        context="test_metric_context",
        exception_type="ValueError"
    )
    mock_labels.inc.assert_called_once()


def test_swallow_exception_handles_missing_metrics():
    """Test that swallow_exception works even if metrics are not available."""
    # This should not raise an exception even if metrics module is not available
    exc = ValueError("test error")

    # Should complete without error
    swallow_exception(exc, context="test_no_metrics")


def test_swallow_exception_with_different_exception_types():
    """Test that various exception types are handled correctly."""
    exception_types = [
        ValueError("value error"),
        RuntimeError("runtime error"),
        KeyError("key error"),
        TypeError("type error"),
        Exception("generic exception"),
    ]

    for exc in exception_types:
        # Should not raise
        swallow_exception(exc, context="test_exception_types")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
