"""
On-Demand Dashboard Generation DAG
Triggered from backend API to generate THREE dashboards for a single company:
1. Structured Dashboard (from payload JSON)
2. RAG Dashboard (from Pinecone vector search)
3. Agentic Dashboard (from SupervisorAgent workflow)

This DAG:
1. Generates all three dashboards in parallel
2. Detects risks in all dashboards
3. Handles HITL approval if risks detected
4. Stores all three dashboards separately in GCS

Trigger: Manual (via Airflow API from backend)
Schedule: None (on-demand only)
"""
from datetime import datetime, timedelta
import json
import logging
import os
import sys
import asyncio
from pathlib import Path
import time

from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable
from airflow.utils.trigger_rule import TriggerRule

# Add src to path
src_path = '/opt/airflow/src'
if src_path not in sys.path:
    sys.path.insert(0, src_path)

logger = logging.getLogger(__name__)

# Get configuration
try:
    GCS_BUCKET_NAME = Variable.get("GCS_BUCKET_NAME", default_var="")
    PROJECT_ID = Variable.get("PROJECT_ID", default_var="")
    MCP_SERVER_URL = Variable.get("MCP_SERVER_URL", default_var="")
    MCP_API_KEY = Variable.get("MCP_API_KEY", default_var="")
    OPENAI_API_KEY = Variable.get("OPENAI_API_KEY", default_var="")
