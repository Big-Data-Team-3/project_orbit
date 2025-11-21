"""
Agent Tools for Supervisor Agent

This module contains the core tools that the Supervisor Agent can use:
- get_latest_structured_payload: Retrieve structured payloads from GCS or local filesystem
- rag_search_company: Query vector DB for company-specific context
- report_layoff_signal: Log high-risk events (layoffs, breaches, etc.)

All tools are async and return Pydantic models for structured I/O.
"""
# region imports
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Tuple

import dotenv

from .models import (
    PayloadResponse,
    RAGSearchResponse,
    RAGContextItem,
    RiskSignal,
    SignalReportResponse,
)
from ..models import Payload
from ..services.embeddings import Embeddings, PineconeStorage
from ..structured_extraction_v2 import get_storage_client
# endregion
# region globals, environment variables, and logging
dotenv.load_dotenv()

# Initialize logging
logger = logging.getLogger(__name__)
# endregion
# region client initialization
_embeddings_client: Optional[Embeddings] = None
_pinecone_storage: Optional[PineconeStorage] = None
# endregion
# region helper functions
def _get_embeddings_client() -> Embeddings:
    """Get or initialize embeddings client."""
    global _embeddings_client
    if _embeddings_client is None:
        _embeddings_client = Embeddings()
    return _embeddings_client


def _get_pinecone_storage() -> PineconeStorage:
    """Get or initialize Pinecone storage client."""
    global _pinecone_storage
    if _pinecone_storage is None:
        _pinecone_storage = PineconeStorage()
    return _pinecone_storage
# endregion

# region Tool 1: Get Latest Structured Payload
# ============================================================================
# Tool 1: Get Latest Structured Payload
# ============================================================================

async def get_latest_structured_payload(company_id: str) -> PayloadResponse:
    """
    Retrieve the latest structured payload for a company.
    
    This tool loads the assembled payload from Assignment 2 (Part 1) which contains
    structured data about the company including company record, events, snapshots,
    products, leadership, and visibility data.
    
    Args:
        company_id: Company ID (e.g., "abridge", "anthropic")
        
    Returns:
        PayloadResponse: Contains the payload if found, along with metadata
    """
    try:
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        payload, source, found = await loop.run_in_executor(
            None, _load_payload_sync, company_id
        )
        
        return PayloadResponse(
            company_id=company_id,
            payload=payload,
            source=source,
            found=found,
            error=None
        )
    except Exception as e:
        logger.error(f"Error loading payload for {company_id}: {e}")
        return PayloadResponse(
            company_id=company_id,
            payload=None,
            source="unknown",
            found=False,
            error=str(e)
        )


def _load_payload_sync(company_id: str) -> Tuple[Optional[Payload], str, bool]:
    """
    Synchronous payload loading logic (runs in executor).
    
    Returns:
        Tuple of (payload, source, found)
    """
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    storage_client = get_storage_client()
    
    # Prioritize GCS if bucket name is set and client is available
    if bucket_name and storage_client:
        # Try to load from GCS first
        payload_path = f"version2/payloads/{company_id}.json"
        logger.info(f"Loading payload from GCS: gs://{bucket_name}/{payload_path}")
        
        try:
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(payload_path)
            
            if blob.exists():
                content = blob.download_as_text()
                payload_data = json.loads(content)
                payload = Payload(**payload_data)
                logger.info(f"✅ Loaded payload from GCS for {company_id}")
                return payload, "gcs", True
            else:
                logger.warning(f"⚠️  Payload not found in GCS: {payload_path}")
        except Exception as e:
            logger.error(f"⚠️  Failed to load payload from GCS: {e}")
    
    # Fallback to local filesystem
    project_root = Path(__file__).resolve().parents[2]
    payload_path = project_root / "data" / "version2" / "payloads" / f"{company_id}.json"
    logger.info(f"Loading payload from local: {payload_path}")
    
    if payload_path.exists():
        try:
            with open(payload_path, 'r') as f:
                payload_data = json.load(f)
            payload = Payload(**payload_data)
            logger.info(f"✅ Loaded payload from local file for {company_id}")
            return payload, "local", True
        except Exception as e:
            logger.error(f"⚠️  Failed to load payload from local file: {e}")
    else:
        logger.warning(f"⚠️  Payload file not found: {payload_path}")
    
    return None, "gcs" if (bucket_name and storage_client) else "local", False
    
# endregion
# region Tool 2: RAG Search Company
# ============================================================================
# Tool 2: RAG Search Company
# ============================================================================

