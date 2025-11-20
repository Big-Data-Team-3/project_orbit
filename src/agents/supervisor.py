"""
Due Diligence Supervisor Agent with ReAct (Reasoning + Acting) workflow.

This module implements a Supervisor Agent that can:
- Manage dashboard logic and queries
- Invoke core agent tools in a structured ReAct workflow
- Log Thought → Action → Observation triplets for audit and debugging
- Execute queries for companies and return structured responses

NOW USES MCP SERVER FOR ALL TOOL CALLS INSTEAD OF DIRECT IMPORTS
"""

# region imports
import logging
import os
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Awaitable, Tuple
from enum import Enum

import dotenv
from openai import OpenAI

# REMOVE DIRECT TOOL IMPORTS - Now using MCP client
# from .tools import (
#     get_latest_structured_payload,
#     rag_search_company,
#     report_layoff_signal,
# )

from .models import (
    PayloadResponse,
    RAGSearchResponse,
    RiskSignal,
    SignalReportResponse,
)
from .react_models import ReActStep, ReActTrace, ActionType
from .cloud_logging import log_react_trace_to_cloud, log_react_step_to_cloud
from .mcp_client import MCPClient  # ADD THIS IMPORT
# endregion

# region globals, environment variables, and logging
dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# OpenAI client initialization
_openai_client: Optional[OpenAI] = None

def _get_openai_client() -> OpenAI:
    """Get or initialize OpenAI client."""
    global _openai_client
    if _openai_client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")
        _openai_client = OpenAI(api_key=api_key)
    return _openai_client
# endregion

