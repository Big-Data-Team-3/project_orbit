"""
Google Cloud Logging Integration for ReAct Traces

This module provides functionality to log ReAct traces to Google Cloud Logging.
It includes graceful fallback for non-GCP environments.
"""

import logging
import os
import json
from typing import Optional, Dict, Any
from datetime import datetime
from pathlib import Path

import dotenv

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# Try to import Google Cloud Logging
try:
    from google.cloud import logging as cloud_logging
    from google.oauth2 import service_account
    CLOUD_LOGGING_AVAILABLE = True
except ImportError:
    CLOUD_LOGGING_AVAILABLE = False
    logger.warning("google-cloud-logging not available. Cloud logging will be disabled.")


class CloudLoggingClient:
    """Client for logging ReAct traces to Google Cloud Logging."""
    
    def __init__(self):
        """Initialize Cloud Logging client."""
        self.client: Optional[Any] = None
        self.logger: Optional[Any] = None
        self.enabled = False
        self.project_id: Optional[str] = None
        self.log_name: str = "react_traces"
        
        # Check if Cloud Logging should be enabled
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize Cloud Logging client if available and configured."""
        if not CLOUD_LOGGING_AVAILABLE:
            logger.info("Cloud Logging not available (library not installed)")
            return
        
        # Check if we should enable Cloud Logging
        enable_cloud_logging = os.getenv("ENABLE_CLOUD_LOGGING", "false").lower() == "true"
        if not enable_cloud_logging:
            logger.info("Cloud Logging disabled (ENABLE_CLOUD_LOGGING not set to 'true')")
            return
        
        self.project_id = os.getenv("PROJECT_ID")
        if not self.project_id:
            logger.warning("PROJECT_ID not set. Cloud Logging disabled.")
            return
        
        try:
            # Try to initialize with credentials file (local development)
            project_root = Path(__file__).resolve().parents[2]
            credentials_path = project_root / "config" / "gcp.json"
            
            if credentials_path.exists():
                credentials = service_account.Credentials.from_service_account_file(
                    str(credentials_path)
                )
                self.client = cloud_logging.Client(
                    project=self.project_id,
                    credentials=credentials
                )
                logger.info(f"Cloud Logging client initialized with credentials from {credentials_path}")
            else:
                # Use Application Default Credentials (production/Cloud Run)
                self.client = cloud_logging.Client(project=self.project_id)
                logger.info("Cloud Logging client initialized with Application Default Credentials")
            
            # Get or create logger
            self.logger = self.client.logger(self.log_name)
            self.enabled = True
            logger.info(f"Cloud Logging enabled for project: {self.project_id}, log: {self.log_name}")
            
        except Exception as e:
            logger.error(f"Failed to initialize Cloud Logging: {e}")
            self.enabled = False
            self.client = None
            self.logger = None
    
    def log_react_trace(
        self,
        trace: Any,  # ReActTrace from react_models
        severity: str = "INFO",
        run_id: Optional[str] = None,
        phase: Optional[str] = None
    ) -> bool:
        """
        Log a ReAct trace to Google Cloud Logging.
        
        Args:
            trace: ReActTrace object to log
            severity: Log severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            run_id: Optional run ID (e.g., Airflow DAG run ID)
            phase: Optional phase identifier (e.g., "workflow_execution", "dashboard_generation")
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.enabled or not self.logger:
            return False
        
        try:
            # Convert trace to dictionary for logging
            trace_dict = self._trace_to_dict(trace)
            
            # Add run_id and phase to trace dict if provided
            if run_id:
                trace_dict["run_id"] = run_id
            if phase:
                trace_dict["phase"] = phase
            
            # Create structured log entry
            log_entry = {
                "severity": severity,
                "timestamp": trace.completed_at.isoformat() if trace.completed_at else datetime.now().isoformat(),
                "labels": {
                    "component": "react_agent",
                    "company_id": trace.company_id or "unknown",
                    "query": trace.query[:50] if trace.query else "unknown",  # Truncate for label
                    "success": str(trace.success),
                    "total_steps": str(trace.total_steps)
                },
                "json_payload": trace_dict
            }
            
            # Add run_id and phase to labels if provided
            if run_id:
                log_entry["labels"]["run_id"] = run_id
            if phase:
                log_entry["labels"]["phase"] = phase
            
            # Log to Cloud Logging
            self.logger.log_struct(
                log_entry,
                severity=severity
            )
            
            logger.debug(f"ReAct trace logged to Cloud Logging: {trace.query[:50]}...")
            return True
            
        except Exception as e:
            logger.error(f"Failed to log ReAct trace to Cloud Logging: {e}")
            return False
    
    def _trace_to_dict(self, trace: Any) -> Dict[str, Any]:
        """
        Convert ReActTrace to dictionary for logging.
        
        Args:
            trace: ReActTrace object
            
        Returns:
            Dictionary representation of the trace
        """
        try:
            # Use Pydantic's model_dump if available (Pydantic v2)
            if hasattr(trace, 'model_dump'):
                trace_dict = trace.model_dump(mode='json')
            # Fallback to dict() for Pydantic v1
            elif hasattr(trace, 'dict'):
                trace_dict = trace.dict()
            else:
                # Manual conversion as fallback
                trace_dict = {
                    "query": trace.query,
                    "company_id": trace.company_id,
                    "final_answer": trace.final_answer,
                    "started_at": trace.started_at.isoformat() if trace.started_at else None,
                    "completed_at": trace.completed_at.isoformat() if trace.completed_at else None,
                    "total_steps": trace.total_steps,
                    "success": trace.success,
                    "steps": [
                        {
                            "step_number": step.step_number,
                            "thought": step.thought,
                            "action": step.action.value if hasattr(step.action, 'value') else str(step.action),
                            "action_input": step.action_input,
                            "observation": step.observation,
                            "timestamp": step.timestamp.isoformat() if step.timestamp else None,
                            "error": step.error
                        }
                        for step in trace.steps
                    ]
                }
            
            return trace_dict
            
        except Exception as e:
            logger.error(f"Failed to convert trace to dict: {e}")
            return {
                "error": f"Failed to serialize trace: {str(e)}",
                "query": getattr(trace, 'query', 'unknown')
            }
    
    def log_step(
        self,
        step: Any,  # ReActStep from react_models
        company_id: Optional[str] = None,
        query: Optional[str] = None,
        severity: str = "INFO",
        run_id: Optional[str] = None,
        phase: Optional[str] = None
    ) -> bool:
        """
        Log an individual ReAct step to Cloud Logging.
        
        Args:
            step: ReActStep object to log
            company_id: Optional company ID for labels
            query: Optional query for labels
            severity: Log severity level
            run_id: Optional run ID (e.g., Airflow DAG run ID)
            phase: Optional phase identifier (e.g., "planner", "data_generator", "risk_detector")
            
        Returns:
            True if logged successfully, False otherwise
        """
        if not self.enabled or not self.logger:
            return False
        
        try:
            # Convert step to dictionary
            if hasattr(step, 'model_dump'):
                step_dict = step.model_dump(mode='json')
            elif hasattr(step, 'dict'):
                step_dict = step.dict()
            else:
                step_dict = {
                    "step_number": step.step_number,
                    "thought": step.thought,
                    "action": step.action.value if hasattr(step.action, 'value') else str(step.action),
                    "action_input": step.action_input,
                    "observation": step.observation,
                    "timestamp": step.timestamp.isoformat() if step.timestamp else None,
                    "error": step.error
                }
            
            # Add run_id and phase to step dict if provided
            if run_id:
                step_dict["run_id"] = run_id
            if phase:
                step_dict["phase"] = phase
            
            # Create structured log entry
            log_entry = {
                "severity": severity,
                "timestamp": step.timestamp.isoformat() if step.timestamp else datetime.now().isoformat(),
                "labels": {
                    "component": "react_agent_step",
                    "company_id": company_id or "unknown",
                    "query": (query[:50] if query else "unknown"),
                    "step_number": str(step.step_number),
                    "action": step.action.value if hasattr(step.action, 'value') else str(step.action)
                },
                "json_payload": step_dict
            }
            
            # Add run_id and phase to labels if provided
            if run_id:
                log_entry["labels"]["run_id"] = run_id
            if phase:
                log_entry["labels"]["phase"] = phase
            
            # Log to Cloud Logging
            self.logger.log_struct(
                log_entry,
                severity=severity
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to log ReAct step to Cloud Logging: {e}")
            return False


# Global Cloud Logging client instance
_cloud_logging_client: Optional[CloudLoggingClient] = None


def get_cloud_logging_client() -> CloudLoggingClient:
    """Get or create global Cloud Logging client."""
    global _cloud_logging_client
    if _cloud_logging_client is None:
        _cloud_logging_client = CloudLoggingClient()
    return _cloud_logging_client


def log_react_trace_to_cloud(
    trace: Any,
    severity: str = "INFO",
    run_id: Optional[str] = None,
    phase: Optional[str] = None
) -> bool:
    """
    Convenience function to log a ReAct trace to Cloud Logging.
    
    Args:
        trace: ReActTrace object
        severity: Log severity level
        run_id: Optional run ID (e.g., Airflow DAG run ID)
        phase: Optional phase identifier (e.g., "workflow_execution", "dashboard_generation")
        
    Returns:
        True if logged successfully, False otherwise
    """
    client = get_cloud_logging_client()
    return client.log_react_trace(trace, severity, run_id, phase)


def log_react_step_to_cloud(
    step: Any,
    company_id: Optional[str] = None,
    query: Optional[str] = None,
    severity: str = "INFO",
    run_id: Optional[str] = None,
    phase: Optional[str] = None
) -> bool:
    """
    Convenience function to log a ReAct step to Cloud Logging.
    
    Args:
        step: ReActStep object
        company_id: Optional company ID
        query: Optional query
        severity: Log severity level
        
    Returns:
        True if logged successfully, False otherwise
    """
    client = get_cloud_logging_client()
    return client.log_step(step, company_id, query, severity, run_id, phase)

