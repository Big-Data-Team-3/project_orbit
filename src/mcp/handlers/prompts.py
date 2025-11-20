"""
MCP Prompt Endpoint Handlers

Handles prompt listing and retrieval for MCP protocol.
Exposes prompts: dashboard system prompt and other reusable templates
"""

import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from ..models import (
    PromptDefinition,
    PromptArgument,
    PromptListResponse,
    PromptGetRequest,
    PromptGetResponse,
)

logger = logging.getLogger(__name__)


def _get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parents[3]


# Prompt registry
PROMPT_REGISTRY: Dict[str, Dict[str, Any]] = {
    "dashboard_system": {
        "description": "System prompt for generating investor-facing diligence dashboards",
        "file": "src/prompts/dashboard_system.md",
        "arguments": []
    },
    "pe-dashboard": {
        "description": "8-section private equity dashboard template for investor diligence",
        "file": "src/prompts/dashboard_system.md",
        "arguments": []
    }
}


async def list_prompts() -> PromptListResponse:
    """
    List all available prompts.
    
    Returns:
        PromptListResponse with list of prompt definitions
    """
    prompts = []
    
    for prompt_id, metadata in PROMPT_REGISTRY.items():
        arguments = [
            PromptArgument(
                name=arg["name"],
                description=arg.get("description"),
                required=arg.get("required", True)
            )
            for arg in metadata.get("arguments", [])
        ]
        
        prompts.append(PromptDefinition(
            name=prompt_id,
            description=metadata.get("description"),
            arguments=arguments
        ))
    
    return PromptListResponse(prompts=prompts)


async def get_prompt(request: PromptGetRequest) -> PromptGetResponse:
    """
    Get a prompt template, optionally with arguments substituted.
    
    Args:
        request: Prompt get request with name and optional arguments
        
    Returns:
        PromptGetResponse with prompt messages
        
    Raises:
        ValueError: If prompt name is not found
    """
    prompt_name = request.name
    
    if prompt_name not in PROMPT_REGISTRY:
        raise ValueError(f"Prompt '{prompt_name}' not found. Available prompts: {list(PROMPT_REGISTRY.keys())}")
    
    try:
        metadata = PROMPT_REGISTRY[prompt_name]
        file_path = metadata["file"]
        
        # Load prompt from file
        project_root = _get_project_root()
        prompt_file = project_root / file_path
        
        if not prompt_file.exists():
            raise ValueError(f"Prompt file not found: {prompt_file}")
        
        prompt_content = prompt_file.read_text()
        
        # Substitute arguments if provided
        if request.arguments:
            for arg_name, arg_value in request.arguments.items():
                prompt_content = prompt_content.replace(f"{{{arg_name}}}", arg_value)
        
        # Return as system message
        messages = [{
            "role": "system",
            "content": prompt_content
        }]
        
        return PromptGetResponse(messages=messages, isError=False)
        
    except Exception as e:
        logger.error(f"Error getting prompt '{prompt_name}': {e}", exc_info=True)
        return PromptGetResponse(
            messages=[{
                "role": "system",
                "content": f"Error: {str(e)}"
            }],
            isError=True
        )

