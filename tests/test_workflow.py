"""
Unit tests for graph-based workflow (Lab 17).

Tests both standard (no-risk) and risk (with HITL) branching paths.
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime
from pathlib import Path
import json
import tempfile
import shutil
import sys

# Mock services before importing modules that depend on it
sys.modules['services'] = MagicMock()
sys.modules['services.embeddings'] = MagicMock()

# Import modules to patch
import src.rag_pipeline
import src.risk_detection

from src.agents.workflow import (
    WorkflowGraph,
    WorkflowState,
    NodeStatus,
    WorkflowStatus,
    PlannerNode,
    DataGeneratorNode,
    RiskDetectorNode,
    HITLPauseNode,
    EvaluatorNode
)


class TestWorkflowNodes:
    """Test individual workflow nodes."""
    
    @pytest.mark.asyncio
    async def test_planner_node(self):
        """Test Planner node execution."""
        node = PlannerNode()
        state = WorkflowState(company_name="TestCompany")
        
        result = await node.execute(state)
        
        assert result.status == NodeStatus.COMPLETED
        assert result.output is not None
        assert "company_name" in result.output
        assert "strategy" in result.output
        assert state.company_id is not None
    
    @pytest.mark.asyncio
    async def test_data_generator_node(self):
        """Test Data Generator node execution."""
        node = DataGeneratorNode()
        state = WorkflowState(company_name="anthropic")
        
        # Mock the generate_dashboard function at its source
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen:
            mock_gen.return_value = "## Company Overview\nTest content\n## Business Model\nTest"
            result = await node.execute(state)
            
            assert result.status == NodeStatus.COMPLETED
            assert result.output is not None
            assert "dashboard" in result.output
            assert state.dashboard is not None
    
    @pytest.mark.asyncio
    async def test_risk_detector_node_no_risk(self):
        """Test Risk Detector node with no risks."""
        node = RiskDetectorNode()
        state = WorkflowState(company_name="TestCompany", company_id="testcompany")
        state.dashboard = "This is a normal dashboard with no risks."
        
        # Mock risk detection to return no risks
        with patch.object(src.risk_detection, 'detect_risk_signals', return_value=[]), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            result = await node.execute(state)
            
            assert result.status == NodeStatus.COMPLETED
            assert result.output["risk_detected"] is False
            assert result.output["risk_count"] == 0
            assert state.risk_detected is False
    
    @pytest.mark.asyncio
    async def test_risk_detector_node_with_risk(self):
        """Test Risk Detector node with risks detected."""
        node = RiskDetectorNode()
        state = WorkflowState(company_name="TestCompany", company_id="testcompany")
        state.dashboard = "Company announces layoff of 10% workforce."
        
        # Mock risk detection to return risks
        mock_risks = [
            {
                "risk_type": "layoff",
                "keyword": "layoff",
                "context": "Company announces layoff of 10% workforce",
                "severity": "high"
            }
        ]
        
        with patch.object(src.risk_detection, 'detect_risk_signals', return_value=mock_risks), \
             patch.object(src.risk_detection, 'search_risks_in_company', return_value=[]), \
             patch.object(src.rag_pipeline, 'retrieve_context', return_value=[]):
            
            result = await node.execute(state)
            
            assert result.status == NodeStatus.COMPLETED
            assert result.output["risk_detected"] is True
            assert result.output["risk_count"] > 0
            assert state.risk_detected is True
            assert len(state.risk_signals) > 0
    
    @pytest.mark.asyncio
    async def test_hitl_pause_node_approved(self):
        """Test HITL Pause node with approval."""
        async def approval_callback(approval_id: str) -> bool:
            return True
        
        node = HITLPauseNode(approval_callback=approval_callback)
        state = WorkflowState(company_name="TestCompany")
        state.risk_detected = True
        state.risk_signals = [{"risk_type": "layoff", "severity": "high"}]
        state.dashboard = "Test dashboard"
        
        result = await node.execute(state)
        
        assert result.status == NodeStatus.COMPLETED
        assert result.output["approved"] is True
        assert state.hitl_approved is True
        assert state.status == WorkflowStatus.APPROVED
    
    @pytest.mark.asyncio
    async def test_hitl_pause_node_rejected(self):
        """Test HITL Pause node with rejection."""
        async def approval_callback(approval_id: str) -> bool:
            return False
        
        node = HITLPauseNode(approval_callback=approval_callback)
        state = WorkflowState(company_name="TestCompany")
        state.risk_detected = True
        state.risk_signals = [{"risk_type": "layoff", "severity": "high"}]
        state.dashboard = "Test dashboard"
        
        result = await node.execute(state)
        
        assert result.status == NodeStatus.COMPLETED
        assert result.output["approved"] is False
        assert state.hitl_approved is False
        assert state.status == WorkflowStatus.REJECTED
    
    @pytest.mark.asyncio
    async def test_evaluator_node(self):
        """Test Evaluator node."""
        node = EvaluatorNode()
        state = WorkflowState(company_name="TestCompany")
        state.dashboard = """## Company Overview
Test
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
        
        result = await node.execute(state)
        
        assert result.status == NodeStatus.COMPLETED
        assert result.output["dashboard_complete"] is True
        assert len(result.output["missing_sections"]) == 0


