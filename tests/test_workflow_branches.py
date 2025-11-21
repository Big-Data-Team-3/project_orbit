"""
Test workflow branches - risk vs no-risk logic.

This module tests the conditional branching in the workflow graph:
- Standard path (no risk detected) → planner → data_generator → risk_detector → evaluator
- Risk path (risk detected) → planner → data_generator → risk_detector → hitl_pause → evaluator

Run: pytest -v --maxfail=1 --disable-warnings
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime

# Import modules to patch
import src.rag_pipeline
import src.risk_detection

from src.agents.workflow import (
    WorkflowGraph,
    WorkflowState,
    NodeStatus,
    WorkflowStatus
)


class TestWorkflowBranchesStandard:
    """Test standard workflow branch (no risk detected)."""
    
    @pytest.mark.asyncio
    async def test_standard_path_no_risk_branch(self):
        """Assert that standard path skips HITL when no risk is detected."""
        workflow = WorkflowGraph()
        
        # Mock no risks detected
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen, \
             patch.object(src.risk_detection, 'detect_risk_signals', return_value=[]), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            mock_gen.return_value = """## Company Overview
Test Company
## Business Model and GTM
Test
## Funding & Investor Profile
Test
## Growth Momentum
Test
## Visibility & Market Sentiment
Test
## Risks and Challenges
Test
## Outlook
Test
## Disclosure Gaps
Test"""
            
            state = await workflow.execute("TestCompany")
            
            # Assert: Standard path taken (no HITL)
            execution_path = workflow.get_execution_path(state)
            assert "hitl_pause" not in execution_path, "HITL should not be triggered when no risk detected"
            assert "evaluator" in execution_path, "Evaluator should be reached in standard path"
            
            # Assert: Risk detector correctly identified no risk
            assert state.risk_detected is False
            assert len(state.risk_signals) == 0
            
            # Assert: Workflow completed successfully
            assert state.status == WorkflowStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_standard_path_node_order(self):
        """Assert correct node order in standard path."""
        workflow = WorkflowGraph()
        
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen, \
             patch.object(src.risk_detection, 'detect_risk_signals', return_value=[]), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            mock_gen.return_value = "## Company Overview\nTest\n## Business Model\nTest\n## Funding\nTest\n## Growth\nTest\n## Visibility\nTest\n## Risks\nTest\n## Outlook\nTest\n## Disclosure\nTest"
            
            state = await workflow.execute("TestCompany")
            execution_path = workflow.get_execution_path(state)
            
            # Assert: Correct order without HITL
            assert execution_path == ["planner", "data_generator", "risk_detector", "evaluator"]


class TestWorkflowBranchesRisk:
    """Test risk workflow branch (risk detected, HITL triggered)."""
    
    @pytest.mark.asyncio
    async def test_risk_path_with_hitl_branch(self):
        """Assert that risk path includes HITL when risk is detected."""
        async def approval_callback(approval_id: str) -> bool:
            return True
        
        workflow = WorkflowGraph(hitl_approval_callback=approval_callback)
        
        # Mock risks detected
        mock_risks = [
            {
                "risk_type": "layoff",
                "keyword": "layoff",
                "context": "Company announces layoff",
                "severity": "high"
            }
        ]
        
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen, \
             patch.object(src.risk_detection, 'detect_risk_signals', return_value=mock_risks), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            mock_gen.return_value = """## Company Overview
