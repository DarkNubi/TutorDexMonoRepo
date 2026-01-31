"""
Pytest configuration and fixtures for backend API tests.

Provides shared fixtures for testing FastAPI endpoints with mocked dependencies.
"""
import os
import pytest
from typing import Generator, Dict, Any
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# Set test environment variables before ANY imports
os.environ["APP_ENV"] = "test"
os.environ["AUTH_REQUIRED"] = "false"
os.environ["FIREBASE_ADMIN_ENABLED"] = "false"
os.environ["SUPABASE_URL"] = "http://localhost:54321"
os.environ["SUPABASE_KEY"] = "test_key"
os.environ["REDIS_URL"] = "redis://localhost:6379/15"
os.environ["OTEL_ENABLED"] = "0"
os.environ["SENTRY_DSN"] = ""
os.environ["ADMIN_API_KEY"] = "test_admin_key"


@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Set up test environment before any tests run."""
    # Already set above
    yield


@pytest.fixture(scope="session")
def test_app():
    """
    Import and configure the FastAPI app for testing.
    """
    # Import the app which will use our test environment variables
    from TutorDexBackend.app import app
    return app


@pytest.fixture
def client(test_app, mock_redis, mock_supabase) -> Generator[TestClient, None, None]:
    """
    Create a FastAPI TestClient for making requests.
    """
    from TutorDexBackend.app_context import AppContext, get_app_context
    from TutorDexBackend.services.analytics_service import AnalyticsService
    from TutorDexBackend.services.auth_service import AuthService
    from TutorDexBackend.services.cache_service import CacheService
    from TutorDexBackend.services.health_service import HealthService
    from TutorDexBackend.services.telegram_service import TelegramService
    from shared.config import load_backend_config
    import logging

    def _override_app_context() -> AppContext:
        cfg = load_backend_config()
        auth_service = AuthService()
        health_service = HealthService(mock_redis, mock_supabase)
        cache_service = CacheService(mock_redis)
        telegram_service = TelegramService(mock_redis)
        analytics_service = AnalyticsService(mock_supabase, mock_redis)
        return AppContext(
            logger=logging.getLogger("tutordex_backend"),
            cfg=cfg,
            store=mock_redis,
            sb=mock_supabase,
            auth_service=auth_service,
            health_service=health_service,
            cache_service=cache_service,
            telegram_service=telegram_service,
            analytics_service=analytics_service,
        )

    test_app.dependency_overrides[get_app_context] = _override_app_context
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.pop(get_app_context, None)


@pytest.fixture
def mock_redis():
    """Mock Redis store behaviors."""
    mock_store = MagicMock()
    # CacheService expects a `.r` Redis client interface for rate limiting/caching.
    mock_store.r = MagicMock()
    mock_store.r.incr.return_value = 1
    mock_store.r.expire.return_value = True
    mock_store.r.get.return_value = None
    mock_store.r.setex.return_value = True

    mock_store.enabled.return_value = True
    mock_store.save_tutor.return_value = True
    mock_store.get_tutor.return_value = None
    mock_store.delete_tutor.return_value = True
    mock_store.get_all_tutors.return_value = []

    # Telegram linking helpers used by routes.
    mock_store.generate_link_code.return_value = "ABC123"

    def _create_telegram_link_code(tutor_id: str, ttl_seconds: int = 600):
        return {
            "ok": True,
            "tutor_id": tutor_id,
            "link_code": mock_store.generate_link_code(),
            "ttl_seconds": int(ttl_seconds),
        }

    mock_store.create_telegram_link_code.side_effect = _create_telegram_link_code
    mock_store.consume_telegram_link_code.side_effect = lambda code: "test-123" if str(code) == "ABC123" else None
    mock_store.set_chat_id.return_value = {"ok": True}

    # Backward-compatible aliases (older callers/tests).
    mock_store.claim_link_code.return_value = {"tutor_id": "test-123"}
    return mock_store


@pytest.fixture
def mock_supabase():
    """Mock Supabase store behaviors."""
    mock_store = MagicMock()
    mock_store.enabled.return_value = True
    # Current backend routes use `list_open_assignments` + `open_assignment_facets`.
    mock_store.list_open_assignments.return_value = {
        "items": [],
        "total": 0,
    }
    mock_store.list_open_assignments_v2.return_value = {
        "items": [],
        "total": 0,
    }
    mock_store.open_assignment_facets.return_value = {
        "levels": ["Primary"],
        "subjects": ["Mathematics"],
        "regions": ["North"],
    }

    # Backward-compatible aliases for older tests/callers (keep these to reduce churn).
    mock_store.list_assignments_paged.return_value = {
        "assignments": [],
        "pagination": {"limit": 10, "offset": 0, "total": 0}
    }
    mock_store.get_assignment.return_value = None
    mock_store.get_assignment_facets.return_value = {
        "levels": ["Primary"],
        "subjects": ["Mathematics"],
        "regions": ["North"]
    }
    mock_store.get_assignment_duplicates.return_value = []
    mock_store.get_duplicate_group_assignments.return_value = []
    mock_store.get_system_stats.return_value = {
        "total_assignments": 100,
        "total_tutors": 50
    }
    mock_store.log_analytics_event.return_value = True
    return mock_store


@pytest.fixture
def mock_firebase_auth():
    """Mock Firebase auth verification for auth-required endpoints."""
    with patch("TutorDexBackend.firebase_auth.verify_id_token") as mock:
        mock.return_value = {
            "uid": "test_user_123",
            "email": "test@example.com"
        }
        yield mock


@pytest.fixture
def auth_headers() -> Dict[str, str]:
    """Generate mock auth headers for testing protected endpoints."""
    return {"Authorization": "Bearer mock_firebase_token"}


@pytest.fixture
def admin_headers() -> Dict[str, str]:
    """Generate admin API key headers for testing admin endpoints."""
    return {"X-Admin-Key": os.environ.get("ADMIN_API_KEY", "test_admin_key")}


@pytest.fixture
def sample_assignment() -> Dict[str, Any]:
    """Sample assignment data for testing."""
    return {
        "id": "test-assignment-123",
        "level": "Primary",
        "subjects": ["Mathematics"],
        "location": {
            "region": "North",
            "postal_code": "730123"
        },
        "rate": "$30-40/hr",
        "tutor_types": ["Full-Time Tutor"],
        "scraped_at": "2026-01-14T00:00:00Z",
        "created_at": "2026-01-14T00:00:00Z"
    }


@pytest.fixture
def sample_tutor_profile() -> Dict[str, Any]:
    """Sample tutor profile data for testing."""
    return {
        "levels": ["Primary", "Secondary"],
        "subjects": ["Mathematics", "Science"],
        "regions": ["North", "Central"],
        "tutor_types": ["Part-Time Tutor"],
        "max_rate": 50
    }
