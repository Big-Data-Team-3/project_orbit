"""
Pydantic models for agent tool inputs and outputs.

This module defines the structured I/O models for the three core agent tools:
- PayloadResponse: Response from get_latest_structured_payload
- RAGSearchResponse: Response from rag_search_company
- RiskSignal: Input for report_layoff_signal
- SignalReportResponse: Response from report_layoff_signal
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Literal
from datetime import datetime
from ..models import Payload


class PayloadResponse(BaseModel):
    """Response model for get_latest_structured_payload tool."""
    company_id: str = Field(..., description="Company ID")
    payload: Optional[Payload] = Field(None, description="Loaded payload if found")
    loaded_at: datetime = Field(default_factory=datetime.now, description="Timestamp when payload was loaded")
    source: str = Field(..., description="Source of payload: 'gcs' or 'local'")
    found: bool = Field(..., description="Whether the payload was found")
    error: Optional[str] = Field(None, description="Error message if loading failed")


class RAGContextItem(BaseModel):
    """Individual context item from RAG search."""
    text: str = Field(..., description="Text content of the context snippet")
    source_path: str = Field(..., description="Source path of the context")
    score: float = Field(..., description="Similarity score (0-1)")


class RAGSearchResponse(BaseModel):
    """Response model for rag_search_company tool."""
    company_id: str = Field(..., description="Company ID that was searched")
    query: str = Field(..., description="Original search query")
    results: List[RAGContextItem] = Field(default_factory=list, description="List of context items")
    total_results: int = Field(0, description="Total number of results found")
    search_timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp when search was performed")
    error: Optional[str] = Field(None, description="Error message if search failed")


class RiskSignal(BaseModel):
    """Input model for report_layoff_signal tool."""
    company_id: str = Field(..., description="Company ID where risk was detected")
    event_type: Literal[
        "layoff", "breach", "regulatory", "security_incident", 
        "pricing_change", "hiring_spike", "leadership_change", "other"
    ] = Field(..., description="Type of risk event")
    description: str = Field(..., description="Description of the risk event")
    severity: Literal["low", "medium", "high", "critical"] = Field(..., description="Severity level")
    detected_at: datetime = Field(default_factory=datetime.now, description="When the risk was detected")
    source: Optional[str] = Field(None, description="Source where risk was detected (e.g., 'news', 'website', 'api')")
    metadata: Optional[Dict] = Field(None, description="Additional metadata about the risk")


class SignalReportResponse(BaseModel):
    """Response model for report_layoff_signal tool."""
    signal_id: str = Field(..., description="Unique identifier for the reported signal")
    status: Literal["logged", "flagged", "escalated"] = Field(..., description="Status of the signal report")
    message: str = Field(..., description="Human-readable status message")
    reported_at: datetime = Field(default_factory=datetime.now, description="Timestamp when signal was reported")
    company_id: str = Field(..., description="Company ID where risk was detected")
    severity: str = Field(..., description="Severity level of the signal")
    error: Optional[str] = Field(None, description="Error message if reporting failed")