except Exception:
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "")
    PROJECT_ID = os.getenv("PROJECT_ID", "")
    MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "")
    MCP_API_KEY = os.getenv("MCP_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

DEFAULT_BUCKET = "project-orbit-data-12345"
DASHBOARDS_PREFIX = "dashboards/on_demand/"

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

with DAG(
    'orbit_on_demand_dashboard_dag',
    default_args=default_args,
    description='On-demand dashboard generation: Structured + RAG + Agentic dashboards with HITL support',
    schedule_interval=None,  # Manual trigger only
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['orbit', 'on-demand', 'dashboard', 'structured', 'rag', 'agentic'],
    params={
        'company_name': 'Anthropic',  # Default, can be overridden via API
        'company_id': None,  # Optional, will be derived if not provided
    },
) as dag:

    @task
    def extract_company_info(**context):
        """Extract company info from DAG run parameters"""
        company_name = context['params'].get('company_name')
        company_id = context['params'].get('company_id')
        
        if not company_name:
            raise ValueError("company_name parameter is required")
        
        # Derive company_id if not provided
        if not company_id:
            from urllib.parse import urlparse
            # Try to get from seed file
            try:
                from gcs_utils import load_json_from_gcs
                bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
                companies = load_json_from_gcs(bucket_name, "seed/forbes_ai50_seed.json")
                for company in companies:
                    if company.get('company_name') == company_name:
                        domain = urlparse(company.get('website', '')).netloc
                        company_id = domain.replace("www.", "").split(".")[0] if domain else company_name.lower()
                        break
            except Exception as e:
                logger.warning(f"Could not load from seed file: {e}")
                company_id = company_name.lower().replace(" ", "_")
        
        logger.info(f"📋 Company Info: {company_name} ({company_id})")
        
        return {
            "company_name": company_name,
            "company_id": company_id
        }

    @task(execution_timeout=timedelta(minutes=15))
    def generate_structured_dashboard(company_info: dict, **context):
        """Generate structured dashboard from payload JSON"""
        import httpx
        
        company_name = company_info['company_name']
        company_id = company_info['company_id']
        
        logger.info(f"📊 Generating structured dashboard for {company_name}")
        
        # Call backend API to generate structured dashboard
        api_base = os.getenv("API_BASE", "http://host.docker.internal:8000")
        
        try:
            async def call_api():
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        f"{api_base}/dashboard/structured",
                        json={"company_name": company_name},
                    )
                    response.raise_for_status()
                    return response.json()
            
            result = asyncio.run(call_api())
            dashboard = result.get("dashboard", "")
            
            logger.info(f"✅ Structured dashboard generated ({len(dashboard)} chars)")
            
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": dashboard,
                "pipeline_type": "structured",
                "status": "success"
            }
        except Exception as e:
            logger.error(f"❌ Error generating structured dashboard: {e}", exc_info=True)
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": None,
                "pipeline_type": "structured",
                "status": "error",
                "error": str(e)
            }

    @task(execution_timeout=timedelta(minutes=15))
    def generate_rag_dashboard(company_info: dict, **context):
        """Generate RAG dashboard from vector database"""
        import httpx
        
        company_name = company_info['company_name']
        company_id = company_info['company_id']
        
        logger.info(f"🔍 Generating RAG dashboard for {company_name}")
        
        # Call backend API to generate RAG dashboard
        api_base = os.getenv("API_BASE", "http://host.docker.internal:8000")
        
        try:
            async def call_api():
                async with httpx.AsyncClient(timeout=300.0) as client:
                    response = await client.post(
                        f"{api_base}/dashboard/rag",
                        json={"company_name": company_name},
                    )
                    response.raise_for_status()
                    return response.json()
            
            result = asyncio.run(call_api())
            dashboard = result.get("dashboard", "")
            
            logger.info(f"✅ RAG dashboard generated ({len(dashboard)} chars)")
            
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": dashboard,
                "pipeline_type": "rag",
                "status": "success"
            }
        except Exception as e:
            logger.error(f"❌ Error generating RAG dashboard: {e}", exc_info=True)
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": None,
                "pipeline_type": "rag",
                "status": "error",
                "error": str(e)
            }

    @task(execution_timeout=timedelta(hours=1))
    def generate_agentic_dashboard(company_info: dict, **context):
        """Generate agentic dashboard using SupervisorAgent workflow"""
        from agents.supervisor import SupervisorAgent  # Import here to avoid timeout
        
        company_name = company_info['company_name']
        company_id = company_info['company_id']
        
        logger.info(f"🤖 Generating agentic dashboard for {company_name}")
        
        # Validate required environment variables
        openai_api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        mcp_server_url = MCP_SERVER_URL or os.getenv("MCP_SERVER_URL", "http://host.docker.internal:8000")
        mcp_api_key = MCP_API_KEY or os.getenv("MCP_API_KEY", "dev-key")
        
        if not openai_api_key:
            logger.error(f"❌ OPENAI_API_KEY is not set for {company_name}")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": None,
                "pipeline_type": "agentic",
                "status": "error",
                "error": "OPENAI_API_KEY not set"
            }
        
        try:
            # Set environment variables
            bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            os.environ['OPENAI_API_KEY'] = openai_api_key
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Set run_id for logging (from Airflow context)
            dag_run_id = context.get('dag_run', {}).run_id if context.get('dag_run') else None
            if dag_run_id:
                os.environ['AIRFLOW_DAG_RUN_ID'] = dag_run_id
            
            # Initialize SupervisorAgent
            supervisor = SupervisorAgent(
                model="gpt-4o-mini",
                max_iterations=10,
                enable_llm_reasoning=True,
                mcp_url=mcp_server_url,
                mcp_api_key=mcp_api_key
            )
            
            logger.info(f"  SupervisorAgent initialized for {company_name}")
            
            # Execute agentic workflow (async function)
            logger.info(f"  Executing workflow for {company_name}...")
            result = asyncio.run(
                supervisor.execute_workflow(
                    company_name=company_name,
                    company_id=company_id
                )
            )
            
            # Extract results
            dashboard = result.get("dashboard", "")
            trace = result.get("trace")
            workflow_state = result.get("workflow_state")
            risk_detected = result.get("risk_detected", False)
            risk_signals = result.get("risk_signals", [])
            execution_path = result.get("execution_path", [])
            
            logger.info(
                f"  ✅ Agentic workflow completed for {company_name}. "
                f"Status: {workflow_state.status.value if workflow_state else 'unknown'}, "
                f"Risk detected: {risk_detected}, "
                f"Dashboard length: {len(dashboard)} chars"
            )
            
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": dashboard,
                "pipeline_type": "agentic",
                "status": "success",
                "workflow_state": workflow_state.status.value if workflow_state else "unknown",
                "risk_detected": risk_detected,
                "risk_signals": [
                    {
                        "signal_type": signal.signal_type if hasattr(signal, 'signal_type') else str(signal),
                        "severity": signal.severity if hasattr(signal, 'severity') else "unknown",
                        "description": str(signal)
                    }
                    for signal in risk_signals
                ] if risk_signals else [],
                "execution_path": execution_path,
                "trace": trace  # Store trace for later (will be saved separately)
            }
        except Exception as e:
            logger.error(f"❌ Error generating agentic dashboard: {e}", exc_info=True)
            return {
                "company_id": company_id,
                "company_name": company_name,
                "dashboard": None,
                "pipeline_type": "agentic",
                "status": "error",
                "error": str(e)
            }

    @task
    def detect_risks(structured_result: dict, rag_result: dict, agentic_result: dict, **context):
        """Detect risks in all three dashboards"""
        try:
            # Try importing from src.risk_detection (if src is in path)
            from risk_detection import detect_risk_signals
        except ImportError:
            try:
                # Fallback: try src.risk_detection
                from src.risk_detection import detect_risk_signals
            except ImportError:
                # Final fallback: simple keyword-based risk detection
                logger.warning("risk_detection module not found, using simple risk detection")
                def detect_risk_signals(text):
                    # Simple keyword-based risk detection
                    risk_keywords = ['layoff', 'breach', 'security', 'regulatory', 'risk', 'challenge', 'concern']
                    risks = []
                    text_lower = text.lower()
                    for keyword in risk_keywords:
                        if keyword in text_lower:
                            risks.append({
                                "risk_type": keyword,
                                "severity": "medium",
                                "description": f"Risk keyword '{keyword}' found in dashboard"
                            })
                    return risks
        
        company_name = structured_result.get('company_name') or rag_result.get('company_name') or agentic_result.get('company_name')
        company_id = structured_result.get('company_id') or rag_result.get('company_id') or agentic_result.get('company_id')
        
        logger.info(f"🔍 Detecting risks for {company_name}")
        
        all_risks = []
        
        # Check structured dashboard
        if structured_result.get('status') == 'success' and structured_result.get('dashboard'):
            try:
                risks = detect_risk_signals(structured_result['dashboard'])
                all_risks.extend(risks)
            except Exception as e:
                logger.warning(f"Error detecting risks in structured dashboard: {e}")
        
        # Check RAG dashboard
        if rag_result.get('status') == 'success' and rag_result.get('dashboard'):
            try:
                risks = detect_risk_signals(rag_result['dashboard'])
                all_risks.extend(risks)
            except Exception as e:
                logger.warning(f"Error detecting risks in RAG dashboard: {e}")
        
        # Check agentic dashboard (may already have risk signals from workflow)
        if agentic_result.get('status') == 'success':
            # Use risk signals from agentic workflow if available
            if agentic_result.get('risk_detected') and agentic_result.get('risk_signals'):
                all_risks.extend(agentic_result['risk_signals'])
            # Also check dashboard content
            elif agentic_result.get('dashboard'):
                try:
                    risks = detect_risk_signals(agentic_result['dashboard'])
                    all_risks.extend(risks)
                except Exception as e:
                    logger.warning(f"Error detecting risks in agentic dashboard: {e}")
        
        risk_detected = len(all_risks) > 0
        
        logger.info(f"{'⚠️  Risks detected' if risk_detected else '✅ No risks detected'}: {len(all_risks)} risk signals")
        
        return {
            "company_id": company_id,
            "company_name": company_name,
            "risk_detected": risk_detected,
            "risk_signals": [r if isinstance(r, dict) else {"description": str(r)} for r in all_risks],
            "risk_count": len(all_risks)
        }

    @task
    def check_hitl_approval(risk_result: dict, **context):
        """Check HITL approval status (waits for approval if risk detected)"""
        company_name = risk_result['company_name']
        company_id = risk_result['company_id']
        risk_detected = risk_result.get('risk_detected', False)
        
        if not risk_detected:
            logger.info(f"✅ No risks detected - skipping HITL approval")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "hitl_required": False,
                "hitl_approved": True,
                "approval_id": None
            }
        
        # Risk detected - need HITL approval
        logger.info(f"⏸️  Risk detected - checking HITL approval for {company_name}")
        
        # Get approval ID from context (set by HITL system)
        approval_id = context.get('params', {}).get('approval_id')
        
        if not approval_id:
            # Generate approval ID
            import uuid
            approval_id = str(uuid.uuid4())
        
        # Check approval file in GCS (wait up to 5 minutes)
        from gcs_utils import read_file_from_gcs
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        approval_path = f"hitl_approvals/{approval_id}.json"
        
        max_wait = 300  # 5 minutes
        check_interval = 10  # Check every 10 seconds
        waited = 0
        
        logger.info(f"   🆔 Approval ID: {approval_id}")
        logger.info(f"   ⏳ Waiting up to {max_wait}s for HITL approval...")
        
        while waited < max_wait:
            try:
                approval_data = read_file_from_gcs(bucket_name, approval_path)
                if approval_data:
                    data = json.loads(approval_data)
                    if "approved" in data:
                        approved = data["approved"]
                        logger.info(f"{'✅ Approved' if approved else '❌ Rejected'}: HITL decision for {company_name}")
                        return {
                            "company_id": company_id,
                            "company_name": company_name,
                            "hitl_required": True,
                            "hitl_approved": approved,
                            "approval_id": approval_id
                        }
            except Exception as e:
                # File doesn't exist yet or error reading
                pass
            
            time.sleep(check_interval)
            waited += check_interval
            if waited % 30 == 0:  # Log every 30 seconds
                logger.info(f"   ⏳ Still waiting for HITL approval... ({waited}/{max_wait}s)")
        
        # Timeout - reject
        logger.warning(f"⏰ HITL approval timeout - rejecting for {company_name}")
        return {
            "company_id": company_id,
            "company_name": company_name,
            "hitl_required": True,
            "hitl_approved": False,
            "approval_id": approval_id,
            "timeout": True
        }

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def store_dashboards(structured_result: dict, rag_result: dict, agentic_result: dict, 
                        risk_result: dict, hitl_result: dict, **context):
        """Store all three dashboards to GCS (only if approved or no risk)"""
        from gcs_utils import upload_string_to_gcs, save_json_to_gcs
        
        company_name = structured_result.get('company_name') or rag_result.get('company_name') or agentic_result.get('company_name')
        company_id = structured_result.get('company_id') or rag_result.get('company_id') or agentic_result.get('company_id')
        
        # Check if we should proceed
        hitl_approved = hitl_result.get('hitl_approved', True)
        risk_detected = risk_result.get('risk_detected', False)
        
        if risk_detected and not hitl_approved:
            logger.warning(f"❌ HITL approval denied - not storing dashboards for {company_name}")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "status": "rejected",
                "reason": "hitl_approval_denied",
                "structured_dashboard_path": None,
                "rag_dashboard_path": None,
                "agentic_dashboard_path": None
            }
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
        dag_run_id = context.get('dag_run').run_id if context.get('dag_run') else 'manual'
        
        dashboard_dir = f"{DASHBOARDS_PREFIX}{company_id}/{timestamp}/"
        
        # Store structured dashboard
        structured_path = None
        if structured_result.get('status') == 'success' and structured_result.get('dashboard'):
            structured_path = f"{dashboard_dir}structured_dashboard.md"
            success = upload_string_to_gcs(
                bucket_name=bucket_name,
                content=structured_result['dashboard'],
                gcs_blob_path=structured_path,
                content_type='text/markdown'
            )
            if success:
                logger.info(f"✅ Structured dashboard saved: gs://{bucket_name}/{structured_path}")
            else:
                logger.error(f"❌ Failed to save structured dashboard")
        
        # Store RAG dashboard
        rag_path = None
        if rag_result.get('status') == 'success' and rag_result.get('dashboard'):
            rag_path = f"{dashboard_dir}rag_dashboard.md"
            success = upload_string_to_gcs(
                bucket_name=bucket_name,
                content=rag_result['dashboard'],
                gcs_blob_path=rag_path,
                content_type='text/markdown'
            )
            if success:
                logger.info(f"✅ RAG dashboard saved: gs://{bucket_name}/{rag_path}")
            else:
                logger.error(f"❌ Failed to save RAG dashboard")
        
        # Store agentic dashboard
        agentic_path = None
        agentic_trace_path = None
        if agentic_result.get('status') == 'success' and agentic_result.get('dashboard'):
            agentic_path = f"{dashboard_dir}agentic_dashboard.md"
            success = upload_string_to_gcs(
                bucket_name=bucket_name,
                content=agentic_result['dashboard'],
                gcs_blob_path=agentic_path,
                content_type='text/markdown'
            )
            if success:
                logger.info(f"✅ Agentic dashboard saved: gs://{bucket_name}/{agentic_path}")
            else:
                logger.error(f"❌ Failed to save agentic dashboard")
            
            # Store trace if available
            if agentic_result.get('trace'):
                trace_path = f"{dashboard_dir}agentic_trace.json"
                try:
                    trace = agentic_result['trace']
                    trace_dict = {
                        "query": trace.query,
                        "company_id": trace.company_id,
                        "started_at": trace.started_at.isoformat() if hasattr(trace.started_at, 'isoformat') else str(trace.started_at),
                        "completed_at": trace.completed_at.isoformat() if hasattr(trace.completed_at, 'isoformat') else str(trace.completed_at),
                        "success": trace.success,
                        "final_answer": trace.final_answer[:500] if trace.final_answer else "",
                        "total_steps": trace.total_steps,
                        "steps": [
                            {
                                "step_number": step.step_number,
                                "thought": step.thought,
                                "action": step.action.value if hasattr(step.action, 'value') else str(step.action),
                                "action_input": step.action_input,
                                "observation": step.observation[:500] if step.observation else "",
                                "timestamp": step.timestamp.isoformat() if hasattr(step.timestamp, 'isoformat') else str(step.timestamp),
                                "error": step.error
                            }
                            for step in trace.steps
                        ]
                    }
                    trace_saved = save_json_to_gcs(
                        bucket_name=bucket_name,
                        data=trace_dict,
                        gcs_blob_path=trace_path
                    )
                    if trace_saved:
                        agentic_trace_path = trace_path
                        logger.info(f"✅ Agentic trace saved: gs://{bucket_name}/{trace_path}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to save agentic trace: {e}")
        
        # Store metadata
        metadata = {
            "company_id": company_id,
            "company_name": company_name,
            "generated_at": datetime.now().isoformat(),
            "dag_run_id": dag_run_id,
            "structured_dashboard": {
                "status": structured_result.get('status'),
                "path": structured_path,
                "length": len(structured_result.get('dashboard', '')) if structured_result.get('dashboard') else 0
            },
            "rag_dashboard": {
                "status": rag_result.get('status'),
                "path": rag_path,
                "length": len(rag_result.get('dashboard', '')) if rag_result.get('dashboard') else 0
            },
            "agentic_dashboard": {
                "status": agentic_result.get('status'),
                "path": agentic_path,
                "length": len(agentic_result.get('dashboard', '')) if agentic_result.get('dashboard') else 0,
                "workflow_state": agentic_result.get('workflow_state'),
                "execution_path": agentic_result.get('execution_path', []),
                "trace_path": agentic_trace_path
            },
            "risk_detection": {
                "risk_detected": risk_detected,
                "risk_count": risk_result.get('risk_count', 0),
                "risk_signals": risk_result.get('risk_signals', [])
            },
            "hitl": {
                "required": hitl_result.get('hitl_required', False),
                "approved": hitl_approved,
                "approval_id": hitl_result.get('approval_id')
            }
        }
        
        metadata_path = f"{dashboard_dir}metadata.json"
        save_json_to_gcs(bucket_name, metadata, metadata_path)
        
        logger.info(f"✅ All dashboards stored for {company_name}")
        logger.info(f"   Structured: {structured_path}")
        logger.info(f"   RAG: {rag_path}")
        logger.info(f"   Agentic: {agentic_path}")
        
        return {
            "company_id": company_id,
            "company_name": company_name,
            "status": "success" if (structured_path or rag_path or agentic_path) else "partial",
            "structured_dashboard_path": structured_path,
            "rag_dashboard_path": rag_path,
            "agentic_dashboard_path": agentic_path,
            "agentic_trace_path": agentic_trace_path,
            "metadata_path": metadata_path
        }

    # Task flow
    company_info = extract_company_info()
    
    # Generate all three dashboards in parallel
    structured_result = generate_structured_dashboard(company_info)
    rag_result = generate_rag_dashboard(company_info)
    agentic_result = generate_agentic_dashboard(company_info)
    
    # Detect risks (depends on all three dashboards)
    risk_result = detect_risks(structured_result, rag_result, agentic_result)
    
    # Check HITL approval (depends on risk detection)
    hitl_result = check_hitl_approval(risk_result)
    
    # Store all dashboards (only if approved or no risk)
    final_result = store_dashboards(structured_result, rag_result, agentic_result, 
                                   risk_result, hitl_result)