class TestWorkflowGraphStandardPath:
    """Test workflow graph execution - Standard path (no risk)."""
    
    @pytest.mark.asyncio
    async def test_standard_path_execution(self):
        """Test complete workflow execution with no risks (standard path)."""
        workflow = WorkflowGraph()
        
        # Mock all external dependencies
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
            
            # Verify workflow completed successfully
            assert state.status == WorkflowStatus.COMPLETED
            assert state.dashboard is not None
            assert state.risk_detected is False
            
            # Verify execution path (should skip HITL)
            execution_path = workflow.get_execution_path(state)
            assert "planner" in execution_path
            assert "data_generator" in execution_path
            assert "risk_detector" in execution_path
            assert "evaluator" in execution_path
            assert "hitl_pause" not in execution_path  # Should skip HITL
            
            # Verify all nodes completed successfully
            for node_name in execution_path:
                assert state.node_results[node_name].status == NodeStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_standard_path_node_order(self):
        """Test that standard path follows correct node order."""
        workflow = WorkflowGraph()
        
        with patch('src.rag_pipeline.generate_dashboard') as mock_gen, \
             patch('src.risk_detection.detect_risk_signals', return_value=[]), \
             patch('src.risk_detection.search_risks_in_company', return_value=[]), \
             patch('src.rag_pipeline.retrieve_context', return_value=[]):
            
            mock_gen.return_value = "## Company Overview\nTest\n## Business Model\nTest\n## Funding\nTest\n## Growth\nTest\n## Visibility\nTest\n## Risks\nTest\n## Outlook\nTest\n## Disclosure\nTest"
            
            state = await workflow.execute("TestCompany")
            
            execution_path = workflow.get_execution_path(state)
            
            # Verify order: planner -> data_generator -> risk_detector -> evaluator
            assert execution_path[0] == "planner"
            assert execution_path[1] == "data_generator"
            assert execution_path[2] == "risk_detector"
            assert execution_path[3] == "evaluator"


class TestWorkflowGraphRiskPath:
    """Test workflow graph execution - Risk path (with HITL)."""
    
    @pytest.mark.asyncio
    async def test_risk_path_execution(self):
        """Test complete workflow execution with risks detected (risk path with HITL)."""
        # Approval callback that approves
        async def approval_callback(approval_id: str) -> bool:
            return True
        
        workflow = WorkflowGraph(hitl_approval_callback=approval_callback)
        
        # Mock risk detection to return risks
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
            
            # Verify workflow completed successfully
            assert state.status == WorkflowStatus.COMPLETED
            assert state.dashboard is not None
            assert state.risk_detected is True
            assert len(state.risk_signals) > 0
            assert state.hitl_approved is True
            
            # Verify execution path (should include HITL)
            execution_path = workflow.get_execution_path(state)
            assert "planner" in execution_path
            assert "data_generator" in execution_path
            assert "risk_detector" in execution_path
            assert "hitl_pause" in execution_path  # Should include HITL
            assert "evaluator" in execution_path
            
            # Verify HITL node was executed
            hitl_result = state.node_results.get("hitl_pause")
            assert hitl_result is not None
            assert hitl_result.status == NodeStatus.COMPLETED
            assert hitl_result.output["approved"] is True
    
    @pytest.mark.asyncio
    async def test_risk_path_rejected(self):
        """Test workflow execution when HITL approval is rejected."""
        # Approval callback that rejects
        async def approval_callback(approval_id: str) -> bool:
            return False
        
        workflow = WorkflowGraph(hitl_approval_callback=approval_callback)
        
        # Mock risk detection to return risks
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
            
            mock_gen.return_value = "## Company Overview\nTest\n## Business Model\nTest\n## Funding\nTest\n## Growth\nTest\n## Visibility\nTest\n## Risks\nLayoff announced\n## Outlook\nTest\n## Disclosure\nTest"
            
            state = await workflow.execute("TestCompany")
            
            # Verify workflow was rejected
            assert state.status == WorkflowStatus.REJECTED
            assert state.risk_detected is True
            assert state.hitl_approved is False
            
            # Verify execution path (should include HITL but not evaluator)
            execution_path = workflow.get_execution_path(state)
            assert "hitl_pause" in execution_path
            assert "evaluator" not in execution_path  # Should not reach evaluator if rejected
    
    @pytest.mark.asyncio
    async def test_risk_path_node_order(self):
        """Test that risk path follows correct node order."""
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
            
            # Verify order: planner -> data_generator -> risk_detector -> hitl_pause -> evaluator
            assert execution_path[0] == "planner"
            assert execution_path[1] == "data_generator"
            assert execution_path[2] == "risk_detector"
            assert execution_path[3] == "hitl_pause"
            assert execution_path[4] == "evaluator"


class TestWorkflowGraphVisualization:
    """Test workflow graph visualization."""
    
    def test_visualize_graph(self):
        """Test that graph visualization generates valid Mermaid diagram."""
        workflow = WorkflowGraph()
        diagram = workflow.visualize_graph()
        
        assert "graph TD" in diagram
        assert "Planner" in diagram
        assert "Data Generator" in diagram
        assert "Risk Detector" in diagram
        assert "HITL" in diagram
        assert "Evaluator" in diagram
        assert "No Risk" in diagram or "risk" in diagram.lower()
        assert "Risk Detected" in diagram or "risk" in diagram.lower()


class TestWorkflowErrorHandling:
    """Test error handling in workflow."""
    
    @pytest.mark.asyncio
    async def test_node_failure_handling(self):
        """Test that workflow handles node failures gracefully."""
        workflow = WorkflowGraph()
        
        # Mock data generator to fail
        with patch.object(src.rag_pipeline, 'generate_dashboard') as mock_gen:
            mock_gen.side_effect = Exception("Dashboard generation failed")
            
            state = await workflow.execute("TestCompany")
            
            # Workflow should fail
            assert state.status == WorkflowStatus.FAILED
            
            # Should have executed planner
            assert "planner" in state.node_results
            assert state.node_results["planner"].status == NodeStatus.COMPLETED
            
            # Data generator should have failed
            assert "data_generator" in state.node_results
            assert state.node_results["data_generator"].status == NodeStatus.FAILED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

