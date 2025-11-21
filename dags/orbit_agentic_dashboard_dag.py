"""
Assignment 5: Agentic Dashboard Generation DAG
Generates agentic dashboards for all Forbes AI 50 companies using SupervisorAgent workflow.

This DAG:
1. Loads company list from GCS seed file
2. Generates agentic dashboard for each company (mapped task)
   - Uses SupervisorAgent.execute_workflow()
   - Runs: Planner → DataGenerator → RiskDetector → HITL → Evaluator
3. Stores dashboards and metadata to GCS
4. Aggregates results and saves batch summary

Schedule: 0 2 * * * (2 AM daily)
"""
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import shutil
import json
import logging
import asyncio
import os
import sys
from urllib.parse import urlparse

from airflow import DAG
from airflow.decorators import task
from airflow.models import Variable

# Add src to path for imports (will be used in tasks)
src_path = '/opt/airflow/src'
if src_path not in sys.path:
    sys.path.insert(0, src_path)

logger = logging.getLogger(__name__)

# Get configuration from Airflow Variables (set in Cloud Composer)
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

# Default values
DEFAULT_BUCKET = "project-orbit-data-12345"  # Update with your bucket name
SEED_FILE_PATH = "seed/forbes_ai50_seed.json"
DASHBOARDS_PREFIX = "dashboards/"

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=10),
    'max_active_tis_per_dag': 5,
}

