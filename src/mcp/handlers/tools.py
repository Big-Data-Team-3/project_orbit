"""
MCP Tool Endpoint Handlers

Handles tool listing and execution for MCP protocol.
Exposes agent tools: get_latest_structured_payload, rag_search_company, report_layoff_signal
"""

import logging
from typing import Dict, Any, List
from src.agents.tools import (
    get_latest_structured_payload,
    rag_search_company,
    report_layoff_signal,
)
from src.agents.models import RiskSignal
from ..models import (
    ToolDefinition,
    ToolListResponse,
    ToolCallRequest,
    ToolCallResponse,
)

logger = logging.getLogger(__name__)


# Tool registry with metadata
TOOL_REGISTRY: Dict[str, Dict[str, Any]] = {
    "get_latest_structured_payload": {
        "description": "Retrieve the latest structured payload for a company from GCS or local filesystem",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "Company ID (e.g., 'abridge', 'anthropic')"
                }
            },
            "required": ["company_id"]
        }
    },
    "rag_search_company": {
        "description": "Search vector database for company-specific context using RAG",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "Company ID to search for"
                },
                "query": {
                    "type": "string",
                    "description": "Search query (e.g., 'funding rounds', 'leadership team')"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of top results to return",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50
                }
            },
            "required": ["company_id", "query"]
        }
    },
    "report_layoff_signal": {
        "description": "Log or flag high-risk events (layoffs, breaches, regulatory issues, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "company_id": {
                    "type": "string",
                    "description": "Company ID where risk was detected"
                },
                "event_type": {
                    "type": "string",
                    "enum": [
                        "layoff", "breach", "regulatory", "security_incident",
                        "pricing_change", "hiring_spike", "leadership_change", "other"
                    ],
                    "description": "Type of risk event"
                },
                "description": {
                    "type": "string",
                    "description": "Description of the risk event"
                },
                "severity": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Severity level"
                },
                "source": {
                    "type": "string",
                    "description": "Source where risk was detected (e.g., 'news', 'website', 'api')"
                },
                "metadata": {
                    "type": "object",
                    "description": "Additional metadata about the risk"
                }
            },
            "required": ["company_id", "event_type", "description", "severity"]
        }
    }
}


async def list_tools() -> ToolListResponse:
    """
    List all available tools.
    
    Returns:
        ToolListResponse with list of tool definitions
    """
    tools = [
        ToolDefinition(
            name=name,
            description=metadata["description"],
            inputSchema=metadata["inputSchema"]
        )
        for name, metadata in TOOL_REGISTRY.items()
    ]
    
    return ToolListResponse(tools=tools)


async def call_tool(request: ToolCallRequest) -> ToolCallResponse:
    """
    Execute a tool call.
    
    Args:
        request: Tool call request with name and arguments
        
    Returns:
        ToolCallResponse with tool output
        
    Raises:
        ValueError: If tool name is not found
    """
    tool_name = request.name
    
    if tool_name not in TOOL_REGISTRY:
        raise ValueError(f"Tool '{tool_name}' not found. Available tools: {list(TOOL_REGISTRY.keys())}")
    
    try:
        # Route to appropriate tool handler
        if tool_name == "get_latest_structured_payload":
            company_id = request.arguments.get("company_id")
            if not company_id:
                raise ValueError("Missing required argument: company_id")
            
            result = await get_latest_structured_payload(company_id)
            content = [{
                "type": "text",
                "text": result.model_dump_json()
            }]
            
        elif tool_name == "rag_search_company":
            company_id = request.arguments.get("company_id")
            query = request.arguments.get("query")
            top_k = request.arguments.get("top_k", 10)
            
            if not company_id:
                raise ValueError("Missing required argument: company_id")
            if not query:
                raise ValueError("Missing required argument: query")
            
            result = await rag_search_company(company_id, query, top_k)
            content = [{
                "type": "text",
                "text": result.model_dump_json()
            }]
            
        elif tool_name == "report_layoff_signal":
            # Build RiskSignal from arguments
            signal_data = RiskSignal(
                company_id=request.arguments.get("company_id"),
                event_type=request.arguments.get("event_type"),
                description=request.arguments.get("description"),
                severity=request.arguments.get("severity"),
                source=request.arguments.get("source"),
                metadata=request.arguments.get("metadata")
            )
            
            result = await report_layoff_signal(signal_data)
            content = [{
                "type": "text",
                "text": result.model_dump_json()
            }]
            
        else:
            raise ValueError(f"Tool '{tool_name}' handler not implemented")
        
        return ToolCallResponse(content=content, isError=False)
        
    except Exception as e:
        logger.error(f"Error executing tool '{tool_name}': {e}", exc_info=True)
        return ToolCallResponse(
            content=[{
                "type": "text",
                "text": f"Error: {str(e)}"
            }],
            isError=True
        )