class SupervisorAgent:
    """
    Due Diligence Supervisor Agent with ReAct workflow.
    
    This agent manages dashboard queries and invokes tools in a structured
    reasoning loop, logging each step for transparency and debugging.
    
    NOW ROUTES ALL TOOL CALLS THROUGH MCP SERVER
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        max_iterations: int = 10,
        enable_llm_reasoning: bool = True,
        mcp_url: str = None,
        mcp_api_key: str = None
    ):
        """
        Initialize the Supervisor Agent.
        
        Args:
            model: OpenAI model to use for reasoning (default: "gpt-4o-mini")
            max_iterations: Maximum number of ReAct steps before stopping
            enable_llm_reasoning: Whether to use LLM for thought generation
            mcp_url: MCP server URL (default: from env MCP_BASE)
            mcp_api_key: MCP API key (default: from env MCP_API_KEY)
        """
        self.model = model
        self.max_iterations = max_iterations
        self.enable_llm_reasoning = enable_llm_reasoning
        
        # Initialize MCP client instead of direct tool registry
        self.mcp_client = MCPClient(base_url=mcp_url, api_key=mcp_api_key)
        
        # Tool registry now maps to MCP client methods
        self.tools: Dict[str, Callable[..., Awaitable[Any]]] = {
            "get_latest_structured_payload": self.mcp_client.get_latest_structured_payload,
            "rag_search_company": self.mcp_client.rag_search_company,
            "report_layoff_signal": self.mcp_client.report_layoff_signal,
        }
        
        logger.info(f"SupervisorAgent initialized with model={model}, max_iterations={max_iterations}")
        logger.info(f"MCP integration enabled: {self.mcp_client.base_url}")
    
    async def execute_query(
        self,
        query: str,
        company_id: Optional[str] = None
    ) -> ReActTrace:
        """
        Execute a query using ReAct workflow.
        
        This method implements the core ReAct loop:
        1. Think about what information is needed
        2. Act by calling appropriate tools
        3. Observe the results
        4. Repeat until sufficient information is gathered
        5. Generate final answer
        
        Args:
            query: The query or question to answer
            company_id: Optional company ID if query is company-specific
            
        Returns:
            ReActTrace: Complete trace of the workflow execution
        """
        trace = ReActTrace(
            query=query,
            company_id=company_id,
            started_at=datetime.now()
        )
        
        logger.info(f"Starting ReAct workflow for query: '{query}' (company_id={company_id})")
        
        # Extract company_id from query if not provided
        if not company_id:
            company_id = self._extract_company_id(query)
        
        # Context accumulated during the workflow
        context: List[str] = []
        step_number = 0
        
        try:
            for iteration in range(self.max_iterations):
                step_number += 1
                
                # Step 1: THOUGHT - Reason about what to do next
                thought = await self._think(query, context, trace.steps)
                
                # Step 2: ACTION - Decide which tool to call
                action_type, action_input = await self._decide_action(
                    thought, query, company_id, context, trace.steps
                )
                
                # Step 3: OBSERVATION - Execute action and observe results
                observation, error = await self._act_and_observe(
                    action_type, action_input
                )
                
                # Create ReAct step
                step = ReActStep(
                    step_number=step_number,
                    thought=thought,
                    action=action_type,
                    action_input=action_input,
                    observation=observation,
                    error=error,
                    timestamp=datetime.now()
                )
                
                trace.steps.append(step)
                logger.info(f"Step {step_number}: {action_type.value} - {thought[:100]}...")
                
                # Log step to Cloud Logging (if enabled)
                try:
                    log_react_step_to_cloud(
                        step=step,
                        company_id=company_id,
                        query=query,
                        severity="INFO" if not error else "WARNING"
                    )
                except Exception as e:
                    logger.debug(f"Failed to log step to Cloud Logging: {e}")
                
                # Update context with observation
                if observation:
                    context.append(f"Step {step_number}: {observation}")
                
                # Check if we have enough information to answer
                if action_type == ActionType.FINAL_ANSWER:
                    trace.final_answer = observation
                    break
                
                # Check if we should stop (e.g., no more useful actions)
                if self._should_stop(action_type, observation, context):
                    trace.final_answer = await self._generate_final_answer(query, context)
                    break
            
            # Generate final answer if not already generated
            if not trace.final_answer:
                trace.final_answer = await self._generate_final_answer(query, context)
            
            trace.completed_at = datetime.now()
            trace.total_steps = len(trace.steps)
            trace.success = True
            
            logger.info(f"ReAct workflow completed: {trace.total_steps} steps, success={trace.success}")
            
            # Log complete trace to Cloud Logging (if enabled)
            try:
                log_react_trace_to_cloud(trace, severity="INFO")
            except Exception as e:
                logger.debug(f"Failed to log trace to Cloud Logging: {e}")
            
        except Exception as e:
            logger.error(f"Error in ReAct workflow: {e}", exc_info=True)
            trace.completed_at = datetime.now()
            trace.total_steps = len(trace.steps)
            trace.success = False
            trace.final_answer = f"Error: {str(e)}"
            
            # Log failed trace to Cloud Logging (if enabled)
            try:
                log_react_trace_to_cloud(trace, severity="ERROR")
            except Exception as log_error:
                logger.debug(f"Failed to log error trace to Cloud Logging: {log_error}")
        
        return trace
    
    async def _think(
        self,
        query: str,
        context: List[str],
        previous_steps: List[ReActStep]
    ) -> str:
        """
        Generate a thought about what to do next.
        
        Args:
            query: Original query
            context: Accumulated context from previous steps
            previous_steps: Previous ReAct steps
            
        Returns:
            Thought string describing what to do next
        """
        if self.enable_llm_reasoning:
            try:
                client = _get_openai_client()
                
                # Build context summary
                context_summary = "\n".join(context[-5:]) if context else "No context yet."
                steps_summary = "\n".join([
                    f"Step {s.step_number}: {s.action.value} - {s.thought[:100]}"
                    for s in previous_steps[-3:]
                ]) if previous_steps else "No previous steps."
                
                prompt = f"""You are a Due Diligence Supervisor Agent analyzing a company.

        Query: {query}

        Previous steps:
        {steps_summary}

        Recent context:
        {context_summary}

        What should I do next? Think step by step about what information is needed to answer the query.
        Be specific about which tool to use and why.

        Available tools:
        1. get_latest_structured_payload - Get structured company data (needs company_id)
        2. rag_search_company - Search company knowledge base (needs company_id and query)
        3. report_layoff_signal - Report a risk signal (needs RiskSignal data)

        Your thought (be concise, 1-2 sentences):"""
                
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that reasons about data retrieval tasks."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=200
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.warning(f"LLM reasoning failed: {e}, using rule-based reasoning")
                return self._rule_based_think(query, context, previous_steps)
        else:
            return self._rule_based_think(query, context, previous_steps)
    
    def _rule_based_think(
        self,
        query: str,
        context: List[str],
        previous_steps: List[ReActStep]
    ) -> str:
        """Rule-based thought generation when LLM is not available."""
        # Check what we've already done
        actions_taken = [step.action for step in previous_steps]
        
        if ActionType.GET_PAYLOAD not in actions_taken:
            return "I need to get the structured payload for the company to understand its basic information."
        elif ActionType.RAG_SEARCH not in actions_taken:
            return "I should search the knowledge base for more detailed information about the query."
        else:
            return "I have enough information to provide a final answer."
    
    async def _decide_action(
        self,
        thought: str,
        query: str,
        company_id: Optional[str],
        context: List[str],
        previous_steps: List[ReActStep]
    ) -> Tuple[ActionType, Dict[str, Any]]:
        """
        Decide which action to take based on thought and context.
        
        Returns:
            Tuple of (ActionType, action_input_dict)
        """
        thought_lower = thought.lower()
        actions_taken = [step.action for step in previous_steps]
        
        # Check if we should get payload
        if ActionType.GET_PAYLOAD not in actions_taken and company_id:
            if "payload" in thought_lower or "structured" in thought_lower or "basic" in thought_lower:
                return ActionType.GET_PAYLOAD, {"company_id": company_id}
        
        # Check if we should do RAG search
        if ActionType.RAG_SEARCH not in actions_taken and company_id:
            if "search" in thought_lower or "knowledge" in thought_lower or "rag" in thought_lower:
                return ActionType.RAG_SEARCH, {
                    "company_id": company_id,
                    "query": query,
                    "top_k": 10
                }
        
        # Check if we should report a signal (if query suggests risk)
        risk_keywords = ["layoff", "breach", "risk", "security", "regulatory", "issue"]
        if any(keyword in query.lower() for keyword in risk_keywords) and company_id:
            if "report" in thought_lower or "signal" in thought_lower:
                return ActionType.REPORT_SIGNAL, {
                    "signal_data": RiskSignal(
                        company_id=company_id,
                        event_type="other",
                        description=f"Risk detected from query: {query}",
                        severity="medium",
                        detected_at=datetime.now()
                    )
                }
        
        # If we've gathered enough info, provide final answer
        if len(previous_steps) >= 2:
            return ActionType.FINAL_ANSWER, {}
        
        # Default: try to get payload if we have company_id
        if company_id and ActionType.GET_PAYLOAD not in actions_taken:
            return ActionType.GET_PAYLOAD, {"company_id": company_id}
        
        # Otherwise, final answer
        return ActionType.FINAL_ANSWER, {}
    
    async def _act_and_observe(
        self,
        action_type: ActionType,
        action_input: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Execute an action and return the observation.
        
        Returns:
            Tuple of (observation_string, error_string)
        """
        try:
            if action_type == ActionType.GET_PAYLOAD:
                company_id = action_input["company_id"]
                result: PayloadResponse = await self.mcp_client.get_latest_structured_payload(company_id)
                
                if result.found and result.payload:
                    if result.payload.company_record:
                        company_name = (
                            result.payload.company_record.brand_name 
                            or result.payload.company_record.legal_name 
                            or 'N/A'
                        )
                    else:
                        company_name = 'N/A'
                    return (
                        f"Retrieved structured payload for {company_id}. "
                        f"Company: {company_name}. "
                        f"Source: {result.source}.",
                        None
                    )
                else:
                    return (
                        f"Payload not found for {company_id}. Error: {result.error}",
                        result.error
                    )
            
            elif action_type == ActionType.RAG_SEARCH:
                company_id = action_input["company_id"]
                query = action_input["query"]
                top_k = action_input.get("top_k", 10)
                
                result: RAGSearchResponse = await self.mcp_client.rag_search_company(
                    company_id, query, top_k
                )
                
                if result.total_results > 0:
                    top_results = result.results[:3]
                    summaries = [f"[{r.score:.2f}] {r.text[:100]}..." for r in top_results]
                    return (
                        f"Found {result.total_results} results. Top results: {'; '.join(summaries)}",
                        None
                    )
                else:
                    return (
                        f"No results found for query '{query}'. Error: {result.error}",
                        result.error
                    )
            
            elif action_type == ActionType.REPORT_SIGNAL:
                signal_data: RiskSignal = action_input["signal_data"]
                result: SignalReportResponse = await self.mcp_client.report_layoff_signal(signal_data)
                
                return (
                    f"Risk signal reported. ID: {result.signal_id}, Status: {result.status}, "
                    f"Message: {result.message}",
                    result.error
                )
            
            elif action_type == ActionType.FINAL_ANSWER:
                return "Ready to provide final answer.", None
            
            else:
                return None, f"Unknown action type: {action_type}"
                
        except Exception as e:
            logger.error(f"Error executing action {action_type}: {e}", exc_info=True)
            return None, str(e)
    
    def _should_stop(
        self,
        action_type: ActionType,
        observation: Optional[str],
        context: List[str]
    ) -> bool:
        """Determine if we should stop the ReAct loop."""
        if action_type == ActionType.FINAL_ANSWER:
            return True
        
        # Stop if we've gathered enough context
        if len(context) >= 3:
            return True
        
        # Stop if last action failed critically
        if observation and "error" in observation.lower() and "not found" not in observation.lower():
            return True
        
        return False
    
    async def _generate_final_answer(
        self,
        query: str,
        context: List[str]
    ) -> str:
        """Generate final answer from accumulated context."""
        if not context:
            return "Unable to gather sufficient information to answer the query."
        
        context_summary = "\n".join(context)
        
        if self.enable_llm_reasoning:
            try:
                client = _get_openai_client()
                
                prompt = f"""Based on the following information gathered, provide a concise answer to the query.

        Query: {query}

        Information gathered:
        {context_summary}

        Provide a clear, concise answer:"""
                
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant that synthesizes information."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=500
                )
                
                return response.choices[0].message.content.strip()
                
            except Exception as e:
                logger.warning(f"LLM final answer generation failed: {e}")
                return f"Based on gathered information: {context_summary[:500]}"
        else:
            return f"Based on gathered information: {context_summary[:500]}"
    
    def _extract_company_id(self, query: str) -> Optional[str]:
        """Extract company ID from query if mentioned."""
        # Simple extraction - look for common company IDs
        common_companies = ["abridge", "anthropic", "openai", "cohere", "mistral"]
        query_lower = query.lower()
        
        for company in common_companies:
            if company in query_lower:
                return company
        
        return None