Test Company
## Business Model and GTM
Test
## Funding & Investor Profile
Test
## Growth Momentum
Test
## Visibility & Market Sentiment
Test
## Risks and Challenges
Company announces layoff
## Outlook
Test
## Disclosure Gaps
Test"""
            
            state = await workflow.execute("TestCompany")
            
            # Assert: Risk path taken (includes HITL)
            execution_path = workflow.get_execution_path(state)
            assert "hitl_pause" in execution_path, "HITL should be triggered when risk detected"
            assert "evaluator" in execution_path, "Evaluator should be reached after HITL approval"
            
            # Assert: Risk detector correctly identified risk
            assert state.risk_detected is True
            assert len(state.risk_signals) > 0
            assert state.hitl_approved is True
            
            # Assert: Workflow completed successfully after approval
            assert state.status == WorkflowStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_risk_path_rejected_branch(self):
        """Assert that risk path stops when HITL is rejected."""
        async def approval_callback(approval_id: str) -> bool:
            return False  # Reject
        
        workflow = WorkflowGraph(hitl_approval_callback=approval_callback)
        
        mock_risks = [
            {
                "risk_type": "layoff",
                "keyword": "layoff",
                "context": "Company announces layoff",
                "severity": "high"
            }
        ]
        
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen, \
             patch.object(src.risk_detection, 'detect_risk_signals', return_value=mock_risks), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            mock_gen.return_value = "## Company Overview\nTest\n## Business Model\nTest\n## Funding\nTest\n## Growth\nTest\n## Visibility\nTest\n## Risks\nLayoff\n## Outlook\nTest\n## Disclosure\nTest"
            
            state = await workflow.execute("TestCompany")
            
            # Assert: Risk path taken but stopped at HITL rejection
            execution_path = workflow.get_execution_path(state)
            assert "hitl_pause" in execution_path, "HITL should be triggered"
            assert "evaluator" not in execution_path, "Evaluator should not be reached if HITL rejected"
            
            # Assert: Workflow rejected
            assert state.status == WorkflowStatus.REJECTED
            assert state.hitl_approved is False
    
    @pytest.mark.asyncio
    async def test_risk_path_node_order(self):
        """Assert correct node order in risk path."""
        async def approval_callback(approval_id: str) -> bool:
            return True
        
        workflow = WorkflowGraph(hitl_approval_callback=approval_callback)
        
        mock_risks = [{"risk_type": "layoff", "keyword": "layoff", "context": "Test", "severity": "high"}]
        
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen, \
             patch.object(src.risk_detection, 'detect_risk_signals', return_value=mock_risks), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            mock_gen.return_value = "## Company Overview\nTest\n## Business Model\nTest\n## Funding\nTest\n## Growth\nTest\n## Visibility\nTest\n## Risks\nTest\n## Outlook\nTest\n## Disclosure\nTest"
            
            state = await workflow.execute("TestCompany")
            execution_path = workflow.get_execution_path(state)
            
            # Assert: Correct order with HITL
            assert execution_path == ["planner", "data_generator", "risk_detector", "hitl_pause", "evaluator"]


class TestWorkflowBranchesConditional:
    """Test conditional branching logic."""
    
    @pytest.mark.asyncio
    async def test_risk_detector_branching_logic(self):
        """Assert risk detector correctly branches based on risk detection."""
        from src.agents.workflow import RiskDetectorNode
        
        # Test no risk branch
        node = RiskDetectorNode()
        state = WorkflowState(company_name="TestCompany", company_id="testcompany")
        state.dashboard = "Normal dashboard content"
        
        with patch.object(src.risk_detection, 'detect_risk_signals', return_value=[]), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            await node.execute(state)
            next_nodes = node.get_next_nodes(state)
            
            # Assert: No risk → goes to evaluator
            assert "evaluator" in next_nodes
            assert "hitl_pause" not in next_nodes
        
        # Test risk branch
        state2 = WorkflowState(company_name="TestCompany", company_id="testcompany")
        state2.dashboard = "Company announces layoff"
        mock_risks = [{"risk_type": "layoff", "severity": "high"}]
        
        with patch.object(src.risk_detection, 'detect_risk_signals', return_value=mock_risks), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            await node.execute(state2)
            next_nodes = node.get_next_nodes(state2)
            
            # Assert: Risk detected → goes to HITL
            assert "hitl_pause" in next_nodes
            assert "evaluator" not in next_nodes


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--maxfail=1", "--disable-warnings"])