"""
MCP Client for Supervisor Agent

This module provides a client for calling MCP server tools instead of direct imports.
"""

import logging
import os
from typing import Dict, Any, Optional
import requests
from .models import (
    PayloadResponse,
    RAGSearchResponse, 
    SignalReportResponse,
    RiskSignal
)

logger = logging.getLogger(__name__)

class MCPClient:
    """Client for calling MCP server tools via HTTP."""
    
    def __init__(self, base_url: str = None, api_key: str = None):
        self.base_url = base_url or os.getenv("MCP_BASE", "http://localhost:8001")
        self.api_key = api_key or os.getenv("MCP_API_KEY", "dev-key")
        self.headers = {"X-API-Key": self.api_key} if self.api_key else {}
        
        logger.info(f"MCP Client initialized with URL: {self.base_url}")
    
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool via MCP server."""
        try:
            response = requests.post(
                f"{self.base_url}/tool/call",
                headers={**self.headers, "Content-Type": "application/json"},
                json={"name": tool_name, "arguments": arguments},
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get("isError"):
                raise Exception(f"MCP tool error: {result['content'][0]['text']}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"MCP server error calling {tool_name}: {e}")
            raise Exception(f"Failed to call MCP tool {tool_name}: {str(e)}")
    
    async def get_latest_structured_payload(self, company_id: str) -> PayloadResponse:
        """Get latest structured payload via MCP."""
        result = await self.call_tool("get_latest_structured_payload", {"company_id": company_id})
        # Parse the JSON response
        import json
        data = json.loads(result["content"][0]["text"])
        return PayloadResponse(**data)
    
    async def rag_search_company(self, company_id: str, query: str, top_k: int = 10) -> RAGSearchResponse:
        """Search company via RAG using MCP."""
        result = await self.call_tool("rag_search_company", {
            "company_id": company_id,
            "query": query,
            "top_k": top_k
        })
        # Parse the JSON response
        import json
        data = json.loads(result["content"][0]["text"])
        return RAGSearchResponse(**data)
    
    async def report_layoff_signal(self, signal: RiskSignal) -> SignalReportResponse:
        """Report risk signal via MCP."""
        result = await self.call_tool("report_layoff_signal", {
            "company_id": signal.company_id,
            "event_type": signal.event_type,
            "description": signal.description,
            "severity": signal.severity,
            "source": signal.source,
            "metadata": signal.metadata
        })
        # Parse the JSON response
        import json
        data = json.loads(result["content"][0]["text"])
        return SignalReportResponse(**data)
