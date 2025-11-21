"""
HITL Approval Dashboard - Streamlit Visualization

This dashboard provides a visual interface for reviewing and approving HITL requests.
It shows workflow execution paths, risk details, and allows reviewers to approve/reject requests.
"""

import streamlit as st
import requests
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import os

# Configuration
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
HITL_APPROVALS_DIR = Path(__file__).parent.parent / "data" / "hitl_approvals"

st.set_page_config(
    page_title="HITL Approval Dashboard",
    page_icon="👤",
    layout="wide"
)

# Custom CSS for better visualization
st.markdown("""
<style>
    .approval-card {
        border: 2px solid #e0e0e0;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .pending {
        border-color: #ff9800;
        background-color: #fff3e0;
    }
    .approved {
        border-color: #4caf50;
        background-color: #e8f5e9;
    }
    .rejected {
        border-color: #f44336;
        background-color: #ffebee;
    }
    .risk-badge {
        display: inline-block;
        padding: 5px 10px;
        border-radius: 15px;
        font-size: 0.8em;
        margin: 5px;
    }
    .risk-high {
        background-color: #ffcdd2;
        color: #c62828;
    }
    .risk-medium {
        background-color: #ffe0b2;
        color: #e65100;
    }
</style>
""", unsafe_allow_html=True)


def load_approvals_from_api() -> List[Dict]:
    """Load approvals from API."""
    try:
        response = requests.get(f"{API_BASE}/hitl/approvals", timeout=5)
        if response.status_code == 200:
            return response.json()
        else:
            st.error(f"Failed to load approvals: {response.status_code}")
            return []
    except Exception as e:
        st.warning(f"API not available, loading from files: {e}")
        return load_approvals_from_files()


def load_approvals_from_files() -> List[Dict]:
    """Load approvals from local files."""
    approvals = []
    if HITL_APPROVALS_DIR.exists():
        for approval_file in HITL_APPROVALS_DIR.glob("*.json"):
            try:
                with open(approval_file, 'r') as f:
                    data = json.load(f)
                    approvals.append(data)
            except:
                continue
    return sorted(approvals, key=lambda x: x.get("paused_at", ""), reverse=True)


def get_approval_status(approval: Dict) -> str:
    """Get approval status."""
    if approval.get("approved") is None:
        return "pending"
    elif approval.get("approved") is True:
        return "approved"
    else:
        return "rejected"


