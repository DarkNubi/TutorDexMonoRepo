"""
Tests for Unified Supabase Client.

Verifies CRUD operations, error handling, and RPC 300 detection.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from shared.supabase_client import (
    SupabaseClient,
    SupabaseConfig,
    SupabaseError,
    SupabaseRPC300Error,
    create_client_from_env,
)


@pytest.fixture
def config():
    """Test configuration."""
    return SupabaseConfig(
        url="http://localhost:54321",
        key="test_key",
        timeout=30,
        max_retries=3,
        enabled=True
    )


@pytest.fixture
def client(config):
    """Test client."""
    return SupabaseClient(config)


class TestSupabaseConfig:
    """Test configuration dataclass."""
    
    def test_default_values(self):
        """Test default configuration values."""
        config = SupabaseConfig(url="http://test", key="key")
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.enabled is True


class TestSupabaseClient:
    """Test Supabase client operations."""
    
    def test_initialization(self, client, config):
        """Test client initialization."""
        assert client.config == config
        assert client.base_url == "http://localhost:54321/rest/v1"
        assert client.session is not None
    
    def test_headers_generation(self, client):
        """Test authentication headers."""
        headers = client._headers()
        assert headers["apikey"] == "test_key"
        assert headers["Authorization"] == "Bearer test_key"
        assert headers["Content-Type"] == "application/json"
    
    def test_headers_with_extra(self, client):
        """Test headers with additional values."""
        headers = client._headers({"X-Custom": "value"})
        assert headers["X-Custom"] == "value"
        assert "apikey" in headers
    
    @patch("shared.supabase_client.requests.Session.get")
    def test_select_basic(self, mock_get, client):
        """Test basic SELECT operation."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1, "name": "test"}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = client.select("assignments")
        
        assert result == [{"id": 1, "name": "test"}]
        assert mock_get.called
    
    @patch("shared.supabase_client.requests.Session.get")
    def test_select_with_filters(self, mock_get, client):
        """Test SELECT with filters."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1}]
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response
        
        result = client.select("assignments", filters={"status": "open"}, limit=10)
        
        assert result == [{"id": 1}]
        # Verify filters were passed
        call_args = mock_get.call_args
        assert "params" in call_args.kwargs
        params = call_args.kwargs["params"]
        assert params["status"] == "eq.open"
        assert params["limit"] == 10
    
    @patch("shared.supabase_client.requests.Session.post")
    def test_insert_single(self, mock_post, client):
        """Test INSERT single row."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1, "name": "test"}]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = client.insert("assignments", {"name": "test"})
        
        assert result == {"id": 1, "name": "test"}  # Returns single dict
        assert mock_post.called
    
    @patch("shared.supabase_client.requests.Session.post")
    def test_insert_multiple(self, mock_post, client):
        """Test INSERT multiple rows."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = client.insert("assignments", [{"name": "test1"}, {"name": "test2"}])
        
        assert len(result) == 2  # Returns list
        assert result[0]["id"] == 1
    
    @patch("shared.supabase_client.requests.Session.post")
    def test_upsert(self, mock_post, client):
        """Test UPSERT operation."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1, "name": "updated"}]
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = client.upsert("assignments", {"id": 1, "name": "updated"})
        
        assert result == {"id": 1, "name": "updated"}
        # Verify on_conflict in URL
        call_args = mock_post.call_args
        assert "on_conflict=id" in call_args.args[0]
    
    @patch("shared.supabase_client.requests.Session.patch")
    def test_update(self, mock_patch, client):
        """Test UPDATE operation."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1, "status": "closed"}]
        mock_response.raise_for_status = Mock()
        mock_patch.return_value = mock_response
        
        result = client.update("assignments", {"status": "closed"}, {"id": 1})
        
        assert len(result) == 1
        assert result[0]["status"] == "closed"
    
    @patch("shared.supabase_client.requests.Session.delete")
    def test_delete(self, mock_delete, client):
        """Test DELETE operation."""
        mock_response = Mock()
        mock_response.json.return_value = [{"id": 1}]
        mock_response.raise_for_status = Mock()
        mock_delete.return_value = mock_response
        
        result = client.delete("assignments", {"id": 1})
        
        assert len(result) == 1
        assert result[0]["id"] == 1
    
    @patch("shared.supabase_client.requests.Session.post")
    def test_rpc_success(self, mock_post, client):
        """Test successful RPC call."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}
        mock_response.raise_for_status = Mock()
        mock_post.return_value = mock_response
        
        result = client.rpc("test_function", {"param": "value"})
        
        assert result == {"result": "success"}
    
    @patch("shared.supabase_client.requests.Session.post")
    def test_rpc_300_detection(self, mock_post, client):
        """Test RPC HTTP 300 detection (audit Priority 2)."""
        mock_response = Mock()
        mock_response.status_code = 300
        mock_post.return_value = mock_response
        
        with pytest.raises(SupabaseRPC300Error) as exc_info:
            client.rpc("test_function")
        
        assert "HTTP 300" in str(exc_info.value)
        assert "test_function" in str(exc_info.value)
    
    @patch("shared.supabase_client.requests.Session.head")
    def test_count(self, mock_head, client):
        """Test count operation."""
        mock_response = Mock()
        mock_response.headers = {"Content-Range": "0-9/42"}
        mock_response.raise_for_status = Mock()
        mock_head.return_value = mock_response
        
        count = client.count("assignments")
        
        assert count == 42
    
    def test_enabled(self, client):
        """Test enabled check."""
        assert client.enabled() is True
        
        disabled_config = SupabaseConfig(url="", key="", enabled=False)
        disabled_client = SupabaseClient(disabled_config)
        assert disabled_client.enabled() is False


class TestCreateClientFromEnv:
    """Test client creation from environment variables."""
    
    @patch.dict("os.environ", {
        "SUPABASE_URL": "http://localhost:54321",
        "SUPABASE_KEY": "test_key",
        "SUPABASE_TIMEOUT": "60",
        "SUPABASE_MAX_RETRIES": "5",
        "SUPABASE_ENABLED": "1"
    })
    def test_create_from_env(self):
        """Test creating client from environment variables."""
        client = create_client_from_env()
        
        assert client.config.url == "http://localhost:54321"
        assert client.config.key == "test_key"
        assert client.config.timeout == 60
        assert client.config.max_retries == 5
        assert client.config.enabled is True
    
    @patch.dict("os.environ", {
        "SUPABASE_URL": "",
        "SUPABASE_KEY": ""
    }, clear=True)
    def test_create_from_env_disabled(self):
        """Test client is disabled when URL/key are missing."""
        client = create_client_from_env()
        
        assert client.config.enabled is False


# Run tests with: pytest tests/test_supabase_client.py -v
