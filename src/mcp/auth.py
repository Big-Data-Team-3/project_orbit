"""
Authentication Middleware for MCP Server

Provides API key authentication for MCP endpoints.
"""

import os
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from typing import Optional
import dotenv

dotenv.load_dotenv()

# API Key header name
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_api_key() -> Optional[str]:
    """Get API key from environment variable."""
    return os.getenv("MCP_API_KEY")


def verify_api_key(api_key: Optional[str] = Security(API_KEY_HEADER)) -> str:
    """
    Verify API key from request header.
    
    Args:
        api_key: API key from X-API-Key header
        
    Returns:
        The verified API key
        
    Raises:
        HTTPException: If API key is missing or invalid
    """
    expected_key = get_api_key()
    
    # If no API key is configured, allow all requests (development mode)
    if expected_key is None:
        return "dev-mode"
    
    # If API key is configured, require it
    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Please provide X-API-Key header."
        )
    
    if api_key != expected_key:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key."
        )
    
    return api_key


def require_auth():
    """
    Dependency function for endpoints that require authentication.
    
    Usage:
        @app.get("/endpoint")
        async def endpoint(api_key: str = Security(require_auth)):
            ...
    """
    return verify_api_key

