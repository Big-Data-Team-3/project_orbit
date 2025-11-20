"""
MCP Resource Endpoint Handlers

Handles resource listing and reading for MCP protocol.
Exposes resources: company data, payloads, risk signals
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from google.cloud import storage
from ..models import (
    ResourceDefinition,
    ResourceListResponse,
    ResourceReadRequest,
    ResourceReadResponse,
)
from src.structured_extraction import get_storage_client

logger = logging.getLogger(__name__)


def _get_project_root() -> Path:
    """Get project root directory."""
    return Path(__file__).resolve().parents[3]


def _get_bucket_name() -> Optional[str]:
    """Get GCS bucket name from environment."""
    return os.getenv("GCS_BUCKET_NAME")


# Resource registry
RESOURCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "company_seed": {
        "name": "Company Seed Data",
        "description": "Forbes AI 50 company seed data",
        "mimeType": "application/json",
        "local_path": "data/forbes_ai50_seed.json",
        "gcs_path": "seed/forbes_ai50_seed.json"
    },
    "payload": {
        "name": "Company Payload",
        "description": "Structured payload for a company (requires company_id parameter)",
        "mimeType": "application/json",
        "local_path_template": "data/payloads/{company_id}.json",
        "gcs_path_template": "payloads/{company_id}.json",
        "requires_param": "company_id"
    },
    "risk_signals": {
        "name": "Risk Signals",
        "description": "Risk signals log (requires date parameter, format: YYYY-MM-DD)",
        "mimeType": "application/x-ndjson",
        "local_path_template": "data/risk_signals/risk_signals_{date}.jsonl",
        "requires_param": "date"
    },
    "ai50/companies": {
        "name": "AI50 Company IDs",
        "description": "List of all Forbes AI50 company IDs",
        "mimeType": "application/json",
        "local_path": "data/forbes_ai50_seed.json",
        "gcs_path": "seed/forbes_ai50_seed.json",
        "handler": "company_list"
    }
}


async def list_resources() -> ResourceListResponse:
    """
    List all available resources.
    
    Returns:
        ResourceListResponse with list of resource definitions
    """
    resources = []
    
    # Add static resources
    for resource_id, metadata in RESOURCE_REGISTRY.items():
        if "requires_param" not in metadata:
            # Static resource
            uri = f"mcp://resource/{resource_id}"
            resources.append(ResourceDefinition(
                uri=uri,
                name=metadata["name"],
                description=metadata["description"],
                mimeType=metadata.get("mimeType")
            ))
        else:
            # Parameterized resource - list as template
            uri = f"mcp://resource/{resource_id}?{metadata['requires_param']}=<value>"
            resources.append(ResourceDefinition(
                uri=uri,
                name=metadata["name"],
                description=f"{metadata['description']} (requires {metadata['requires_param']} parameter)",
                mimeType=metadata.get("mimeType")
            ))
    
    return ResourceListResponse(resources=resources)


async def read_resource(request: ResourceReadRequest) -> ResourceReadResponse:
    """
    Read a resource by URI.
    
    Args:
        request: Resource read request with URI
        
    Returns:
        ResourceReadResponse with resource contents
        
    Raises:
        ValueError: If URI is invalid or resource not found
    """
    uri = request.uri
    
    # Parse URI: mcp://resource/{resource_id}?param=value
    if not uri.startswith("mcp://resource/"):
        raise ValueError(f"Invalid resource URI format: {uri}")
    
    # Extract resource ID and parameters
    uri_parts = uri.replace("mcp://resource/", "").split("?")
    resource_id = uri_parts[0]
    params = {}
    if len(uri_parts) > 1:
        for param in uri_parts[1].split("&"):
            if "=" in param:
                key, value = param.split("=", 1)
                params[key] = value
    
    if resource_id not in RESOURCE_REGISTRY:
        raise ValueError(f"Resource '{resource_id}' not found")
    
    metadata = RESOURCE_REGISTRY[resource_id]
    
    try:
        # Determine if we should use GCS or local
        bucket_name = _get_bucket_name()
        use_gcs = bucket_name is not None and get_storage_client() is not None
        
        content_text = None
        
        if resource_id == "company_seed":
            # Static resource
            if use_gcs:
                client = get_storage_client()
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(metadata["gcs_path"])
                if blob.exists():
                    content_text = blob.download_as_text()
                else:
                    raise ValueError(f"Resource not found in GCS: {metadata['gcs_path']}")
            else:
                project_root = _get_project_root()
                local_path = project_root / metadata["local_path"]
                if local_path.exists():
                    content_text = local_path.read_text()
                else:
                    raise ValueError(f"Resource not found locally: {local_path}")
        
        elif resource_id == "payload":
            # Parameterized resource
            company_id = params.get("company_id")
            if not company_id:
                raise ValueError("Missing required parameter: company_id")
            
            if use_gcs:
                client = get_storage_client()
                bucket = client.bucket(bucket_name)
                gcs_path = metadata["gcs_path_template"].format(company_id=company_id)
                blob = bucket.blob(gcs_path)
                if blob.exists():
                    content_text = blob.download_as_text()
                else:
                    raise ValueError(f"Payload not found for company_id: {company_id}")
            else:
                project_root = _get_project_root()
                local_path = project_root / metadata["local_path_template"].format(company_id=company_id)
                if local_path.exists():
                    content_text = local_path.read_text()
                else:
                    raise ValueError(f"Payload not found for company_id: {company_id}")
        
        elif resource_id == "risk_signals":
            # Parameterized resource
            date = params.get("date")
            if not date:
                raise ValueError("Missing required parameter: date")

            project_root = _get_project_root()
            local_path = project_root / metadata["local_path_template"].format(date=date)
            if local_path.exists():
                content_text = local_path.read_text()
            else:
                raise ValueError(f"Risk signals not found for date: {date}")

        elif resource_id == "ai50/companies":
            # Special handler for company IDs list
            if use_gcs:
                client = get_storage_client()
                bucket = client.bucket(bucket_name)
                blob = bucket.blob(metadata["gcs_path"])
                if blob.exists():
                    content_text = blob.download_as_text()
                else:
                    raise ValueError(f"Company seed data not found in GCS: {metadata['gcs_path']}")
            else:
                project_root = _get_project_root()
                local_path = project_root / metadata["local_path"]
                if local_path.exists():
                    content_text = local_path.read_text()
                else:
                    raise ValueError(f"Company seed data not found locally: {local_path}")

            # Parse JSON and extract company IDs
            seed_data = json.loads(content_text)
            company_ids = [company["company_name"] for company in seed_data]
            content_text = json.dumps(company_ids, indent=2)

        else:
            raise ValueError(f"Resource handler not implemented for: {resource_id}")
        
        # Parse content based on MIME type
        if metadata.get("mimeType") == "application/json":
            content_data = json.loads(content_text)
            contents = [{
                "type": "text",
                "text": json.dumps(content_data, indent=2)
            }]
        elif metadata.get("mimeType") == "application/x-ndjson":
            # JSONL format - return as array of JSON objects
            lines = [line.strip() for line in content_text.split("\n") if line.strip()]
            contents = [{
                "type": "text",
                "text": json.dumps([json.loads(line) for line in lines], indent=2)
            }]
        else:
            # Plain text
            contents = [{
                "type": "text",
                "text": content_text
            }]
        
        return ResourceReadResponse(contents=contents, isError=False)
        
    except Exception as e:
        logger.error(f"Error reading resource '{resource_id}': {e}", exc_info=True)
        return ResourceReadResponse(
            contents=[{
                "type": "text",
                "text": f"Error: {str(e)}"
            }],
            isError=True
        )