with DAG(
    'orbit_agentic_dashboard_dag',
    default_args=default_args,
    description='Generate agentic dashboards for all Forbes AI 50 companies using SupervisorAgent workflow',
    schedule_interval='0 2 * * *',  # 2 AM daily
    start_date=datetime(2025, 1, 1),
    catchup=False,
    tags=['orbit', 'agentic', 'dashboard', 'workflow'],
    max_active_tasks=5,  # Control parallelism
) as dag:

    @task
    def load_company_list(**context):
        """Load company list from GCS"""
        from gcs_utils import load_json_from_gcs  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        companies_data = load_json_from_gcs(bucket_name, SEED_FILE_PATH)
        
        if not companies_data:
            raise ValueError(f"Failed to load seed file from GCS: gs://{bucket_name}/{SEED_FILE_PATH}")
        
        from urllib.parse import urlparse
        for company in companies_data:
            if 'company_id' not in company:
                domain = urlparse(company.get('website', '')).netloc
                company['company_id'] = domain.replace("www.", "").split(".")[0] if domain else company.get('company_name', '').lower()
        
        logger.info(f"✅ Loaded {len(companies_data)} companies for dashboard generation")
        return companies_data

    @task(execution_timeout=timedelta(hours=1))  # Allow up to 1 hour per company
    def generate_dashboard_for_company(company: dict, **context):
        """Generate agentic dashboard for a single company"""
        from agents.supervisor import SupervisorAgent  # Import here to avoid timeout
        from gcs_utils import upload_string_to_gcs, save_json_to_gcs  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        company_id = company.get('company_id')
        company_name = company.get('company_name', 'Unknown')
        
        logger.info(f"🎯 Generating dashboard for {company_name} ({company_id})")
        
        # Validate required environment variables
        openai_api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
        mcp_server_url = MCP_SERVER_URL or os.getenv("MCP_SERVER_URL", "http://localhost:8000")
        mcp_api_key = MCP_API_KEY or os.getenv("MCP_API_KEY", "dev-key")
        
        if not openai_api_key:
            logger.error(f"❌ OPENAI_API_KEY is not set for {company_name}")
            return {
                "company_id": company_id,
                "company_name": company_name,
                "success": False,
                "dashboard_path": None,
                "metadata_path": None,
                "risk_detected": False,
                "status": "error",
                "dashboard_length": 0,
                "error": "OPENAI_API_KEY not set"
            }
        
        try:
            # Set environment variables
            os.environ['GCS_BUCKET_NAME'] = bucket_name
            os.environ['OPENAI_API_KEY'] = openai_api_key
            if PROJECT_ID:
                os.environ['PROJECT_ID'] = PROJECT_ID
            
            # Set run_id for logging (from Airflow context)
            dag_run_id = context.get('dag_run', {}).run_id if context else None
            if dag_run_id:
                os.environ['AIRFLOW_DAG_RUN_ID'] = dag_run_id
            
            # 1. Initialize SupervisorAgent with MCP configuration
            supervisor = SupervisorAgent(
                model="gpt-4o-mini",
                max_iterations=10,
                enable_llm_reasoning=True,
                mcp_url=mcp_server_url,
                mcp_api_key=mcp_api_key
            )
            
            logger.info(f"  SupervisorAgent initialized for {company_name}")
            
            # 2. Execute agentic workflow (async function)
            # Use asyncio.run() to execute async function in sync context
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
                f"  ✅ Workflow completed for {company_name}. "
                f"Status: {workflow_state.status.value if workflow_state else 'unknown'}, "
                f"Risk detected: {risk_detected}, "
                f"Dashboard length: {len(dashboard)} chars"
            )
            
            # 3. Prepare metadata
            timestamp = datetime.now()
            date_str = timestamp.strftime('%Y-%m-%d_%H%M%S')
            
            metadata = {
                "company_id": company_id,
                "company_name": company_name,
                "generated_at": timestamp.isoformat(),
                "status": workflow_state.status.value if workflow_state else "unknown",
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
                "dashboard_length": len(dashboard),
                "success": result.get("trace").success if trace else False,
                "evaluation_score": result.get("evaluation_score")
            }
            
            # 4. Save dashboard and metadata to GCS
            dashboard_dir = f"{DASHBOARDS_PREFIX}{company_id}/{date_str}/"
            
            # Save dashboard markdown
            dashboard_path = f"{dashboard_dir}dashboard.md"
            dashboard_uploaded = upload_string_to_gcs(
                bucket_name=bucket_name,
                content=dashboard,
                gcs_blob_path=dashboard_path,
                content_type='text/markdown'
            )
            
            if not dashboard_uploaded:
                raise Exception(f"Failed to upload dashboard to {dashboard_path}")
            
            logger.info(f"  📄 Dashboard saved to gs://{bucket_name}/{dashboard_path}")
            
            # Save metadata
            metadata_path = f"{dashboard_dir}metadata.json"
            metadata_saved = save_json_to_gcs(
                bucket_name=bucket_name,
                data=metadata,
                gcs_blob_path=metadata_path
            )
            
            if not metadata_saved:
                logger.warning(f"  ⚠️  Failed to save metadata to {metadata_path}")
            
            # Save trace (if available)
            if trace:
                trace_path = f"{dashboard_dir}trace.json"
                try:
                    # Convert ReActTrace to dict
                    trace_dict = {
                        "query": trace.query,
                        "company_id": trace.company_id,
                        "started_at": trace.started_at.isoformat() if hasattr(trace.started_at, 'isoformat') else str(trace.started_at),
                        "completed_at": trace.completed_at.isoformat() if hasattr(trace.completed_at, 'isoformat') else str(trace.completed_at),
                        "success": trace.success,
                        "final_answer": trace.final_answer[:500] if trace.final_answer else "",  # Truncate for storage
                        "total_steps": trace.total_steps,
                        "steps": [
                            {
                                "step_number": step.step_number,
                                "thought": step.thought,
                                "action": step.action.value if hasattr(step.action, 'value') else str(step.action),
                                "action_input": step.action_input,
                                "observation": step.observation[:500] if step.observation else "",  # Truncate
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
                        logger.info(f"  📊 Trace saved to gs://{bucket_name}/{trace_path}")
                except Exception as e:
                    logger.warning(f"  ⚠️  Failed to save trace: {e}")
            
            # Return summary for aggregation
            return {
                "company_id": company_id,
                "company_name": company_name,
                "success": metadata["success"],
                "dashboard_path": dashboard_path,
                "metadata_path": metadata_path,
                "risk_detected": risk_detected,
                "status": metadata["status"],
                "dashboard_length": len(dashboard),
                "error": None
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating dashboard for {company_name}: {e}", exc_info=True)
            
            # Return error summary
            return {
                "company_id": company_id,
                "company_name": company_name,
                "success": False,
                "dashboard_path": None,
                "metadata_path": None,
                "risk_detected": False,
                "status": "error",
                "dashboard_length": 0,
                "error": str(e)
            }

    @task
    def store_batch_summary(all_results: list, **context):
        """Log and store batch summary to GCS bucket"""
        from gcs_utils import save_json_to_gcs  # Import here to avoid timeout
        
        bucket_name = GCS_BUCKET_NAME or DEFAULT_BUCKET
        
        # Resolve LazyXComAccess objects to actual lists/dicts for JSON serialization
        try:
            if hasattr(all_results, '__iter__') and not isinstance(all_results, (list, dict, str)):
                all_results = list(all_results)
        except Exception as e:
            logger.warning(f"⚠️  Could not resolve LazyXComAccess for all_results: {e}")
            all_results = [r for r in all_results] if all_results else []
        
        timestamp = datetime.now()
        batch_id = timestamp.strftime('%Y%m%d_%H%M%S')
        
        # Aggregate results
        successful = [r for r in all_results if r.get('success', False)]
        failed = [r for r in all_results if not r.get('success', False)]
        high_risk = [r for r in all_results if r.get('risk_detected', False)]
        
        total_dashboard_length = sum(r.get('dashboard_length', 0) for r in all_results)
        avg_dashboard_length = total_dashboard_length / len(all_results) if all_results else 0
        
        summary = {
            "batch_id": f"batch_{batch_id}",
            "generation_date": timestamp.isoformat(),
            "date": timestamp.strftime('%Y-%m-%d'),
            "version": "v2-agentic-dashboard",
            "dag_run_id": context.get('dag_run').run_id if context.get('dag_run') else None,
            "total_companies": len(all_results),
            "successful": len(successful),
            "failed": len(failed),
            "high_risk_companies": len(high_risk),
            "success_rate": round(len(successful) / len(all_results) * 100, 2) if all_results else 0,
            "total_dashboard_length": total_dashboard_length,
            "average_dashboard_length": round(avg_dashboard_length, 0),
            "companies": all_results,
            "failed_companies": [
                {
                    "company_id": r.get('company_id'),
                    "company_name": r.get('company_name'),
                    "error": r.get('error')
                }
                for r in failed
            ],
            "high_risk_companies": [
                {
                    "company_id": r.get('company_id'),
                    "company_name": r.get('company_name'),
                    "risk_detected": True
                }
                for r in high_risk
            ]
        }
        
        # Save batch summary to GCS
        summary_path = f"{DASHBOARDS_PREFIX}batch_{batch_id}/summary.json"
        success = save_json_to_gcs(bucket_name, summary, summary_path)
        
        if success:
            logger.info(f"✅ Batch summary saved to gs://{bucket_name}/{summary_path}")
            logger.info(
                f"   Summary: {len(successful)}/{len(all_results)} successful, "
                f"{len(high_risk)} high-risk, {len(failed)} failed"
            )
            logger.info(f"   Total dashboard length: {total_dashboard_length} chars, Average: {round(avg_dashboard_length, 0)} chars")
        else:
            logger.error(f"❌ Failed to save batch summary to GCS")
        
        return summary

    # Task flow - Pipeline pattern: each company processes independently
    companies = load_company_list()
    
    # Expand: Create one task per company (mapped task)
    # Airflow will automatically create 50 parallel tasks (controlled by max_active_tasks=5)
    dashboard_results = generate_dashboard_for_company.expand(company=companies)
    
    # Aggregate results
    batch_summary = store_batch_summary(dashboard_results)