import streamlit as st
import requests
import os

API_BASE = os.getenv("API_BASE", "http://localhost:8000")

st.set_page_config(page_title="Project Orbit", layout="wide")
st.title("Project ORBIT – PE Dashboard for Forbes AI 50")

try:
    companies = requests.get(f"{API_BASE}/companies", timeout=30).json()
except requests.exceptions.Timeout:
    st.warning(f"⏱️ API service timeout. The service may be starting up. Please try again in a moment.")
    companies = []
except requests.exceptions.ConnectionError:
    st.error(f"🔌 Cannot connect to API service at {API_BASE}. Please verify the service is running.")
    companies = []
except Exception as e:
    st.warning(f"⚠️ Could not load companies from API: {str(e)}. Loading from local files.")
    companies = []

names = [c["company_name"] for c in companies] if companies else ["ExampleAI"]
choice = st.selectbox("Select company", names)

col1, col2 = st.columns(2)

with col1:
    st.subheader("Structured pipeline")
    if st.button("Generate (Structured)"):
        resp = requests.post(f"{API_BASE}/dashboard/structured", json={"company_name": choice})
        st.markdown(resp.json()["dashboard"])

with col2:
    st.subheader("RAG pipeline")
    if st.button("Generate (RAG)"):
        resp = requests.post(f"{API_BASE}/dashboard/rag", json={"company_name": choice})
        st.markdown(resp.json()["dashboard"])
        
# AI Agent Workflow Section
st.divider()
st.subheader("🤖 AI Agent Workflow (Supervisor Agent + WorkflowGraph)")

if st.button("🚀 Generate with AI Agent", type="primary", use_container_width=True):
    with st.spinner("🤖 Supervisor Agent is reasoning and gathering information..."):
        try:
            # Call the agent endpoint
            default_query = f"Generate a comprehensive dashboard for {choice}"
            resp = requests.post(
                f"{API_BASE}/dashboard/agent",
                json={
                    "company_name": choice,
                    "query": default_query
                },
                timeout=300  # 5 minute timeout for agent workflow
            )
            
            if resp.status_code == 200:
                result = resp.json()
                
                # Display success message
                st.success(f"✅ Agent workflow completed successfully!")
                
                # Show summary metrics
                col_metric1, col_metric2, col_metric3, col_metric4 = st.columns(4)
                with col_metric1:
                    st.metric("Agent Steps", result["agent_trace"]["total_steps"])
                with col_metric2:
                    st.metric("Workflow Nodes", len(result["execution_path"]))
                with col_metric3:
                    st.metric("Risks Detected", result["risk_count"])
                with col_metric4:
                    status_emoji = "✅" if result["status"] == "completed" else "⏸️" if result["status"] == "paused_for_approval" else "❌"
                    st.metric("Status", f"{status_emoji} {result['status']}")
                
                # Create tabs for different views
                tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "🤖 Agent Trace", "🔄 Workflow Execution", "📈 Summary"])
                
                with tab1:
                    st.markdown("### Generated Dashboard")
                    if result.get("dashboard"):
                        st.markdown(result["dashboard"])
                    else:
                        st.warning("No dashboard generated. Check workflow execution for details.")
                
                with tab2:
                    st.markdown("### Supervisor Agent ReAct Trace")
                    agent_trace = result.get("agent_trace", {})
                    
                    st.info(f"**Query:** {agent_trace.get('query', 'N/A')}")
                    st.info(f"**Company ID:** {agent_trace.get('company_id', 'N/A')}")
                    st.info(f"**Success:** {agent_trace.get('success', False)}")
                    st.info(f"**Total Steps:** {agent_trace.get('total_steps', 0)}")
                    
                    if agent_trace.get("final_answer"):
                        st.markdown("#### Final Answer")
                        st.markdown(agent_trace["final_answer"])
                    
                    st.markdown("#### ReAct Steps")
                    steps = agent_trace.get("steps", [])
                    for i, step in enumerate(steps, 1):
                        with st.expander(f"Step {step.get('step_number', i)}: {step.get('action', 'N/A')}"):
                            st.markdown(f"**Thought:** {step.get('thought', 'N/A')}")
                            st.markdown(f"**Action:** `{step.get('action', 'N/A')}`")
                            if step.get("action_input"):
                                st.json(step["action_input"])
                            st.markdown(f"**Observation:** {step.get('observation', 'N/A')[:500]}...")
                            if step.get("error"):
                                st.error(f"**Error:** {step['error']}")
                
                with tab3:
                    st.markdown("### Workflow Graph Execution")
                    workflow = result.get("workflow_execution", {})
                    
                    st.info(f"**Status:** {workflow.get('status', 'N/A')}")
                    st.info(f"**Execution Path:** {' → '.join(result.get('execution_path', []))}")
                    
                    st.markdown("#### Node Results")
                    node_results = workflow.get("node_results", {})
                    for node_name, node_result in node_results.items():
                        with st.expander(f"Node: {node_name}"):
                            st.markdown(f"**Status:** {node_result.get('status', 'N/A')}")
                            if node_result.get("output"):
                                st.json(node_result["output"])
                            if node_result.get("error"):
                                st.error(f"**Error:** {node_result['error']}")
                            st.caption(f"Timestamp: {node_result.get('timestamp', 'N/A')}")
                    
                    if workflow.get("risk_detected"):
                        st.warning(f"⚠️ **Risk Detected:** {workflow.get('risk_count', 0)} risk(s) found")
                        if workflow.get("hitl_approval_id"):
                            st.info(f"🛑 **HITL Approval Required:** {workflow.get('hitl_approval_id')}")
                
                with tab4:
                    st.markdown("### Execution Summary")
                    st.json({
                        "company_name": result.get("company_name"),
                        "company_id": result.get("company_id"),
                        "query": result.get("query"),
                        "status": result.get("status"),
                        "agent_steps": result.get("agent_trace", {}).get("total_steps"),
                        "workflow_path": result.get("execution_path"),
                        "risk_detected": result.get("risk_detected"),
                        "risk_count": result.get("risk_count"),
                        "hitl_approval_id": result.get("hitl_approval_id"),
                        "started_at": result.get("started_at"),
                        "completed_at": result.get("completed_at")
                    })
            
            else:
                st.error(f"❌ Error: {resp.status_code} - {resp.text}")
                
        except requests.exceptions.Timeout:
            st.error("⏱️ Request timed out. The agent workflow may take several minutes. Please try again.")
        except requests.exceptions.ConnectionError:
            st.error("🔌 Connection error. Make sure the API server is running at " + API_BASE)
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.exception(e)
        