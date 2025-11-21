"""
Graph-Based Workflow for Dashboard Creation

This module implements Lab 17: A directed graph workflow for dashboard creation with:
- Nodes: Planner, Data Generator, Evaluator, Risk Detector
- Conditional branching: Standard path (no risk) vs Risk path (with HITL)
- Workflow execution with state management
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Awaitable
from pathlib import Path
import json
from .metrics import increment_dashboard_generated, increment_hitl_triggered, increment_dashboard_failed


import dotenv
from openai import OpenAI

from .models import RiskSignal

# Lazy imports to avoid circular dependencies
def _get_risk_detection():
    from ..risk_detection import detect_risk_signals, search_risks_in_company
    return detect_risk_signals, search_risks_in_company

def _get_rag_pipeline():
    from ..rag_pipeline import generate_dashboard, retrieve_context
    return generate_dashboard, retrieve_context

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# OpenAI client initialization
_openai_client: Optional[OpenAI] = None

def _get_openai_client() -> OpenAI:
    """Get or initialize OpenAI client."""
    global _openai_client
    if _openai_client is None:
        import os
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client


class NodeStatus(str, Enum):
    """Status of a workflow node."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    """Status of the overall workflow."""
    NOT_STARTED = "not_started"
    RUNNING = "running"
    PAUSED_FOR_APPROVAL = "paused_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class NodeResult:
    """Result from executing a workflow node."""
    node_name: str
    status: NodeStatus
    output: Optional[Any] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class WorkflowState:
    """State of the workflow execution."""
    company_name: str
    company_id: Optional[str] = None
    status: WorkflowStatus = WorkflowStatus.NOT_STARTED
    current_node: Optional[str] = None
    node_results: Dict[str, NodeResult] = field(default_factory=dict)
    dashboard: Optional[str] = None
    risk_detected: bool = False
    risk_signals: List[Dict] = field(default_factory=list)
    hitl_approval_id: Optional[str] = None
    hitl_approved: Optional[bool] = None
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None


class WorkflowNode(ABC):
    """Base class for workflow nodes."""
    
    def __init__(self, name: str):
        self.name = name
        self.status = NodeStatus.PENDING
    
    @abstractmethod
    async def execute(self, state: WorkflowState) -> NodeResult:
        """
        Execute the node's logic.
        
        Args:
            state: Current workflow state
            
        Returns:
            NodeResult with execution results
        """
        pass
    
    def get_next_nodes(self, state: WorkflowState) -> List[str]:
        """
        Determine which nodes to execute next based on current state.
        
        Args:
            state: Current workflow state
            
        Returns:
            List of node names to execute next
        """
        return []


class PlannerNode(WorkflowNode):
    """Planner node: Plans the dashboard creation strategy."""
    
    def __init__(self):
        super().__init__("planner")
    
    async def execute(self, state: WorkflowState) -> NodeResult:
        """Plan the dashboard creation approach."""
        self.status = NodeStatus.RUNNING
        logger.info(f"Executing {self.name} node for {state.company_name}")
        
        try:
            # Extract company_id from company_name if not set
            if not state.company_id:
                state.company_id = state.company_name.lower().replace(" ", "_")
            
            # Plan the dashboard generation strategy
            plan = {
                "company_name": state.company_name,
                "company_id": state.company_id,
                "strategy": "rag_pipeline",  # Could be "structured" or "rag_pipeline"
                "sections_required": [
                    "Company Overview",
                    "Business Model and GTM",
                    "Funding & Investor Profile",
                    "Growth Momentum",
                    "Visibility & Market Sentiment",
                    "Risks and Challenges",
                    "Outlook",
                    "Disclosure Gaps"
                ]
            }
            
            self.status = NodeStatus.COMPLETED
            return NodeResult(
                node_name=self.name,
                status=self.status,
                output=plan,
                metadata={"planned_at": datetime.now().isoformat()}
            )
        except Exception as e:
            self.status = NodeStatus.FAILED
            logger.error(f"Error in {self.name}: {e}")
            return NodeResult(
                node_name=self.name,
                status=self.status,
                error=str(e)
            )
    
    def get_next_nodes(self, state: WorkflowState) -> List[str]:
        """After planning, go to data generator."""
        return ["data_generator"]


class DataGeneratorNode(WorkflowNode):
    """Data Generator node: Generates dashboard data using RAG pipeline."""
    
    def __init__(self):
        super().__init__("data_generator")
    
    async def execute(self, state: WorkflowState) -> NodeResult:
        """Generate dashboard data."""
        self.status = NodeStatus.RUNNING
        logger.info(f"🔄 Executing {self.name} node")
        logger.info(f"   Company Name: '{state.company_name}'")
        logger.info(f"   Company ID: '{state.company_id}'")
        
        try:
            # Generate dashboard using RAG pipeline
            # Use company_id for vector DB lookup (matches source_path format like "anthropic/homepage")
            # Use company_name for LLM display (better for generating proper company name in output)
            company_identifier = state.company_id if state.company_id else state.company_name.lower().replace(" ", "_")
            logger.info(f"   📌 Using company_identifier='{company_identifier}' for vector DB lookup")
            logger.info(f"   📌 Using company_display_name='{state.company_name}' for LLM prompt")
            
            generate_dashboard, _ = _get_rag_pipeline()
            logger.info(f"   🚀 Calling generate_dashboard(company_identifier='{company_identifier}', company_display_name='{state.company_name}')")
            dashboard = generate_dashboard(company_identifier, company_display_name=state.company_name)
            
            logger.info(f"   ✅ Dashboard generated successfully ({len(dashboard)} characters)")
            logger.info(f"   📊 Dashboard preview (first 200 chars): {dashboard[:200]}...")
            
            state.dashboard = dashboard
            
            self.status = NodeStatus.COMPLETED
            return NodeResult(
                node_name=self.name,
                status=self.status,
                output={"dashboard": dashboard},
                metadata={"generated_at": datetime.now().isoformat()}
            )
        except Exception as e:
            self.status = NodeStatus.FAILED
            logger.error(f"Error in {self.name}: {e}")
            return NodeResult(
                node_name=self.name,
                status=self.status,
                error=str(e)
            )
    
    def get_next_nodes(self, state: WorkflowState) -> List[str]:
        """After generating data, check for risks."""
        return ["risk_detector"]


class RiskDetectorNode(WorkflowNode):
    """Risk Detector node: Detects risks in the generated dashboard and company data."""
    
    def __init__(self):
        super().__init__("risk_detector")
    
    async def execute(self, state: WorkflowState) -> NodeResult:
        """Detect risks in dashboard and company data."""
        self.status = NodeStatus.RUNNING
        logger.info(f"Executing {self.name} node for {state.company_name}")
        
        try:
            detect_risk_signals, search_risks_in_company = _get_risk_detection()
            _, retrieve_context = _get_rag_pipeline()
            
            risk_signals = []
            
            # Check dashboard content for risks
            if state.dashboard:
                dashboard_risks = detect_risk_signals(state.dashboard)
                risk_signals.extend(dashboard_risks)
            
            # Check company data for risks
            if state.company_id:
                company_risks = search_risks_in_company(state.company_id)
                risk_signals.extend(company_risks)
            
            # Also check retrieved context for risks
            # Use company_id for proper vector DB filtering (matches source_path format)
            company_identifier = state.company_id if state.company_id else state.company_name.lower().replace(" ", "_")
            contexts = retrieve_context(company_identifier, top_k=10)
            for ctx in contexts:
                text = ctx.get("text", "")
                ctx_risks = detect_risk_signals(text)
                for risk in ctx_risks:
                    risk["source_path"] = ctx.get("source_path", "unknown")
                    risk["score"] = ctx.get("score", 0)
                risk_signals.extend(ctx_risks)
            
            # Remove duplicates
            seen = set()
            unique_risks = []
            for risk in risk_signals:
                key = (risk.get("risk_type"), risk.get("source_path"))
                if key not in seen:
                    seen.add(key)
                    unique_risks.append(risk)
            
            state.risk_signals = unique_risks
            state.risk_detected = len(unique_risks) > 0
            
            logger.info(f"   ✅ Risk detection completed: {len(unique_risks)} risks found, risk_detected={state.risk_detected}")
            logger.info(f"   📊 Next node will be: {'hitl_pause' if state.risk_detected else 'evaluator'}")
            
            # Increment HITL triggered metric if risk detected
            if state.risk_detected:
                try:
                    from .metrics import increment_hitl_triggered
                    increment_hitl_triggered(state.company_id)
                except Exception as e:
                    logger.debug(f"Failed to increment HITL metric: {e}")

            self.status = NodeStatus.COMPLETED
            logger.info(f"   🔄 Risk detector returning NodeResult with status {self.status}")
            result = NodeResult(
                node_name=self.name,
                status=self.status,
                output={
                    "risk_detected": state.risk_detected,
                    "risk_count": len(unique_risks),
                    "risks": unique_risks
                },
                metadata={"detected_at": datetime.now().isoformat()}
            )
            logger.info(f"   ✅ Risk detector NodeResult created, returning now")
            return result
        except Exception as e:
            self.status = NodeStatus.FAILED
            logger.error(f"Error in {self.name}: {e}")
            return NodeResult(
                node_name=self.name,
                status=self.status,
                error=str(e)
            )
    
    def get_next_nodes(self, state: WorkflowState) -> List[str]:
        """Branch based on risk detection."""
        if state.risk_detected:
            # Risk detected: go to HITL pause
            return ["hitl_pause"]
        else:
            # No risk: go to evaluator
            return ["evaluator"]


class HITLPauseNode(WorkflowNode):
    """HITL Pause node: Pauses workflow for human approval when risk is detected."""
    
    def __init__(self, approval_callback: Optional[Callable[[str], Awaitable[bool]]] = None):
        super().__init__("hitl_pause")
        self.approval_callback = approval_callback
    
    async def execute(self, state: WorkflowState) -> NodeResult:
        """Pause workflow and wait for human approval."""
        self.status = NodeStatus.RUNNING
        logger.info(f"Executing {self.name} node - pausing for approval")
        logger.info(f"   🏢 Company: {state.company_name}")
        logger.info(f"   ⚠️  Risks detected: {len(state.risk_signals)}")
        logger.info(f"   ⏱️  Timeout: 30 seconds")

        # Generate approval ID
        import uuid
        approval_id = str(uuid.uuid4())
        logger.info(f"   🆔 Approval ID: {approval_id}")
        state.hitl_approval_id = approval_id
        state.status = WorkflowStatus.PAUSED_FOR_APPROVAL

        # Create approval request
        approval_request = {
            "approval_id": approval_id,
            "company_name": state.company_name,
            "risk_count": len(state.risk_signals),
            "risks": state.risk_signals[:5],  # Show top 5 risks
            "dashboard_preview": state.dashboard[:500] if state.dashboard else None,
            "paused_at": datetime.now().isoformat()
        }

        # Save approval request to file (for HITL system)
        self._save_approval_request(approval_request)

        # Log HITL pause event
        logger.info(
            f"HITL_PAUSE: Workflow paused for approval. "
            f"Approval ID: {approval_id}, Company: {state.company_name}, "
            f"Risk Count: {len(state.risk_signals)}"
        )

        # If callback provided, use it; otherwise wait for file-based approval
        if self.approval_callback:
            approved = await self.approval_callback(approval_id)
        else:
            # Wait for approval file to be created/updated
            approved = await self._wait_for_approval(approval_id)

        state.hitl_approved = approved

        if approved:
            state.status = WorkflowStatus.APPROVED
            self.status = NodeStatus.COMPLETED

            # Log HITL approval event
            logger.info(
                f"HITL_APPROVED: Approval granted. "
                f"Approval ID: {approval_id}, Company: {state.company_name}"
            )

            return NodeResult(
                node_name=self.name,
                status=self.status,
                output={"approved": True, "approval_id": approval_id},
                metadata={"approved_at": datetime.now().isoformat()}
            )
        else:
            state.status = WorkflowStatus.REJECTED
            self.status = NodeStatus.COMPLETED

            # Log HITL rejection event
            logger.warning(
                f"HITL_REJECTED: Approval denied (timed out). "
                f"Approval ID: {approval_id}, Company: {state.company_name}"
            )

            return NodeResult(
                node_name=self.name,
                status=self.status,
                output={"approved": False, "approval_id": approval_id},
                metadata={"rejected_at": datetime.now().isoformat()}
            )
        
    

    def _save_approval_request(self, request: Dict) -> None:
        """Save approval request to file."""
        project_root = Path(__file__).resolve().parents[2]
        hitl_dir = project_root / "data" / "hitl_approvals"
        hitl_dir.mkdir(parents=True, exist_ok=True)
        
        approval_file = hitl_dir / f"{request['approval_id']}.json"
        with open(approval_file, 'w') as f:
            json.dump(request, f, indent=2)
        
        logger.info(f"Saved approval request to {approval_file}")
    
    async def _wait_for_approval(self, approval_id: str, timeout: int = 30) -> bool:
        """Wait for approval file to be updated (for testing)."""
        import asyncio
        import time

        project_root = Path(__file__).resolve().parents[2]
        approval_file = project_root / "data" / "hitl_approvals" / f"{approval_id}.json"

        logger.info(f"   ⏳ Waiting for approval file: {approval_file}")
        logger.info(f"   ⏱️  Timeout: {timeout} seconds")

        start_time = time.time()
        while time.time() - start_time < timeout:
            if approval_file.exists():
                try:
                    with open(approval_file, 'r') as f:
                        data = json.load(f)
                    if "approved" in data:
                        logger.info(f"   ✅ Found approval decision: {data['approved']}")
                        return data["approved"]
                except Exception as e:
                    logger.debug(f"   ⚠️  Error reading approval file: {e}")
            await asyncio.sleep(1)

        # Timeout: default to False (reject)
        logger.warning(f"   ⏰ Timeout reached after {timeout} seconds - rejecting")
        return False
    
    def get_next_nodes(self, state: WorkflowState) -> List[str]:
        """After HITL, proceed to evaluator if approved."""
        if state.hitl_approved:
            return ["evaluator"]
        else:
            # Rejected: end workflow
            return []


class EvaluatorNode(WorkflowNode):
    """Evaluator node: Evaluates and finalizes the dashboard."""
    
    def __init__(self):
        super().__init__("evaluator")
    
    async def execute(self, state: WorkflowState) -> NodeResult:
        """Evaluate and finalize dashboard."""
        logger.info(f"   🚀 Starting EvaluatorNode.execute() for {state.company_name}")
        self.status = NodeStatus.RUNNING
        logger.info(f"Executing {self.name} node for {state.company_name}")

        try:
            logger.info(f"   📋 Evaluating dashboard (length: {len(state.dashboard) if state.dashboard else 0})")

            # Validate dashboard has all required sections
            required_sections = [
                "## Company Overview",
                "## Business Model and GTM",
                "## Funding & Investor Profile",
                "## Growth Momentum",
                "## Visibility & Market Sentiment",
                "## Risks and Challenges",
                "## Outlook",
                "## Disclosure Gaps"
            ]

            logger.info(f"   📋 Checking for {len(required_sections)} required sections...")

            missing_sections = []
            if state.dashboard:
                for section in required_sections:
                    if section not in state.dashboard:
                        missing_sections.append(section)
                        logger.warning(f"   ⚠️  Missing section: {section}")
                    else:
                        logger.debug(f"   ✅ Found section: {section}")

            evaluation = {
                "dashboard_complete": len(missing_sections) == 0,
                "missing_sections": missing_sections,
                "risk_detected": state.risk_detected,
                "risk_count": len(state.risk_signals),
                "hitl_approved": state.hitl_approved if state.risk_detected else None
            }

            logger.info(f"   ✅ Evaluation complete: dashboard_complete={evaluation['dashboard_complete']}")
            logger.info(f"   📊 Missing sections: {len(missing_sections)}")
            
            # Increment dashboard generated metric if dashboard is complete
            if evaluation.get('dashboard_complete') and state.dashboard:
                try:
                    from .metrics import increment_dashboard_generated
                    increment_dashboard_generated(state.company_id)
                except Exception as e:
                    logger.debug(f"Failed to increment dashboard metric: {e}")

            self.status = NodeStatus.COMPLETED
            logger.info(f"   🔄 EvaluatorNode status set to {self.status}")
            result = NodeResult(
                node_name=self.name,
                status=self.status,
                output=evaluation,
                metadata={"evaluated_at": datetime.now().isoformat()}
            )
            logger.info(f"   ✅ EvaluatorNode NodeResult created, returning now")
            return result
        except Exception as e:
            logger.error(f"Error in {self.name}: {e}")
            self.status = NodeStatus.FAILED
            return NodeResult(
                node_name=self.name,
                status=self.status,
                error=str(e)
            )
    
    def get_next_nodes(self, state: WorkflowState) -> List[str]:
        """After evaluation, workflow is complete."""
        logger.info(f"   📋 EvaluatorNode.get_next_nodes() called")
        logger.info(f"   📍 Returning empty list (workflow complete)")
        return []


class WorkflowGraph:
    """Graph-based workflow executor for dashboard creation."""
    
    def __init__(self, hitl_approval_callback: Optional[Callable[[str], Awaitable[bool]]] = None, mcp_url: Optional[str] = None, mcp_api_key: Optional[str] = None):
        """
        Initialize the workflow graph.
        
        Args:
            hitl_approval_callback: Optional async callback for HITL approval (for testing)
        """
        # Create nodes
        self.nodes: Dict[str, WorkflowNode] = {
            "planner": PlannerNode(),
            "data_generator": DataGeneratorNode(),
            "risk_detector": RiskDetectorNode(),
            "hitl_pause": HITLPauseNode(approval_callback=hitl_approval_callback),
            "evaluator": EvaluatorNode()
        }
        
        # Define graph structure (edges)
        self.graph: Dict[str, List[str]] = {
            "planner": ["data_generator"],
            "data_generator": ["risk_detector"],
            "risk_detector": ["hitl_pause", "evaluator"],  # Conditional branching
            "hitl_pause": ["evaluator"],  # Only if approved
            "evaluator": []  # Terminal node
        }
        
        logger.info("WorkflowGraph initialized")

        # Initialize SupervisorAgent for tools
        from .supervisor import SupervisorAgent
        self.supervisor = SupervisorAgent(
            mcp_url=mcp_url,
            mcp_api_key=mcp_api_key
        )
    
    async def execute(self, company_name: str, company_id: Optional[str] = None) -> WorkflowState:
        """
        Execute the workflow for a company.
        
        Args:
            company_name: Name of the company
            company_id: Optional company ID
            
        Returns:
            WorkflowState with execution results
        """
        state = WorkflowState(company_name=company_name, company_id=company_id)
        state.status = WorkflowStatus.RUNNING
        
        logger.info(f"Starting workflow for {company_name}")
        
        # Start from planner node
        current_node_name = "planner"
        visited_nodes = set()
        
        try:
            while current_node_name:
                if current_node_name in visited_nodes:
                    logger.warning(f"Cycle detected: {current_node_name} already visited")
                    break
                
                visited_nodes.add(current_node_name)
                state.current_node = current_node_name
                
                # Execute current node
                logger.info(f"   🚀 Starting execution of node: {current_node_name}")
                node = self.nodes[current_node_name]
                logger.info(f"   📋 Calling node.execute() for {current_node_name}...")
                result = await node.execute(state)
                logger.info(f"   ✅ Node.execute() returned for {current_node_name}")
                state.node_results[current_node_name] = result

                logger.info(f"Node {current_node_name} completed with status {result.status}")

                # Check if node failed
                if result.status == NodeStatus.FAILED:
                    logger.error(f"   ❌ Node {current_node_name} failed with error: {result.error}")
                    state.status = WorkflowStatus.FAILED
                    state.completed_at = datetime.now()
                    return state

                # Determine next nodes
                logger.info(f"   🔄 Determining next nodes from {current_node_name}...")
                logger.info(f"   📋 Calling node.get_next_nodes() for {current_node_name}...")
                next_nodes = node.get_next_nodes(state)
                logger.info(f"   📍 Next nodes: {next_nodes}")

                # If no next nodes, workflow is complete
                if not next_nodes:
                    logger.info(f"   ✅ No next nodes - workflow complete")
                    break

                # Move to first next node (for now, we handle one path)
                # In a more complex system, we might execute multiple paths in parallel
                current_node_name = next_nodes[0] if next_nodes else None
                logger.info(f"   ➡️  Moving to next node: {current_node_name}")
                logger.info(f"   🔄 Continuing to next iteration of while loop...")
            
            # Workflow completed - set to COMPLETED if it was running or approved (approved means we continued after HITL)
            if state.status in [WorkflowStatus.RUNNING, WorkflowStatus.PAUSED_FOR_APPROVAL, WorkflowStatus.APPROVED]:
                state.status = WorkflowStatus.COMPLETED
            # Preserve REJECTED status if workflow was rejected
            state.completed_at = datetime.now()
            logger.info(f"Workflow completed for {company_name} with status {state.status}")
            
        except Exception as e:
            logger.error(f"Error in workflow execution: {e}", exc_info=True)
            state.status = WorkflowStatus.FAILED
            state.completed_at = datetime.now()
            
            # Increment failed metric
            try:
                from .metrics import increment_dashboard_failed
                increment_dashboard_failed(state.company_id)
            except Exception as e:
                logger.debug(f"Failed to increment failed metric: {e}")
        
        # Increment workflow completed metric
        try:
            from .metrics import increment_workflow_completed
            increment_workflow_completed()
        except Exception as e:
            logger.debug(f"Failed to increment workflow completed metric: {e}")
        
        return state
    
    def get_execution_path(self, state: WorkflowState) -> List[str]:
        """Get the execution path taken through the graph."""
        return list(state.node_results.keys())
    
    def visualize_graph(self) -> str:
        """Generate Mermaid diagram representation of the graph."""
        mermaid = """graph TD
    Start([Start]) --> Planner[Planner Node]
    Planner --> DataGen[Data Generator Node]
    DataGen --> RiskDet[Risk Detector Node]
    RiskDet -->|No Risk| Eval[Evaluator Node]
    RiskDet -->|Risk Detected| HITL[HITL Pause Node]
    HITL -->|Approved| Eval
    HITL -->|Rejected| EndReject([End: Rejected])
    Eval --> EndSuccess([End: Dashboard Complete])
    
    style Planner fill:#e1f5ff
    style DataGen fill:#e1f5ff
    style RiskDet fill:#fff4e1
    style HITL fill:#ffe1e1
    style Eval fill:#e1ffe1
"""
        return mermaid

