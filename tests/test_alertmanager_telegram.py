"""Test alertmanager-telegram message formatting."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

# Add the alertmanager-telegram directory to sys.path
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "observability",
        "alertmanager-telegram",
    ),
)

# Import after path setup
import server  # type: ignore  # noqa: E402


def test_format_alertmanager_includes_environment(monkeypatch: Any) -> None:
    """Test that alert messages include the environment."""
    # Set environment to PROD
    monkeypatch.setattr(server, "ENVIRONMENT", "PROD")
    monkeypatch.setattr(server, "PREFIX", "[TutorDex]")

    payload: Dict[str, Any] = {
        "status": "firing",
        "commonLabels": {
            "alertname": "HighErrorRate",
            "component": "backend",
        },
        "alerts": [
            {
                "annotations": {
                    "summary": "Error rate is high",
                    "description": "Error rate exceeded threshold",
                }
            }
        ],
    }

    result = server._format_alertmanager(payload)

    # Verify environment is in the message
    assert "[PROD]" in result
    assert "FIRING" in result
    assert "HighErrorRate" in result


def test_format_alertmanager_dev_environment(monkeypatch: Any) -> None:
    """Test that alert messages show DEV environment when set to dev."""
    # Set environment to DEV
    monkeypatch.setattr(server, "ENVIRONMENT", "DEV")
    monkeypatch.setattr(server, "PREFIX", "[TutorDex]")

    payload: Dict[str, Any] = {
        "status": "resolved",
        "commonLabels": {
            "alertname": "TestAlert",
            "component": "test",
        },
        "alerts": [],
    }

    result = server._format_alertmanager(payload)

    # Verify environment is in the message
    assert "[DEV]" in result
    assert "RESOLVED" in result


def test_format_alertmanager_staging_environment(monkeypatch: Any) -> None:
    """Test that alert messages show STAGING environment when set to staging."""
    # Set environment to STAGING
    monkeypatch.setattr(server, "ENVIRONMENT", "STAGING")
    monkeypatch.setattr(server, "PREFIX", "[TutorDex]")

    payload: Dict[str, Any] = {
        "status": "firing",
        "commonLabels": {
            "alertname": "DatabaseIssue",
            "component": "database",
        },
        "alerts": [],
    }

    result = server._format_alertmanager(payload)

    # Verify environment is in the message
    assert "[STAGING]" in result
    assert "FIRING" in result
    assert "DatabaseIssue" in result
