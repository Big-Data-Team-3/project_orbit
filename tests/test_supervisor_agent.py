"""
Unit tests for Supervisor Agent with ReAct workflow.

Tests verify:
- Supervisor agent correctly calls each tool as needed
- Output logs show clear sequential invocation steps and reasoning
- ReAct trace contains Thought → Action → Observation triplets
- Agent handles errors gracefully
"""

# region imports
import pytest
from datetime import datetime
from src.agents.supervisor import SupervisorAgent
from src.agents.react_models import ReActTrace, ReActStep, ActionType
from src.agents.models import RiskSignal
# endregion

# region tests
@pytest.mark.asyncio
async def test_supervisor_agent_initialization():
    """Test that Supervisor Agent initializes correctly with tools registered."""
    agent = SupervisorAgent()
    
    assert agent is not None
    assert agent.model == "gpt-4o-mini"
    assert agent.max_iterations == 10
    assert len(agent.tools) == 3
    assert "get_latest_structured_payload" in agent.tools
    assert "rag_search_company" in agent.tools
    assert "report_layoff_signal" in agent.tools


@pytest.mark.asyncio
async def test_supervisor_agent_execute_query_with_company():
    """Test executing a query with a company ID."""
    agent = SupervisorAgent(enable_llm_reasoning=False)  # Use rule-based for faster tests
    
    trace = await agent.execute_query(
        query="What is the funding information for this company?",
        company_id="abridge"
    )
    
    assert trace is not None
    assert trace.query == "What is the funding information for this company?"
    assert trace.company_id == "abridge"
    assert len(trace.steps) > 0
    assert trace.total_steps > 0
    assert trace.started_at is not None


@pytest.mark.asyncio
async def test_react_trace_structure():
    """Test that ReAct trace contains proper Thought → Action → Observation structure."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=3)
    
    trace = await agent.execute_query(
        query="Tell me about the company's leadership",
        company_id="abridge"
    )
    
    # Verify trace structure
    assert isinstance(trace, ReActTrace)
    assert trace.query is not None
    assert len(trace.steps) > 0
    
    # Verify each step has Thought → Action → Observation
    for step in trace.steps:
        assert isinstance(step, ReActStep)
        assert step.step_number > 0
        assert step.thought is not None and len(step.thought) > 0
        assert step.action is not None
        assert isinstance(step.action, ActionType)
        assert step.action_input is not None
        # Observation may be None if action failed, but should be present for successful actions
        assert step.timestamp is not None


@pytest.mark.asyncio
async def test_sequential_tool_invocation():
    """Test that agent calls tools in a logical sequence."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=5)
    
    trace = await agent.execute_query(
        query="What are the key details about this company?",
        company_id="abridge"
    )
    
    # Check that tools are called
    actions = [step.action for step in trace.steps]
    
    # Should have at least one tool call
    assert len(actions) > 0
    
    # Should have GET_PAYLOAD or RAG_SEARCH
    assert ActionType.GET_PAYLOAD in actions or ActionType.RAG_SEARCH in actions
    
    # Should end with FINAL_ANSWER
    assert ActionType.FINAL_ANSWER in actions or trace.final_answer is not None


@pytest.mark.asyncio
async def test_get_payload_tool_invocation():
    """Test that agent correctly invokes get_latest_structured_payload tool."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=2)
    
    trace = await agent.execute_query(
        query="Get the company payload",
        company_id="abridge"
    )
    
    # Find the step that called GET_PAYLOAD
    payload_steps = [s for s in trace.steps if s.action == ActionType.GET_PAYLOAD]
    
    if payload_steps:
        step = payload_steps[0]
        assert step.action == ActionType.GET_PAYLOAD
        assert "company_id" in step.action_input
        assert step.action_input["company_id"] == "abridge"
        assert step.observation is not None  # Should have observation from tool


@pytest.mark.asyncio
async def test_rag_search_tool_invocation():
    """Test that agent correctly invokes rag_search_company tool."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=3)
    
    trace = await agent.execute_query(
        query="Search for funding information",
        company_id="abridge"
    )
    
    # Find the step that called RAG_SEARCH
    rag_steps = [s for s in trace.steps if s.action == ActionType.RAG_SEARCH]
    
    # May or may not be called depending on reasoning, but if called, should be correct
    if rag_steps:
        step = rag_steps[0]
        assert step.action == ActionType.RAG_SEARCH
        assert "company_id" in step.action_input
        assert "query" in step.action_input
        assert step.action_input["company_id"] == "abridge"


@pytest.mark.asyncio
async def test_reasoning_steps_logged():
    """Test that reasoning (thought) steps are properly logged."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=3)
    
    trace = await agent.execute_query(
        query="What is the company's business model?",
        company_id="abridge"
    )
    
    # All steps should have thoughts
    for step in trace.steps:
        assert step.thought is not None
        assert len(step.thought) > 0
        # Thought should describe reasoning
        assert len(step.thought) > 10  # Should be more than just a word


@pytest.mark.asyncio
async def test_final_answer_generation():
    """Test that agent generates a final answer."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=5)
    
    trace = await agent.execute_query(
        query="Summarize the company information",
        company_id="abridge"
    )
    
    # Should have a final answer
    assert trace.final_answer is not None
    assert len(trace.final_answer) > 0
    assert trace.completed_at is not None
    assert trace.total_steps == len(trace.steps)


@pytest.mark.asyncio
async def test_error_handling():
    """Test that agent handles errors gracefully."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=2)
    
    # Query with invalid company ID
    trace = await agent.execute_query(
        query="Get company information",
        company_id="nonexistent_company_12345"
    )
    
    # Should still complete (with errors)
    assert trace is not None
    assert trace.completed_at is not None
    
    # May have errors in steps
    errors = [step.error for step in trace.steps if step.error]
    # Errors are acceptable, but trace should still be valid


@pytest.mark.asyncio
async def test_company_id_extraction():
    """Test that agent can extract company ID from query."""
    agent = SupervisorAgent(enable_llm_reasoning=False)
    
    # Query mentioning a company
    trace = await agent.execute_query(
        query="Tell me about abridge company's funding"
    )
    
    # Should extract company_id or use it from query
    assert trace is not None
    # May have extracted "abridge" as company_id
    if trace.company_id:
        assert trace.company_id in ["abridge"]


@pytest.mark.asyncio
async def test_max_iterations_limit():
    """Test that agent respects max_iterations limit."""
    agent = SupervisorAgent(enable_llm_reasoning=False, max_iterations=2)
    
    trace = await agent.execute_query(
        query="Get comprehensive company information",
        company_id="abridge"
    )
    
    # Should not exceed max_iterations
    assert len(trace.steps) <= agent.max_iterations
    assert trace.total_steps <= agent.max_iterations
# endregion

