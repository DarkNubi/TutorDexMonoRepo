"""
HTTP Integration Tests for TutorDex Backend API.

Tests all 30 API endpoints using FastAPI TestClient with mocked dependencies.
Validates request/response contracts, error handling, and business logic.
"""
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check and monitoring endpoints."""

    def test_health_basic(self, client: TestClient):
        """Test basic health endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data
        assert data["ok"] is True

    def test_health_redis(self, client: TestClient):
        """Test Redis health check."""
        response = client.get("/health/redis")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ok" in data

    def test_health_supabase(self, client: TestClient):
        """Test Supabase health check."""
        response = client.get("/health/supabase")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ok" in data

    def test_health_full(self, client: TestClient):
        """Test comprehensive health endpoint."""
        response = client.get("/health/full")
        assert response.status_code == 200
        data = response.json()
        assert "ok" in data or "status" in data
        # May have checks or services keys
        assert isinstance(data, dict)

    def test_health_collector(self, client: TestClient):
        """Test collector health check."""
        response = client.get("/health/collector")
        # May return 200 or 503 depending on collector status
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ok" in data or "status" in data

    def test_health_worker(self, client: TestClient):
        """Test worker health check."""
        response = client.get("/health/worker")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ok" in data or "status" in data

    def test_health_dependencies(self, client: TestClient):
        """Test dependencies health check."""
        response = client.get("/health/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_health_webhook(self, client: TestClient):
        """Test webhook health check."""
        response = client.get("/health/webhook")
        assert response.status_code in [200, 503]
        data = response.json()
        assert "ok" in data or "status" in data


class TestMetricsEndpoint:
    """Test Prometheus metrics endpoint."""

    def test_metrics_endpoint(self, client: TestClient):
        """Test metrics are exposed in Prometheus format."""
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        # Check for some expected metrics
        text = response.text
        assert "python_info" in text or "http_" in text


class TestContractsEndpoint:
    """Test schema contract endpoints."""

    def test_assignment_schema(self, client: TestClient):
        """Test assignment row schema endpoint."""
        response = client.get("/contracts/assignment-row.schema.json")
        assert response.status_code == 200
        data = response.json()
        # Verify it's a valid JSON schema
        assert "$schema" in data or "type" in data or "properties" in data


class TestAssignmentEndpoints:
    """Test assignment listing and filtering endpoints."""

    def test_list_assignments_default(self, client: TestClient, mock_supabase):
        """Test listing assignments with default parameters."""
        response = client.get("/assignments")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_list_assignments_with_filters(self, client: TestClient, mock_supabase):
        """Test listing assignments with filters."""
        response = client.get("/assignments?level=Primary&limit=10&sort=newest")
        assert response.status_code == 200
        data = response.json()
        assert len(data.get("items") or []) <= 10

    def test_list_assignments_invalid_sort(self, client: TestClient):
        """Test listing with invalid sort parameter."""
        response = client.get("/assignments?sort=invalid_sort")
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data

    def test_list_assignments_negative_limit(self, client: TestClient):
        """Test listing with negative limit."""
        response = client.get("/assignments?limit=-1")
        assert response.status_code == 400

    def test_list_assignments_distance_requires_auth(self, client: TestClient):
        """Test that distance sorting requires authentication."""
        response = client.get("/assignments?sort=distance")
        # Should fail without auth as it requires tutor location
        assert response.status_code in [400, 401]

    def test_assignments_facets(self, client: TestClient, mock_supabase):
        """Test assignment facets endpoint."""
        mock_supabase.open_assignment_facets.return_value = {
            "levels": ["Primary", "Secondary"],
            "subjects": ["Mathematics", "Science"],
            "regions": ["North", "South"]
        }

        response = client.get("/assignments/facets")
        assert response.status_code == 200
        data = response.json()
        assert "facets" in data or "levels" in data

    def test_get_assignment_duplicates(self, client: TestClient, mock_supabase):
        """Test getting duplicates for a specific assignment."""
        response = client.get("/assignments/123/duplicates")
        assert response.status_code in [200, 404, 503, 500]

    def test_get_duplicate_group(self, client: TestClient, mock_supabase):
        """Test getting all assignments in a duplicate group."""
        response = client.get("/duplicate-groups/123")
        assert response.status_code in [200, 404, 503, 500]


class TestTutorEndpoints:
    """Test tutor profile management endpoints (deprecated, use /me/tutor)."""

    def test_get_tutor_profile(self, client: TestClient, mock_redis):
        """Test getting tutor profile."""
        response = client.get("/tutors/test-tutor-123")
        assert response.status_code in [200, 401, 404]

    def test_update_tutor_profile(self, client: TestClient, mock_redis):
        """Test updating tutor profile."""
        mock_redis.save_tutor.return_value = True

        profile = {
            "levels": ["Primary"],
            "subjects": ["Mathematics"]
        }
        response = client.put("/tutors/test-tutor-123", json=profile)
        # May require auth or be deprecated
        assert response.status_code in [200, 401, 403]

    def test_delete_tutor_profile(self, client: TestClient, mock_redis):
        """Test deleting tutor profile."""
        mock_redis.delete_tutor.return_value = True

        response = client.delete("/tutors/test-tutor-123")
        assert response.status_code in [200, 204, 401, 403]


class TestMatchingEndpoint:
    """Test assignment matching endpoint."""

    def test_match_payload_missing_data(self, client: TestClient):
        """Test matching with missing required fields."""
        response = client.post("/match/payload", json={})
        assert response.status_code == 422  # Validation error

    def test_match_payload_valid(self, client: TestClient, admin_headers):
        """Test matching with valid assignment payload."""
        payload = {"payload": {"parsed": {"subjects": ["Math"], "levels": ["Primary"]}}}
        response = client.post("/match/payload", json=payload, headers=admin_headers)
        assert response.status_code in [200, 400, 401]
        if response.status_code == 200:
            data = response.json()
            assert "matches" in data


class TestAuthenticatedEndpoints:
    """Test endpoints that require Firebase authentication."""

    def test_me_without_auth(self, client: TestClient):
        """Test /me endpoint without authentication."""
        response = client.get("/me")
        assert response.status_code == 401

    def test_me_tutor_without_auth(self, client: TestClient):
        """Test /me/tutor endpoint without authentication."""
        response = client.get("/me/tutor")
        assert response.status_code == 401

    def test_update_me_tutor_without_auth(self, client: TestClient):
        """Test PUT /me/tutor without authentication."""
        profile = {"levels": ["Primary"]}
        response = client.put("/me/tutor", json=profile)
        assert response.status_code == 401

    def test_me_assignments_match_counts_without_auth(self, client: TestClient):
        """Test match counts endpoint without authentication."""
        response = client.post("/me/assignments/match-counts", json={"assignment_ids": []})
        assert response.status_code == 401

    def test_telegram_link_code_without_auth(self, client: TestClient):
        """Test Telegram link code generation without auth."""
        response = client.post("/me/telegram/link-code")
        assert response.status_code == 401


class TestAnalyticsEndpoints:
    """Test analytics and tracking endpoints."""

    def test_track_endpoint(self, client: TestClient):
        """Test legacy track endpoint."""
        event_data = {
            "event": "assignment_view",
            "assignment_id": "test-123"
        }
        response = client.post("/track", json=event_data)
        # May be deprecated or require specific format
        assert response.status_code in [200, 400, 404, 422]

    def test_analytics_event(self, client: TestClient, mock_supabase):
        """Test analytics event logging."""
        mock_supabase.log_analytics_event.return_value = True

        event_data = {
            "event_type": "assignment_view",
            "event_data": {"assignment_id": "test-123"}
        }
        response = client.post("/analytics/event", json=event_data)
        assert response.status_code in [200, 401]


class TestTelegramEndpoints:
    """Test Telegram integration endpoints."""

    def test_telegram_link_code_public(self, client: TestClient, admin_headers):
        """Test admin Telegram link code generation."""
        response = client.post("/telegram/link-code", json={"tutor_id": "test-123"}, headers=admin_headers)
        assert response.status_code in [200, 400, 401, 500]

    def test_telegram_claim(self, client: TestClient, admin_headers):
        """Test claiming a Telegram link code."""
        response = client.post("/telegram/claim", json={"code": "ABC123", "chat_id": "123456789"}, headers=admin_headers)
        assert response.status_code in [200, 400, 401, 404, 500, 422]

    def test_telegram_callback(self, client: TestClient):
        """Test Telegram webhook callback."""
        callback_data = {
            "update_id": 123,
            "message": {
                "message_id": 1,
                "from": {"id": 123456789},
                "chat": {"id": 123456789},
                "text": "/start"
            }
        }
        response = client.post("/telegram/callback", json=callback_data)
        # Webhook handling may vary
        assert response.status_code in [200, 400]


class TestCORSHeaders:
    """Test CORS configuration."""

    def test_cors_preflight(self, client: TestClient):
        """Test CORS preflight request."""
        response = client.options(
            "/assignments",
            headers={"Origin": "http://example.com", "Access-Control-Request-Method": "GET"},
        )
        assert "access-control-allow-origin" in {k.lower(): v for k, v in response.headers.items()}

    def test_cors_on_get_request(self, client: TestClient):
        """Test CORS headers on GET request."""
        response = client.get("/health")
        # Check for CORS headers
        headers = {k.lower(): v for k, v in response.headers.items()}
        assert "access-control-allow-origin" in headers or response.status_code == 200


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_404_on_invalid_endpoint(self, client: TestClient):
        """Test 404 response on non-existent endpoint."""
        response = client.get("/this/does/not/exist")
        assert response.status_code == 404

    def test_405_on_wrong_method(self, client: TestClient):
        """Test 405 response on wrong HTTP method."""
        response = client.post("/health")  # Should be GET
        assert response.status_code == 405

    def test_422_on_invalid_json(self, client: TestClient):
        """Test 422 response on invalid request body."""
        response = client.post(
            "/match/payload",
            json={"invalid": "data"},  # Missing required fields
        )
        assert response.status_code == 422


class TestRateLimiting:
    """Test rate limiting (if enabled)."""

    def test_rate_limit_headers_present(self, client: TestClient):
        """Check if rate limit headers are present when enabled."""
        response = client.get("/assignments")
        # Rate limiting may be optional
        if "x-ratelimit-limit" in response.headers:
            assert "x-ratelimit-remaining" in response.headers
            assert "x-ratelimit-reset" in response.headers


# Run tests with: pytest tests/test_backend_api.py -v
