"""
Model Context Protocol (MCP) Server

This package implements an MCP server that exposes:
- Tools: Agent tools (get_latest_structured_payload, rag_search_company, report_layoff_signal)
- Resources: Company data, payloads, risk signals
- Prompts: Reusable prompt templates

The MCP server follows the protocol specification for exposing these capabilities
to AI agents and external systems via HTTP endpoints.
"""

__version__ = "0.1.0"

