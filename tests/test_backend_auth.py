"""
Authentication Tests for TutorDex Backend API.

Tests Firebase authentication flow, token verification, and auth-required endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient


class TestFirebaseAuth:
    """Test Firebase authentication integration."""
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_me_endpoint_with_valid_token(self, mock_require_uid, client: TestClient, mock_redis):
        """Test /me endpoint with valid Firebase token."""
        mock_require_uid.return_value = "test_user_123"
        mock_redis.get_tutor.return_value = {
            "levels": ["Primary"],
            "subjects": ["Mathematics"]
        }
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.get("/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "uid" in data
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_me_tutor_with_auth(self, mock_require_uid, client: TestClient, mock_redis):
        """Test /me/tutor endpoint with authentication."""
        mock_require_uid.return_value = "test_user_123"
        mock_redis.get_tutor.return_value = {
            "levels": ["Primary"],
            "subjects": ["Mathematics"],
            "regions": ["North"]
        }
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.get("/me/tutor", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "tutor_id" in data or "levels" in data
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_update_tutor_profile_with_auth(self, mock_require_uid, client: TestClient, mock_redis):
        """Test updating tutor profile with authentication."""
        mock_require_uid.return_value = "test_user_123"
        
        profile = {
            "levels": ["Primary", "Secondary"],
            "subjects": ["Mathematics", "Science"],
            "regions": ["North"],
            "tutor_types": ["Part-Time Tutor"],
            "max_rate": 50
        }
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.put("/me/tutor", json=profile, headers=headers)
        assert response.status_code == 200
        assert response.json().get("ok") is True
    
    def test_expired_token(self, client: TestClient):
        """Test handling of expired Firebase token."""
        headers = {"Authorization": "Bearer expired_token"}
        response = client.get("/me", headers=headers)
        assert response.status_code == 401
    
    def test_invalid_token_format(self, client: TestClient):
        """Test handling of malformed token."""
        headers = {"Authorization": "InvalidFormat"}
        response = client.get("/me", headers=headers)
        assert response.status_code == 401
    
    def test_missing_auth_header(self, client: TestClient):
        """Test request without Authorization header."""
        response = client.get("/me")
        assert response.status_code == 401
        data = response.json()
        assert "detail" in data


class TestAuthMiddleware:
    """Test authentication middleware behavior."""
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_auth_propagates_user_context(self, mock_require_uid, client: TestClient):
        """Test that user ID is available in request context."""
        mock_require_uid.return_value = "test_user_123"
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.get("/me", headers=headers)
        assert response.status_code == 200
        assert mock_require_uid.called
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_auth_allows_multiple_requests(self, mock_require_uid, client: TestClient, mock_redis):
        """Test multiple authenticated requests."""
        mock_require_uid.return_value = "test_user_123"
        mock_redis.get_tutor.return_value = None
        
        headers = {"Authorization": "Bearer valid_token"}
        
        # First request
        response1 = client.get("/me", headers=headers)
        assert response1.status_code == 200
        
        # Second request
        response2 = client.get("/me/tutor", headers=headers)
        assert response2.status_code == 200


class TestTelegramLinkingAuth:
    """Test Telegram linking flow with authentication."""
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_generate_link_code_authenticated(self, mock_require_uid, client: TestClient, mock_redis):
        """Test generating Telegram link code with auth."""
        mock_require_uid.return_value = "test_user_123"
        mock_redis.generate_link_code.return_value = "ABC123"
        
        headers = {"Authorization": "Bearer valid_token"}
        response = client.post("/me/telegram/link-code", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "link_code" in data or "code" in data


class TestMatchCountsAuth:
    """Test assignment match counts with authentication."""
    
    @patch("TutorDexBackend.services.auth_service.AuthService.require_uid")
    def test_match_counts_with_auth(self, mock_require_uid, client: TestClient, mock_redis):
        """Test getting match counts for assignments."""
        mock_require_uid.return_value = "test_user_123"
        mock_redis.get_tutor.return_value = {
            "levels": ["Primary"],
            "subjects": ["Mathematics"]
        }
        
        headers = {"Authorization": "Bearer valid_token"}
        payload = {
            "assignment_ids": ["assign-1", "assign-2"]
        }
        response = client.post("/me/assignments/match-counts", json=payload, headers=headers)
        assert response.status_code in [200, 400]


# Run tests with: pytest tests/test_backend_auth.py -v
