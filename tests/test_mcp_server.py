"""
Tests for MCP Server endpoints

Tests cover:
- Tool listing and execution
- Resource listing and reading
- Prompt listing and retrieval
- Authentication
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
import json
from pathlib import Path

# Import the MCP server app
from src.mcp.server import app

# Create test client
client = TestClient(app)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_api_key(monkeypatch):
    """Set MCP_API_KEY for testing."""
    monkeypatch.setenv("MCP_API_KEY", "test-api-key")
    yield "test-api-key"
    monkeypatch.delenv("MCP_API_KEY", raising=False)


@pytest.fixture
def no_auth_mode(monkeypatch):
    """Disable authentication for testing."""
    monkeypatch.delenv("MCP_API_KEY", raising=False)


# ============================================================================
# Health Check Tests
# ============================================================================

def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "MCP Server"


def test_root_endpoint():
    """Test root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "endpoints" in data


# ============================================================================
# Tool Endpoint Tests
# ============================================================================

def test_list_tools_no_auth(no_auth_mode):
    """Test listing tools without authentication."""
    response = client.get("/tool/list")
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data
    assert len(data["tools"]) == 3
    
    tool_names = [tool["name"] for tool in data["tools"]]
    assert "get_latest_structured_payload" in tool_names
    assert "rag_search_company" in tool_names
    assert "report_layoff_signal" in tool_names


