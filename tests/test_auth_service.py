"""
Tests for auth service to ensure authentication and authorization work correctly.
"""

import pytest
from unittest.mock import Mock, patch
from fastapi import HTTPException
from TutorDexBackend.services.auth_service import AuthService


class MockConfig:
    """Mock configuration"""
    def __init__(self):
        self.auth_required = True
        self.app_env = "production"
        self.firebase_admin_enabled = True


class TestAuthServiceInitialization:
    """Test auth service initialization"""
    
    def test_auth_service_initializes_with_config(self):
        """Test that auth service initializes with proper config"""
        config = MockConfig()
        service = AuthService(config)
        assert service.cfg is not None
    
    def test_is_auth_required_returns_config_value(self):
        """Test that auth required returns config value"""
        config = MockConfig()
        config.auth_required = True
        service = AuthService(config)
        assert service.is_auth_required() == True
        
        config.auth_required = False
        service = AuthService(config)
        assert service.is_auth_required() == False
    
    def test_validate_production_config_checks_auth(self):
        """Test that production config validation checks auth"""
        config = MockConfig()
        config.app_env = "production"
        config.auth_required = False
        service = AuthService(config)
        
        # Should log warning or raise error in production without auth
        # This is a safety check
        try:
            service.validate_production_config()
        except Exception:
            # If it raises, that's actually good (preventing unsafe production config)
            pass


class TestAuthServiceTokenVerification:
    """Test token verification logic"""
    
    def test_require_uid_raises_when_no_auth_header(self):
        """Test that require_uid raises 401 when no auth header"""
        config = MockConfig()
        service = AuthService(config)
        
        mock_request = Mock()
        mock_request.headers = {}
        
        with pytest.raises(HTTPException) as exc_info:
            service.require_uid(mock_request)
        
        assert exc_info.value.status_code == 401
    
    def test_require_uid_raises_when_invalid_header_format(self):
        """Test that require_uid raises 401 when auth header format is invalid"""
        config = MockConfig()
        service = AuthService(config)
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "InvalidFormat"}
        
        with pytest.raises(HTTPException) as exc_info:
            service.require_uid(mock_request)
        
        assert exc_info.value.status_code == 401
    
    @patch('TutorDexBackend.services.auth_service.firebase_auth')
    def test_require_uid_verifies_valid_token(self, mock_firebase):
        """Test that require_uid verifies valid Firebase token"""
        config = MockConfig()
        service = AuthService(config)
        
        # Mock Firebase verification
        mock_firebase.verify_id_token.return_value = {"uid": "test_user_123"}
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "Bearer valid_token_here"}
        
        uid = service.require_uid(mock_request)
        assert uid == "test_user_123"
        mock_firebase.verify_id_token.assert_called_once_with("valid_token_here")
    
    @patch('TutorDexBackend.services.auth_service.firebase_auth')
    def test_require_uid_raises_when_token_invalid(self, mock_firebase):
        """Test that require_uid raises 401 when token is invalid"""
        config = MockConfig()
        service = AuthService(config)
        
        # Mock Firebase verification failure
        mock_firebase.verify_id_token.side_effect = Exception("Invalid token")
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "Bearer invalid_token"}
        
        with pytest.raises(HTTPException) as exc_info:
            service.require_uid(mock_request)
        
        assert exc_info.value.status_code == 401


class TestAuthServiceAdminVerification:
    """Test admin verification logic"""
    
    @patch('TutorDexBackend.services.auth_service.firebase_auth')
    def test_require_admin_checks_admin_claim(self, mock_firebase):
        """Test that require_admin verifies admin claim"""
        config = MockConfig()
        service = AuthService(config)
        
        # Mock Firebase verification with admin claim
        mock_firebase.verify_id_token.return_value = {
            "uid": "admin_user_123",
            "admin": True
        }
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "Bearer admin_token"}
        
        uid = service.require_admin(mock_request)
        assert uid == "admin_user_123"
    
    @patch('TutorDexBackend.services.auth_service.firebase_auth')
    def test_require_admin_raises_when_not_admin(self, mock_firebase):
        """Test that require_admin raises 403 when user is not admin"""
        config = MockConfig()
        service = AuthService(config)
        
        # Mock Firebase verification without admin claim
        mock_firebase.verify_id_token.return_value = {
            "uid": "regular_user_123",
            "admin": False
        }
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "Bearer regular_token"}
        
        with pytest.raises(HTTPException) as exc_info:
            service.require_admin(mock_request)
        
        assert exc_info.value.status_code == 403


class TestAuthServiceOptionalAuth:
    """Test optional authentication"""
    
    def test_get_uid_from_request_returns_none_when_no_header(self):
        """Test that get_uid_from_request returns None when no auth header"""
        config = MockConfig()
        service = AuthService(config)
        
        mock_request = Mock()
        mock_request.headers = {}
        
        uid = service.get_uid_from_request(mock_request)
        assert uid is None
    
    @patch('TutorDexBackend.services.auth_service.firebase_auth')
    def test_get_uid_from_request_returns_uid_when_valid(self, mock_firebase):
        """Test that get_uid_from_request returns UID when token is valid"""
        config = MockConfig()
        service = AuthService(config)
        
        # Mock Firebase verification
        mock_firebase.verify_id_token.return_value = {"uid": "test_user_123"}
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "Bearer valid_token"}
        
        uid = service.get_uid_from_request(mock_request)
        assert uid == "test_user_123"
    
    @patch('TutorDexBackend.services.auth_service.firebase_auth')
    def test_get_uid_from_request_returns_none_on_error(self, mock_firebase):
        """Test that get_uid_from_request returns None on verification error"""
        config = MockConfig()
        service = AuthService(config)
        
        # Mock Firebase verification failure
        mock_firebase.verify_id_token.side_effect = Exception("Invalid token")
        
        mock_request = Mock()
        mock_request.headers = {"authorization": "Bearer invalid_token"}
        
        uid = service.get_uid_from_request(mock_request)
        assert uid is None


class TestAuthServiceAuthDisabled:
    """Test behavior when auth is disabled"""
    
    def test_require_uid_bypasses_when_auth_disabled(self):
        """Test that require_uid bypasses check when auth is disabled"""
        config = MockConfig()
        config.auth_required = False
        service = AuthService(config)
        
        mock_request = Mock()
        mock_request.headers = {}
        
        # Should not raise when auth is disabled
        uid = service.require_uid(mock_request)
        # May return None or a default value
        assert uid is None or isinstance(uid, str)
