"""
Agent Service - FastAPI wrapper for SupervisorAgent

This service exposes the SupervisorAgent as a standalone HTTP service.
Main FastAPI service calls this service via HTTP instead of direct instantiation.
"""

import logging
import os
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import dotenv
from src.agents.supervisor import SupervisorAgent
from src.agents.react_models import ReActTrace

dotenv.load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Initialize FastAPI app
app = FastAPI(
    title="Project Orbit Agent Service",
    description="Standalone Agent Service for SupervisorAgent",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


class AgentExecuteRequest(BaseModel):
    """Request model for agent execution"""
    query: str = Field(..., description="Query or question to execute")
    company_id: Optional[str] = Field(None, description="Optional company ID if query is company-specific")


class AgentExecuteResponse(BaseModel):
    """Response model for agent execution"""
    query: str
    company_id: Optional[str]
    final_answer: Optional[str]
    success: bool
    total_steps: int
    started_at: str
    completed_at: Optional[str]
    steps: list


@app.post("/execute", tags=["Agent"], response_model=AgentExecuteResponse)
async def execute_agent(request: AgentExecuteRequest):
    """
    Execute a query using SupervisorAgent with ReAct workflow.
    
    This endpoint:
    1. Initializes SupervisorAgent
    2. Executes the query using ReAct workflow
    3. Returns the complete trace as JSON
    
    Args:
        request: Agent execution request with query and optional company_id
    
    Returns:
        Agent execution response with ReAct trace
    """
    try:
        logger.info(f"Agent execution request received: query='{request.query}', company_id='{request.company_id}'")
        
        # Initialize Supervisor Agent
        agent = SupervisorAgent(
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
            max_iterations=10,
            enable_llm_reasoning=True,
            mcp_url=os.getenv("MCP_BASE", "http://localhost:8001"),
            mcp_api_key=os.getenv("MCP_API_KEY", "dev-key")
        )
        
        # Execute query
        agent_trace_obj = await agent.execute_query(request.query, request.company_id)
        
        # Convert ReActTrace to dict for response
        response = AgentExecuteResponse(
            query=agent_trace_obj.query,
            company_id=agent_trace_obj.company_id,
            final_answer=agent_trace_obj.final_answer,
            success=agent_trace_obj.success,
            total_steps=agent_trace_obj.total_steps,
            started_at=agent_trace_obj.started_at.isoformat(),
            completed_at=agent_trace_obj.completed_at.isoformat() if agent_trace_obj.completed_at else None,
            steps=[
                {
                    "step_number": step.step_number,
                    "thought": step.thought,
                    "action": step.action.value,
                    "action_input": step.action_input,
                    "observation": step.observation,
                    "error": step.error,
                    "timestamp": step.timestamp.isoformat()
                }
                for step in agent_trace_obj.steps
            ]
        )
        
        logger.info(f"Agent execution completed: {agent_trace_obj.total_steps} steps, success={agent_trace_obj.success}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in agent execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute agent query: {str(e)}"
        )


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": "Project Orbit Agent Service",
        "version": "0.1.0",
        "endpoints": {
            "execute": "/execute",
            "health": "/health",
            "docs": "/docs"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agent-service"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