def test_list_tools_with_auth(mock_api_key):
    """Test listing tools with authentication."""
    response = client.get(
        "/tool/list",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "tools" in data


def test_list_tools_invalid_auth(mock_api_key):
    """Test listing tools with invalid API key."""
    response = client.get(
        "/tool/list",
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 403


@patch('src.mcp.handlers.tools.get_latest_structured_payload')
def test_call_tool_get_payload(mock_tool, no_auth_mode):
    """Test calling get_latest_structured_payload tool."""
    # Mock the tool response
    from src.agents.models import PayloadResponse
    mock_response = PayloadResponse(
        company_id="test_company",
        payload=None,
        source="local",
        found=False,
        error=None
    )
    mock_tool.return_value = AsyncMock(return_value=mock_response)()
    
    request = {
        "name": "get_latest_structured_payload",
        "arguments": {
            "company_id": "test_company"
        }
    }
    
    response = client.post("/tool/call", json=request)
    assert response.status_code == 200
    data = response.json()
    assert "content" in data
    assert data["isError"] is False


@patch('src.mcp.handlers.tools.rag_search_company')
def test_call_tool_rag_search(mock_tool, no_auth_mode):
    """Test calling rag_search_company tool."""
    # Mock the tool response
    from src.agents.models import RAGSearchResponse, RAGContextItem
    mock_response = RAGSearchResponse(
        company_id="test_company",
        query="test query",
        results=[],
        total_results=0,
        error=None
    )
    mock_tool.return_value = AsyncMock(return_value=mock_response)()
    
    request = {
        "name": "rag_search_company",
        "arguments": {
            "company_id": "test_company",
            "query": "test query",
            "top_k": 10
        }
    }
    
    response = client.post("/tool/call", json=request)
    assert response.status_code == 200
    data = response.json()
    assert "content" in data


def test_call_tool_invalid_name(no_auth_mode):
    """Test calling non-existent tool."""
    request = {
        "name": "invalid_tool",
        "arguments": {}
    }
    
    response = client.post("/tool/call", json=request)
    assert response.status_code == 400


def test_call_tool_missing_arguments(no_auth_mode):
    """Test calling tool with missing required arguments."""
    request = {
        "name": "get_latest_structured_payload",
        "arguments": {}
    }
    
    response = client.post("/tool/call", json=request)
    assert response.status_code == 200  # Tool handles error internally
    data = response.json()
    # Should return error in content
    assert data.get("isError") or "Error" in str(data.get("content", []))


# ============================================================================
# Resource Endpoint Tests
# ============================================================================

def test_list_resources_no_auth(no_auth_mode):
    """Test listing resources without authentication."""
    response = client.get("/resource/list")
    assert response.status_code == 200
    data = response.json()
    assert "resources" in data
    assert len(data["resources"]) > 0
    
    resource_uris = [r["uri"] for r in data["resources"]]
    assert any("company_seed" in uri for uri in resource_uris)
    assert any("payload" in uri for uri in resource_uris)
    assert any("risk_signals" in uri for uri in resource_uris)


@patch('src.mcp.handlers.resources.get_storage_client')
def test_read_resource_company_seed(mock_storage, no_auth_mode, tmp_path):
    """Test reading company seed resource."""
    # Create a temporary seed file
    seed_file = tmp_path / "forbes_ai50_seed.json"
    seed_data = [{"company_name": "Test Company", "website": "https://test.com"}]
    seed_file.write_text(json.dumps(seed_data))
    
    # Mock project root to point to tmp_path
    with patch('src.mcp.handlers.resources._get_project_root', return_value=tmp_path):
        request = {
            "uri": "mcp://resource/company_seed"
        }
        
        response = client.post("/resource/read", json=request)
        assert response.status_code == 200
        data = response.json()
        assert "contents" in data
        assert data["isError"] is False


def test_read_resource_invalid_uri(no_auth_mode):
    """Test reading resource with invalid URI."""
    request = {
        "uri": "invalid://resource/test"
    }
    
    response = client.post("/resource/read", json=request)
    assert response.status_code == 400


def test_read_resource_not_found(no_auth_mode):
    """Test reading non-existent resource."""
    request = {
        "uri": "mcp://resource/nonexistent"
    }
    
    response = client.post("/resource/read", json=request)
    assert response.status_code == 400


# ============================================================================
# Prompt Endpoint Tests
# ============================================================================

def test_list_prompts_no_auth(no_auth_mode):
    """Test listing prompts without authentication."""
    response = client.get("/prompt/list")
    assert response.status_code == 200
    data = response.json()
    assert "prompts" in data
    assert len(data["prompts"]) > 0
    
    prompt_names = [p["name"] for p in data["prompts"]]
    assert "dashboard_system" in prompt_names


def test_get_prompt_dashboard_system(no_auth_mode):
    """Test getting dashboard system prompt."""
    request = {
        "name": "dashboard_system"
    }
    
    response = client.post("/prompt/get", json=request)
    assert response.status_code == 200
    data = response.json()
    assert "messages" in data
    assert data["isError"] is False
    assert len(data["messages"]) > 0
    assert data["messages"][0]["role"] == "system"


def test_get_prompt_invalid_name(no_auth_mode):
    """Test getting non-existent prompt."""
    request = {
        "name": "nonexistent_prompt"
    }
    
    response = client.post("/prompt/get", json=request)
    assert response.status_code == 400


# ============================================================================
# Authentication Tests
# ============================================================================

def test_endpoints_require_auth_when_configured(mock_api_key):
    """Test that endpoints require auth when MCP_API_KEY is set."""
    # Try without API key
    response = client.get("/tool/list")
    assert response.status_code == 401
    
    # Try with wrong API key
    response = client.get(
        "/tool/list",
        headers={"X-API-Key": "wrong-key"}
    )
    assert response.status_code == 403
    
    # Try with correct API key
    response = client.get(
        "/tool/list",
        headers={"X-API-Key": "test-api-key"}
    )
    assert response.status_code == 200


def test_endpoints_no_auth_when_not_configured(no_auth_mode):
    """Test that endpoints work without auth when MCP_API_KEY is not set."""
    response = client.get("/tool/list")
    assert response.status_code == 200


# ============================================================================
# Integration Tests
# ============================================================================

def test_full_workflow(no_auth_mode):
    """Test a full workflow: list tools, call tool, list resources."""
    # List tools
    response = client.get("/tool/list")
    assert response.status_code == 200
    tools = response.json()["tools"]
    assert len(tools) > 0
    
    # List resources
    response = client.get("/resource/list")
    assert response.status_code == 200
    resources = response.json()["resources"]
    assert len(resources) > 0
    
    # List prompts
    response = client.get("/prompt/list")
    assert response.status_code == 200
    prompts = response.json()["prompts"]
    assert len(prompts) > 0

