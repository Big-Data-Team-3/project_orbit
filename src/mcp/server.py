"""
MCP Server - Main FastAPI Application

Implements Model Context Protocol server exposing:
- /tool/* endpoints for agent tools
- /resource/* endpoints for resources
- /prompt/* endpoints for prompts

Follows MCP protocol specification for agent integration.
"""

import logging
from fastapi import FastAPI, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .auth import require_auth
from .models import (
    ToolListResponse,
    ToolCallRequest,
    ToolCallResponse,
    ResourceListResponse,
    ResourceReadRequest,
    ResourceReadResponse,
    PromptListResponse,
    PromptGetRequest,
    PromptGetResponse,
    MCPError,
)
from .handlers import tools, resources, prompts

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MCP Server - Project Orbit",
    description="Model Context Protocol server for exposing agent tools, resources, and prompts",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware for cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Error Handlers
# ============================================================================

@app.exception_handler(ValueError)
async def value_error_handler(request, exc: ValueError):
    """Handle ValueError exceptions."""
    return JSONResponse(
        status_code=400,
        content=MCPError(
            code=400,
            message=str(exc),
            data={"type": "ValueError"}
        ).model_dump()
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Handle general exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content=MCPError(
            code=500,
            message="Internal server error",
            data={"type": type(exc).__name__, "detail": str(exc)}
        ).model_dump()
    )


# ============================================================================
# Health Check
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "MCP Server",
        "version": "0.1.0"
    }


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": "MCP Server - Project Orbit",
        "version": "0.1.0",
        "protocol": "Model Context Protocol",
        "endpoints": {
            "tools": "/tool/list, /tool/call",
            "resources": "/resource/list, /resource/read",
            "prompts": "/prompt/list, /prompt/get",
            "docs": "/docs"
        }
    }


# ============================================================================
# Tool Endpoints
# ============================================================================

@app.get(
    "/tool/list",
    response_model=ToolListResponse,
    tags=["Tools"],
    summary="List available tools"
)
async def list_tools_endpoint(api_key: str = Security(require_auth)):
    """
    List all available tools.
    
    Returns a list of tool definitions with their schemas.
    """
    return await tools.list_tools()


@app.post(
    "/tool/call",
    response_model=ToolCallResponse,
    tags=["Tools"],
    summary="Call a tool"
)
async def call_tool_endpoint(
    request: ToolCallRequest,
    api_key: str = Security(require_auth)
):
    """
    Execute a tool call.
    
    - **name**: Tool name to call
    - **arguments**: Tool arguments as JSON object
    
    Returns tool execution result.
    """
    return await tools.call_tool(request)


# ============================================================================
# Resource Endpoints
# ============================================================================

@app.get(
    "/resource/list",
    response_model=ResourceListResponse,
    tags=["Resources"],
    summary="List available resources"
)
async def list_resources_endpoint(api_key: str = Security(require_auth)):
    """
    List all available resources.
    
    Returns a list of resource definitions with their URIs.
    """
    return await resources.list_resources()


@app.post(
    "/resource/read",
    response_model=ResourceReadResponse,
    tags=["Resources"],
    summary="Read a resource"
)
async def read_resource_endpoint(
    request: ResourceReadRequest,
    api_key: str = Security(require_auth)
):
    """
    Read a resource by URI.
    
    - **uri**: Resource URI (e.g., "mcp://resource/payload?company_id=abridge")
    
    Returns resource contents.
    """
    return await resources.read_resource(request)


# ============================================================================
# Prompt Endpoints
# ============================================================================

@app.get(
    "/prompt/list",
    response_model=PromptListResponse,
    tags=["Prompts"],
    summary="List available prompts"
)
async def list_prompts_endpoint(api_key: str = Security(require_auth)):
    """
    List all available prompts.
    
    Returns a list of prompt definitions with their arguments.
    """
    return await prompts.list_prompts()


@app.post(
    "/prompt/get",
    response_model=PromptGetResponse,
    tags=["Prompts"],
    summary="Get a prompt"
)
async def get_prompt_endpoint(
    request: PromptGetRequest,
    api_key: str = Security(require_auth)
):
    """
    Get a prompt template.
    
    - **name**: Prompt name
    - **arguments**: Optional prompt arguments for substitution
    
    Returns prompt messages ready for LLM use.
    """
    return await prompts.get_prompt(request)

