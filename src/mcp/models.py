"""
MCP Protocol Request/Response Models

This module defines Pydantic models for MCP protocol requests and responses
following the Model Context Protocol specification.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List, Literal
from datetime import datetime


# ============================================================================
# Tool Models
# ============================================================================

class ToolDefinition(BaseModel):
    """MCP tool definition schema."""
    name: str = Field(..., description="Tool name/identifier")
    description: str = Field(..., description="Tool description")
    inputSchema: Dict[str, Any] = Field(..., description="JSON schema for tool inputs")


class ToolListResponse(BaseModel):
    """Response for listing available tools."""
    tools: List[ToolDefinition] = Field(..., description="List of available tools")


class ToolCallRequest(BaseModel):
    """Request to call a tool."""
    name: str = Field(..., description="Tool name to call")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolCallResponse(BaseModel):
    """Response from tool call."""
    content: List[Dict[str, Any]] = Field(..., description="Tool output content")
    isError: bool = Field(default=False, description="Whether the result is an error")


# ============================================================================
# Resource Models
# ============================================================================

class ResourceDefinition(BaseModel):
    """MCP resource definition schema."""
    uri: str = Field(..., description="Resource URI")
    name: str = Field(..., description="Resource name")
    description: Optional[str] = Field(None, description="Resource description")
    mimeType: Optional[str] = Field(None, description="MIME type of the resource")


class ResourceListResponse(BaseModel):
    """Response for listing available resources."""
    resources: List[ResourceDefinition] = Field(..., description="List of available resources")


class ResourceReadRequest(BaseModel):
    """Request to read a resource."""
    uri: str = Field(..., description="Resource URI to read")


class ResourceReadResponse(BaseModel):
    """Response from reading a resource."""
    contents: List[Dict[str, Any]] = Field(..., description="Resource contents")
    isError: bool = Field(default=False, description="Whether the result is an error")


# ============================================================================
# Prompt Models
# ============================================================================

class PromptArgument(BaseModel):
    """Prompt argument definition."""
    name: str = Field(..., description="Argument name")
    description: Optional[str] = Field(None, description="Argument description")
    required: bool = Field(default=True, description="Whether argument is required")


class PromptDefinition(BaseModel):
    """MCP prompt definition schema."""
    name: str = Field(..., description="Prompt name/identifier")
    description: Optional[str] = Field(None, description="Prompt description")
    arguments: List[PromptArgument] = Field(default_factory=list, description="Prompt arguments")


class PromptListResponse(BaseModel):
    """Response for listing available prompts."""
    prompts: List[PromptDefinition] = Field(..., description="List of available prompts")


class PromptGetRequest(BaseModel):
    """Request to get a prompt."""
    name: str = Field(..., description="Prompt name")
    arguments: Optional[Dict[str, str]] = Field(None, description="Prompt arguments")


class PromptGetResponse(BaseModel):
    """Response from getting a prompt."""
    messages: List[Dict[str, str]] = Field(..., description="Prompt messages")
    isError: bool = Field(default=False, description="Whether the result is an error")


# ============================================================================
# Error Models
# ============================================================================

class MCPError(BaseModel):
    """MCP error response."""
    code: int = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    data: Optional[Dict[str, Any]] = Field(None, description="Additional error data")

