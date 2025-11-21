"""
ReAct (Reasoning + Acting) models for Supervisor Agent trace logging.

This module defines the data structures for tracking the ReAct workflow:
- Thought: The agent's reasoning about what to do next
- Action: The tool call and parameters
- Observation: The result from the tool execution
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ActionType(str, Enum):
    """Types of actions the supervisor agent can take."""
    GET_PAYLOAD = "get_latest_structured_payload"
    RAG_SEARCH = "rag_search_company"
    REPORT_SIGNAL = "report_layoff_signal"
    FINAL_ANSWER = "final_answer"


class ReActStep(BaseModel):
    """A single step in the ReAct workflow (Thought → Action → Observation)."""
    
    step_number: int = Field(..., description="Sequential step number in the trace")
    thought: str = Field(..., description="Agent's reasoning about what to do next")
    action: ActionType = Field(..., description="Type of action taken")
    action_input: Dict[str, Any] = Field(default_factory=dict, description="Input parameters for the action")
    observation: Optional[str] = Field(None, description="Result or observation from the action")
    timestamp: datetime = Field(default_factory=datetime.now, description="When this step occurred")
    error: Optional[str] = Field(None, description="Error message if action failed")


class ReActTrace(BaseModel):
    """Complete ReAct workflow trace for a query execution."""
    
    query: str = Field(..., description="Original query or question")
    company_id: Optional[str] = Field(None, description="Company ID if query is company-specific")
    steps: List[ReActStep] = Field(default_factory=list, description="List of ReAct steps")
    final_answer: Optional[str] = Field(None, description="Final answer or conclusion")
    started_at: datetime = Field(default_factory=datetime.now, description="When the trace started")
    completed_at: Optional[datetime] = Field(None, description="When the trace completed")
    total_steps: int = Field(0, description="Total number of steps executed")
    success: bool = Field(False, description="Whether the workflow completed successfully")