def approve_request(approval_id: str, reviewer: str, notes: str) -> bool:
    """Approve a request via API."""
    try:
        response = requests.post(
            f"{API_BASE}/hitl/approvals/{approval_id}/approve",
            json={"reviewer": reviewer, "review_notes": notes},
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to approve: {e}")
        return False


def reject_request(approval_id: str, reviewer: str, notes: str) -> bool:
    """Reject a request via API."""
    try:
        response = requests.post(
            f"{API_BASE}/hitl/approvals/{approval_id}/reject",
            json={"reviewer": reviewer, "review_notes": notes},
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        st.error(f"Failed to reject: {e}")
        return False


def render_workflow_visualization(approval: Dict):
    """Render workflow execution path visualization."""
    status = get_approval_status(approval)
    
    # Define workflow nodes
    nodes = ["Planner", "Data Generator", "Risk Detector"]
    
    if status == "pending":
        nodes.append("⏸️ HITL Pause (Waiting)")
    elif status == "approved":
        nodes.append("✅ HITL Approved")
        nodes.append("Evaluator")
    else:
        nodes.append("❌ HITL Rejected")
    
    # Create visualization
    st.subheader("Workflow Execution Path")
    
    # Simple text-based visualization
    path_str = " → ".join(nodes)
    st.markdown(f"**Execution Path:** `{path_str}`")
    
    # Status indicator
    if status == "pending":
        st.warning("⏸️ Workflow is paused, waiting for approval")
    elif status == "approved":
        st.success("✅ Workflow approved, continuing to completion")
    else:
        st.error("❌ Workflow rejected, execution stopped")


def render_risk_details(approval: Dict):
    """Render risk details."""
    st.subheader("Risk Details")
    
    risk_count = approval.get("risk_count", 0)
    risks = approval.get("risks", [])
    
    st.metric("Total Risks Detected", risk_count)
    
    if risks:
        for i, risk in enumerate(risks[:5], 1):
            risk_type = risk.get("risk_type", "unknown")
            severity = risk.get("severity", "medium")
            context = risk.get("context", "")[:200]
            
            severity_color = "risk-high" if severity == "high" else "risk-medium"
            
            with st.expander(f"Risk {i}: {risk_type.upper()} ({severity})"):
                st.markdown(f"**Type:** `{risk_type}`")
                st.markdown(f"**Severity:** `{severity}`")
                st.markdown(f"**Context:** {context}...")


def main():
    """Main dashboard function."""
    st.title("👤 HITL Approval Dashboard")
    st.markdown("Human-in-the-Loop approval interface for risk-sensitive workflows")
    
    # Sidebar filters
    with st.sidebar:
        st.header("Filters")
        status_filter = st.selectbox(
            "Status",
            ["All", "Pending", "Approved", "Rejected"]
        )
        
        st.header("Actions")
        if st.button("🔄 Refresh"):
            st.rerun()
    
    # Load approvals
    approvals = load_approvals_from_api()
    
    # Filter approvals
    if status_filter != "All":
        status_map = {"Pending": "pending", "Approved": "approved", "Rejected": "rejected"}
        approvals = [
            a for a in approvals
            if get_approval_status(a) == status_map[status_filter]
        ]
    
    # Statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Requests", len(approvals))
    with col2:
        pending = sum(1 for a in approvals if get_approval_status(a) == "pending")
        st.metric("Pending", pending, delta=None)
    with col3:
        approved = sum(1 for a in approvals if get_approval_status(a) == "approved")
        st.metric("Approved", approved, delta=None)
    with col4:
        rejected = sum(1 for a in approvals if get_approval_status(a) == "rejected")
        st.metric("Rejected", rejected, delta=None)
    
    st.divider()
    
    # Display approvals
    if not approvals:
        st.info("No approval requests found.")
        return
    
    for approval in approvals:
        approval_id = approval.get("approval_id", "unknown")
        company_name = approval.get("company_name", "Unknown")
        status = get_approval_status(approval)
        paused_at = approval.get("paused_at", "")
        
        # Status-based styling
        status_class = status
        status_icon = {
            "pending": "⏸️",
            "approved": "✅",
            "rejected": "❌"
        }.get(status, "❓")
        
        with st.container():
            st.markdown(f'<div class="approval-card {status_class}">', unsafe_allow_html=True)
            
            # Header
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"### {status_icon} {company_name}")
                st.caption(f"Approval ID: `{approval_id}`")
                if paused_at:
                    try:
                        dt = datetime.fromisoformat(paused_at.replace('Z', '+00:00'))
                        st.caption(f"Paused at: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                    except:
                        st.caption(f"Paused at: {paused_at}")
            
            with col2:
                st.markdown(f"**Status:** `{status.upper()}`")
            
            # Tabs for different views
            tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Risks", "Workflow", "Dashboard Preview"])
            
            with tab1:
                st.write(f"**Company:** {company_name}")
                st.write(f"**Risk Count:** {approval.get('risk_count', 0)}")
                st.write(f"**Status:** {status}")
                
                if approval.get("reviewed_at"):
                    st.write(f"**Reviewed At:** {approval.get('reviewed_at')}")
                if approval.get("reviewer"):
                    st.write(f"**Reviewer:** {approval.get('reviewer')}")
                if approval.get("review_notes"):
                    st.write(f"**Review Notes:** {approval.get('review_notes')}")
            
            with tab2:
                render_risk_details(approval)
            
            with tab3:
                render_workflow_visualization(approval)
            
            with tab4:
                dashboard_preview = approval.get("dashboard_preview")
                if dashboard_preview:
                    st.markdown("**Dashboard Preview (first 500 chars):**")
                    st.text(dashboard_preview)
                else:
                    st.info("No dashboard preview available")
            
            # Action buttons (only for pending)
            if status == "pending":
                st.divider()
                col1, col2, col3 = st.columns([1, 1, 2])
                
                with col1:
                    if st.button(f"✅ Approve", key=f"approve_{approval_id}", type="primary"):
                        reviewer = st.session_state.get(f"reviewer_{approval_id}", "Reviewer")
                        notes = st.session_state.get(f"notes_{approval_id}", "")
                        if approve_request(approval_id, reviewer, notes):
                            st.success("Approved successfully!")
                            st.rerun()
                
                with col2:
                    if st.button(f"❌ Reject", key=f"reject_{approval_id}"):
                        reviewer = st.session_state.get(f"reviewer_{approval_id}", "Reviewer")
                        notes = st.session_state.get(f"notes_{approval_id}", "")
                        if reject_request(approval_id, reviewer, notes):
                            st.success("Rejected successfully!")
                            st.rerun()
                
                with col3:
                    reviewer_name = st.text_input(
                        "Reviewer Name",
                        key=f"reviewer_{approval_id}",
                        value=st.session_state.get(f"reviewer_{approval_id}", "")
                    )
                    review_notes = st.text_area(
                        "Review Notes",
                        key=f"notes_{approval_id}",
                        value=st.session_state.get(f"notes_{approval_id}", "")
                    )
            
            st.markdown('</div>', unsafe_allow_html=True)
            st.divider()


if __name__ == "__main__":
    main()