async def rag_search_company(company_id: str, query: str, top_k: int = 10) -> RAGSearchResponse:
    """
    Search vector DB for company-specific context using RAG.
    
    This tool queries the Pinecone vector database for relevant context snippets
    related to a specific company and query. Results are filtered by company_id
    and ranked by similarity score.
    
    Args:
        company_id: Company ID to search for (e.g., "abridge", "anthropic")
        query: Search query (e.g., "funding rounds", "leadership team", "product features")
        top_k: Number of top results to return (default: 10)
        
    Returns:
        RAGSearchResponse: Contains list of context items with text, source_path, and scores
    """
    try:
        # Run in executor to avoid blocking
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None, _rag_search_sync, company_id, query, top_k
        )
        
        # Convert to RAGContextItem models
        context_items = [
            RAGContextItem(
                text=result.get("text", ""),
                source_path=result.get("source_path", ""),
                score=result.get("score", 0.0)
            )
            for result in results
        ]
        
        return RAGSearchResponse(
            company_id=company_id,
            query=query,
            results=context_items,
            total_results=len(context_items),
            error=None
        )
    except Exception as e:
        logger.error(f"Error in RAG search for {company_id} with query '{query}': {e}")
        return RAGSearchResponse(
            company_id=company_id,
            query=query,
            results=[],
            total_results=0,
            error=str(e)
        )

def _rag_search_sync(company_id: str, query: str, top_k: int) -> List[Dict]:
    """
    Synchronous RAG search logic (runs in executor).
    
    Returns:
        List of dictionaries with 'text', 'source_path', and 'score' keys
    """
    # Enhance query with company context
    enhanced_query = f"{query} {company_id} company"
    
    # Generate embedding for the query
    embeddings_client = _get_embeddings_client()
    query_embedding = embeddings_client.embed_text(enhanced_query)
    
    # Query Pinecone - get more results to filter by company_id
    pinecone_storage = _get_pinecone_storage()
    all_results = pinecone_storage.query(
        embedding=query_embedding,
        top_k=top_k * 2  # Get more results to filter from
    )
    
    # Filter results by company_id in source_path (case-insensitive)
    company_id_lower = company_id.lower()
    filtered_results = [
        result for result in all_results
        if company_id_lower in result.get("source_path", "").lower()
    ]
    
    # If we have filtered results, use them; otherwise use all results
    if filtered_results:
        return filtered_results[:top_k]
    else:
        # If no company-specific results, return top results anyway
        logger.warning(f"No company-specific results for {company_id}, returning top results")
        return all_results[:top_k]
# endregion
# region Tool 3: Report Layoff Signal
# ============================================================================
# Tool 3: Report Layoff Signal
# ============================================================================

async def report_layoff_signal(signal_data: RiskSignal) -> SignalReportResponse:
    """
    Log or flag high-risk events (layoffs, breaches, regulatory issues, etc.).
    
    This tool records risk signals that may require human review or escalation.
    Signals are logged to a structured log file for audit and monitoring purposes.
    
    Args:
        signal_data: RiskSignal model containing event details
        
    Returns:
        SignalReportResponse: Confirmation with signal ID and status
    """
    try:
        # Generate unique signal ID
        signal_id = str(uuid.uuid4())
        
        # Determine status based on severity
        if signal_data.severity in ["critical", "high"]:
            status = "escalated"
            message = f"High-severity risk signal logged and escalated for {signal_data.company_id}"
        elif signal_data.severity == "medium":
            status = "flagged"
            message = f"Medium-severity risk signal flagged for {signal_data.company_id}"
        else:
            status = "logged"
            message = f"Risk signal logged for {signal_data.company_id}"
        
        # Log the signal (run in executor)
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, _log_risk_signal_sync, signal_id, signal_data
        )
        
        logger.info(f"✅ Risk signal reported: {signal_id} for {signal_data.company_id} ({signal_data.severity})")
        
        return SignalReportResponse(
            signal_id=signal_id,
            status=status,
            message=message,
            company_id=signal_data.company_id,
            severity=signal_data.severity,
            error=None
        )
    except Exception as e:
        logger.error(f"Error reporting risk signal for {signal_data.company_id}: {e}")
        return SignalReportResponse(
            signal_id="",
            status="logged",
            message=f"Failed to report signal: {str(e)}",
            company_id=signal_data.company_id,
            severity=signal_data.severity,
            error=str(e)
        )


def _log_risk_signal_sync(signal_id: str, signal_data: RiskSignal) -> None:
    """
    Synchronous risk signal logging (runs in executor).
    
    Logs to a structured JSON file for audit and monitoring.
    """
    project_root = Path(__file__).resolve().parents[2]
    logs_dir = project_root / "data" / "risk_signals"
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Create log entry
    log_entry = {
        "signal_id": signal_id,
        "company_id": signal_data.company_id,
        "event_type": signal_data.event_type,
        "description": signal_data.description,
        "severity": signal_data.severity,
        "detected_at": signal_data.detected_at.isoformat(),
        "source": signal_data.source,
        "metadata": signal_data.metadata,
        "logged_at": datetime.now().isoformat()
    }
    
    # Append to log file (one file per day for easier management)
    log_file = logs_dir / f"risk_signals_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')
    
    logger.info(f"Risk signal logged to {log_file}")

# endregion