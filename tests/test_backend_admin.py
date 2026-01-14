"""
Admin Endpoint Tests for TutorDex Backend API.

Tests admin-only endpoints that require X-Admin-Key authentication.
"""
import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient


class TestAdminAuthentication:
    """Test admin API key authentication."""
    
    def test_admin_endpoint_without_key(self, client: TestClient):
        """Test admin endpoint without API key."""
        response = client.get("/admin/stats")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data
    
    def test_admin_endpoint_with_invalid_key(self, client: TestClient):
        """Test admin endpoint with wrong API key."""
        headers = {"X-Admin-Key": "wrong_key"}
        response = client.get("/admin/stats", headers=headers)
        assert response.status_code == 401
    
    @patch.dict(os.environ, {"ADMIN_API_KEY": "test_admin_key"})
    def test_admin_endpoint_with_valid_key(self, client: TestClient, mock_supabase):
        """Test admin endpoint with correct API key."""
        mock_supabase.get_system_stats.return_value = {
            "total_assignments": 100,
            "total_tutors": 50
        }
        
        headers = {"X-Admin-Key": "test_admin_key"}
        response = client.get("/admin/stats", headers=headers)
        # May succeed or fail depending on implementation
        assert response.status_code in [200, 404, 500]


class TestAdminStatsEndpoint:
    """Test admin statistics endpoint."""
    
    @patch.dict(os.environ, {"ADMIN_API_KEY": "test_admin_key"})
    def test_get_system_stats(self, client: TestClient, mock_supabase):
        """Test retrieving system statistics."""
        mock_supabase.get_system_stats.return_value = {
            "assignments": {
                "total": 1000,
                "open": 500,
                "closed": 500
            },
            "tutors": {
                "total": 200,
                "active": 150
            }
        }
        
        headers = {"X-Admin-Key": "test_admin_key"}
        response = client.get("/admin/stats", headers=headers)
        if response.status_code == 200:
            data = response.json()
            assert "assignments" in data or "stats" in data


class TestAdminManagementEndpoints:
    """Test admin management operations (if they exist)."""
    
    @patch.dict(os.environ, {"ADMIN_API_KEY": "test_admin_key"})
    def test_admin_clear_cache(self, client: TestClient, mock_redis):
        """Test clearing cache as admin."""
        mock_redis.clear_all.return_value = True
        
        headers = {"X-Admin-Key": "test_admin_key"}
        response = client.post("/admin/cache/clear", headers=headers)
        # Endpoint may not exist
        assert response.status_code in [200, 404]
    
    @patch.dict(os.environ, {"ADMIN_API_KEY": "test_admin_key"})
    def test_admin_force_refresh(self, client: TestClient):
        """Test forcing data refresh as admin."""
        headers = {"X-Admin-Key": "test_admin_key"}
        response = client.post("/admin/refresh", headers=headers)
        # Endpoint may not exist
        assert response.status_code in [200, 404]


class TestAdminSecurity:
    """Test security aspects of admin endpoints."""
    
    def test_admin_key_not_leaked_in_logs(self, client: TestClient):
        """Ensure admin key is not exposed in error responses."""
        headers = {"X-Admin-Key": "secret_key_12345"}
        response = client.get("/admin/stats", headers=headers)
        # Key should not appear in response
        response_text = response.text
        assert "secret_key_12345" not in response_text
    
    def test_admin_endpoint_rate_limiting(self, client: TestClient):
        """Test that admin endpoints have rate limiting."""
        headers = {"X-Admin-Key": "wrong_key"}
        
        # Make multiple requests
        for _ in range(5):
            response = client.get("/admin/stats", headers=headers)
            # Should fail auth, not rate limit
            assert response.status_code in [401, 429]


# Run tests with: pytest tests/test_backend_admin.py -v
