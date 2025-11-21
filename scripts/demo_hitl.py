#!/usr/bin/env python3
"""
HITL Approval Demo Script

This script demonstrates the HITL (Human-In-The-Loop) approval workflow:
1. Executes a workflow that triggers HITL pause
2. Shows the approval request
3. Simulates human approval/rejection
4. Shows the workflow continuation
"""

import asyncio
import sys
import json
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.agents.workflow import WorkflowGraph, WorkflowStatus
from src.agents.workflow import HITLPauseNode, WorkflowState
import requests
import time

API_BASE = "http://localhost:8000"


def print_section(title: str):
    """Print a formatted section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80 + "\n")


def print_step(step_num: int, description: str):
    """Print a workflow step."""
    print(f"Step {step_num}: {description}")


def simulate_workflow_with_risks():
    """Simulate a workflow that will trigger HITL pause."""
    print_section("HITL Approval Workflow Demo")
    
    print("This demo shows how the workflow pauses for human approval when risks are detected.")
    print("\nWorkflow Steps:")
    print("1. Planner: Plans dashboard creation")
    print("2. Data Generator: Generates dashboard content")
    print("3. Risk Detector: Detects risks in the data")
    print("4. HITL Pause: Pauses for human approval (if risks detected)")
    print("5. Evaluator: Finalizes dashboard (if approved)")
    
    print_section("Starting Workflow Execution")
    
    # Create workflow with callback for demo
    approval_id_holder = {"id": None, "approved": None}
    
    async def approval_callback(approval_id: str) -> bool:
        """Callback for HITL approval in demo mode."""
        approval_id_holder["id"] = approval_id
        print(f"\n⚠️  HITL PAUSE TRIGGERED")
        print(f"   Approval ID: {approval_id}")
        print(f"   Workflow paused, waiting for human approval...")
        
        # In demo, we'll use the API to approve
        print(f"\n   Checking approval status via API...")
        
        # Wait a bit to simulate human review time
        await asyncio.sleep(2)
        
        # Try to get approval from API (if available)
        try:
            response = requests.get(f"{API_BASE}/hitl/approvals/{approval_id}", timeout=5)
            if response.status_code == 200:
                approval_data = response.json()
                if approval_data.get("approved") is not None:
                    approved = approval_data.get("approved", False)
                    approval_id_holder["approved"] = approved
                    print(f"   ✅ Approval decision found: {'APPROVED' if approved else 'REJECTED'}")
                    return approved
        except:
            pass
        
        # For demo, auto-approve after showing the request
        print(f"\n   📋 Approval Request Details:")
        print(f"      - Company: TestCompany")
        print(f"      - Risk Count: 2")
        print(f"      - Risks: layoff, security_breach")
        print(f"\n   🤖 Demo Mode: Auto-approving for demonstration...")
        await asyncio.sleep(1)
        
        approval_id_holder["approved"] = True
        return True
    
    # Execute workflow
    workflow = WorkflowGraph(hitl_approval_callback=approval_callback)
    
    print("Executing workflow for 'TestCompany'...")
    print("(Note: This will use mocked risk detection for demo purposes)\n")
    
    # Run workflow
    state = asyncio.run(workflow.execute("TestCompany"))
    
    print_section("Workflow Execution Results")
    
    print(f"Company: {state.company_name}")
    print(f"Status: {state.status.value}")
    print(f"Risk Detected: {state.risk_detected}")
    print(f"HITL Approval ID: {state.hitl_approval_id}")
    print(f"HITL Approved: {state.hitl_approved}")
    
    print("\nExecution Path:")
    execution_path = workflow.get_execution_path(state)
    for i, node in enumerate(execution_path, 1):
        marker = "⏸️" if node == "hitl_pause" else "✅"
        print(f"  {i}. {marker} {node}")
    
    if state.hitl_approval_id:
        print(f"\n📝 HITL Event History:")
        print(f"   - Pause triggered: Risk detected")
        if state.hitl_approved:
            print(f"   - Approval granted: Workflow continued")
        else:
            print(f"   - Approval denied: Workflow stopped")
    
    print_section("Demo Complete")
    
    return state


def demonstrate_api_endpoints():
    """Demonstrate HITL API endpoints."""
    print_section("HITL API Endpoints Demo")
    
    print("Available HITL API Endpoints:")
    print("1. GET  /hitl/approvals - List all approval requests")
    print("2. GET  /hitl/approvals/{id} - Get approval details")
    print("3. POST /hitl/approvals/{id}/approve - Approve a request")
    print("4. POST /hitl/approvals/{id}/reject - Reject a request")
    print("5. POST /dashboard/workflow - Execute workflow with HITL")
    
    print("\nTesting API endpoints...")
    
    try:
        # List approvals
        print("\n1. Listing all approvals:")
        response = requests.get(f"{API_BASE}/hitl/approvals", timeout=5)
        if response.status_code == 200:
            approvals = response.json()
            print(f"   Found {len(approvals)} approval requests")
            for approval in approvals[:3]:  # Show first 3
                status = "pending" if approval.get("approved") is None else (
                    "approved" if approval.get("approved") else "rejected"
                )
                print(f"   - {approval.get('approval_id', 'unknown')[:8]}... ({status})")
        else:
            print(f"   API returned status {response.status_code}")
    except Exception as e:
        print(f"   ⚠️  API not available: {e}")
        print("   (This is OK if the API server is not running)")


def main():
    """Main demo function."""
    print("\n" + "=" * 80)
    print("  HITL (Human-In-The-Loop) Approval System Demo")
    print("=" * 80)
    
    # Show API demo first
    demonstrate_api_endpoints()
    
    # Run workflow demo
    try:
        state = simulate_workflow_with_risks()
        
        print("\n" + "=" * 80)
        print("  Next Steps:")
        print("=" * 80)
        print("1. Start the API server: uvicorn src.api:app --reload")
        print("2. Start the HITL Dashboard: streamlit run src/hitl_dashboard.py")
        print("3. View approval requests in the dashboard")
        print("4. Approve/reject requests via the web interface")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

