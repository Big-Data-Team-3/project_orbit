from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
import json
import logging
from pathlib import Path
import os
import dotenv
from google.cloud import storage
from google.api_core.exceptions import NotFound
from google.oauth2 import service_account
from src.rag_pipeline import generate_dashboard, retrieve_context, load_system_prompt
from openai import OpenAI
from src.services.embeddings import Embeddings
from src.structured_extraction_v2 import extract_company_payload
from urllib.parse import urlparse
from src.agents.workflow import WorkflowGraph, WorkflowState, WorkflowStatus
from src.agents.react_models import ReActTrace, ReActStep, ActionType
from datetime import datetime
import requests


dotenv.load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Project Orbit API",
    description="PE Dashboard Factory API for Forbes AI 50 Companies",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Initialize clients
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
embeddings_client = Embeddings()

storage_client = None



def get_storage_client():
    """Get or create GCS storage client"""
    global storage_client
    
    # If already initialized, return it
    if storage_client is not None:
        return storage_client
    
    # Check if we need GCS (production mode)
    bucket_name = os.getenv("GCS_BUCKET_NAME")
    if not bucket_name:
        # Local development - don't initialize
        print("GCS_BUCKET_NAME not set, skipping GCS client initialization")
        return None
    
    # Production mode - MUST initialize successfully
    print(f"Initializing GCS client for bucket: {bucket_name}")
    try:
        project_id = os.getenv("PROJECT_ID")
        PROJECT_ROOT = Path(__file__).parent.parent
        credentials_path = PROJECT_ROOT / "config" / "gcp.json"
        
        # Try to use credentials file if it exists (local development)
        if credentials_path.exists():
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(
                str(credentials_path)
            )
            storage_client = storage.Client(project=project_id, credentials=credentials)
            print(f"GCS client initialized with credentials from {credentials_path}")
        else:
            # Use Application Default Credentials (production/Cloud Run)
            # Cloud Run automatically provides credentials via the service account
            storage_client = storage.Client(project=project_id)
            print("GCS client initialized with Application Default Credentials (production mode)")
        
        print("GCS client initialized successfully")
        return storage_client
    except Exception as e:
        error_msg = str(e)
        print(f"ERROR: Failed to initialize GCS client: {error_msg}")
        
        # In production, this is a critical error - raise it
        raise HTTPException(
            status_code=500,
            detail=f"GCS client initialization failed. This is required when GCS_BUCKET_NAME is set. "
                   f"Error: {error_msg}. "
                   f"Check that the Cloud Run service account has 'Storage Object Viewer' role. "
                   f"Verify that Application Default Credentials are configured correctly."
        )
        
# Paths
PROJECT_ROOT = Path(__file__).parent.parent
SEED_FILE = PROJECT_ROOT / "data" / "forbes_ai50_seed.json"
PAYLOADS_DIR = PROJECT_ROOT / "data" / "payloads"


# ============================================================================
# Pydantic Models
# ============================================================================

class CompanyRequest(BaseModel):
    """Request model for company name"""
    company_name: str = Field(..., description="Name of the company (e.g., 'Abridge', 'Anthropic')")

class RAGSearchRequest(BaseModel):
    """Request model for RAG search"""
    company_name: str = Field(..., description="Name of the company to search")
    top_k: Optional[int] = Field(10, ge=1, le=50, description="Number of top results to return")

class DashboardResponse(BaseModel):
    """Response model for dashboard generation"""
    company_name: str
    dashboard: str
    pipeline_type: str  # "rag" or "structured"

class RAGSearchResponse(BaseModel):
    """Response model for RAG search"""
    company_name: str
    results: List[Dict]
    total_results: int

class CompanyInfo(BaseModel):
    """Company information model"""
    company_name: str
    website: str
    linkedin: str
    hq_city: str
    hq_country: str
    category: str

class AgentDashboardRequest(BaseModel):
    """Request model for agent-driven dashboard generation"""
    company_name: str = Field(..., description="Name of the company (e.g., 'Abridge', 'Anthropic')")
    query: Optional[str] = Field(None, description="Optional query or question about the company")
    company_id: Optional[str] = Field(None, description="Optional company ID (will be extracted if not provided)")

class AgentDashboardResponse(BaseModel):
    """Response model for agent-driven dashboard generation"""
    company_name: str
    company_id: Optional[str]
    query: Optional[str]
    dashboard: Optional[str]
    status: str
    # Supervisor Agent trace
    agent_trace: Dict
    # Workflow execution details
    workflow_execution: Dict
    # Combined metadata
    execution_path: List[str]
    risk_detected: bool
    risk_count: int
    hitl_approval_id: Optional[str] = None
    hitl_approved: Optional[bool] = None
    started_at: str
    completed_at: Optional[str] = None

def load_companies() -> List[Dict]:
    """Load companies from seed file (local development)"""
    try:
        with open(SEED_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Company seed file not found")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON in seed file")

def load_companies_from_gcs() -> List[Dict]:
    """Load companies from GCS bucket (production)"""
    try:
        # Check if GCS_BUCKET_NAME is set
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        if not bucket_name:
            raise HTTPException(
                status_code=500, 
                detail="GCS_BUCKET_NAME environment variable is not set"
            )
        
        # Initialize GCS client lazily
        client = get_storage_client()
        if not client:
            raise HTTPException(
                status_code=500,
                detail="GCS client is not initialized. Check service account permissions and ensure GCS_BUCKET_NAME is set."
            )
        
        # Get the file path (remove leading slash if present)
        file_path = os.getenv("GCS_SEED_FILE_PATH", "seed/forbes_ai50_seed.json")
        if file_path.startswith('/'):
            file_path = file_path[1:]
        
        # Get the bucket and blob
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(file_path)
        
        # Check if blob exists
        if not blob.exists():
            raise HTTPException(
                status_code=404,
                detail=f"File not found in GCS: gs://{bucket_name}/{file_path}"
            )
        
        # Download and parse JSON
        content = blob.download_as_text()
        companies = json.loads(content)
        
        # Validate it's a list
        if not isinstance(companies, list):
            raise HTTPException(
                status_code=500,
                detail="Invalid data format: expected a list of companies"
            )
        
        return companies
        
    except Exception as e:
        # Check if it's a NotFound exception by checking error message/type
        error_str = str(e).lower()
        if 'not found' in error_str or '404' in error_str:
            raise HTTPException(
                status_code=404,
                detail=f"GCS bucket or file not found: gs://{bucket_name}/{file_path}"
            )
        elif isinstance(e, HTTPException):
            # Re-raise HTTP exceptions
            raise
        elif isinstance(e, json.JSONDecodeError):
            raise HTTPException(
                status_code=500,
                detail=f"Invalid JSON in GCS file: {str(e)}"
            )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to load companies from GCS: {str(e)}"
            )
def get_company_id_from_name(company_name: str) -> str:
    """Get company_id from company name by looking up website"""
    try:
        # Load companies (same logic as get_companies endpoint)
        if os.getenv("GCS_BUCKET_NAME"):
            companies = load_companies_from_gcs()
        else:
            companies = load_companies()
        
        # Find company by name (case-insensitive)
        company = None
        for c in companies:
            if c.get("company_name", "").lower() == company_name.lower():
                company = c
                break
        
        if not company:
            raise HTTPException(
                status_code=404,
                detail=f"Company '{company_name}' not found in seed file"
            )
        
        # Extract company_id from website domain
        website = company.get("website", "")
        if not website:
            raise HTTPException(
                status_code=400,
                detail=f"Company '{company_name}' has no website URL"
            )
        
        domain = urlparse(website).netloc
        company_id = domain.replace("www.", "").split(".")[0]
        return company_id.lower()
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get company_id: {str(e)}"
        )


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/", tags=["Root"])
async def root():
    """Root endpoint"""
    return {
        "message": "Project Orbit API - PE Dashboard Factory",
        "version": "0.1.0",
        "endpoints": {
            "companies": "/companies",
            "dashboard_rag": "/dashboard/rag",
            "dashboard_structured": "/dashboard/structured",
            "dashboard_workflow": "/dashboard/workflow",
            "dashboard_agent": "/dashboard/agent",
            "hitl_approvals": "/hitl/approvals",
        }
    }

@app.get("/companies", response_model=List[CompanyInfo], tags=["Companies"])
async def get_companies():
    """
    Get list of all Forbes AI 50 companies.
    
    Returns a list of all companies with their basic information.
    """
    try:
        # Check if we should use GCS (production) or local file (development)
        if os.getenv("GCS_BUCKET_NAME"):
            companies = load_companies_from_gcs()
        else:
            companies = load_companies()
        
        return [CompanyInfo(**company) for company in companies]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load companies: {str(e)}")

@app.post("/dashboard/rag", response_model=DashboardResponse, tags=["Dashboard"])
async def generate_rag_dashboard(request: CompanyRequest):
    """
    Generate an investor-facing diligence dashboard using RAG pipeline.
    
    This endpoint implements Lab 7:
    - Retrieves top-k context from vector DB
    - Calls LLM with dashboard prompt
    - Returns markdown dashboard with all 8 required sections
    
    The dashboard is generated from unstructured data stored in the vector database.
    """
    try:
        logger.info(f"📋 RAG Dashboard Generation Request")
        logger.info(f"   Company Name: '{request.company_name}'")
        
        # Get company_id for proper vector DB filtering (matches source_path format)
        try:
            logger.info(f"   🔍 Looking up company_id from company_name...")
            company_id = get_company_id_from_name(request.company_name)
            logger.info(f"   ✅ Found company_id: '{company_id}'")
        except HTTPException:
            # Fallback to lowercase company name if lookup fails
            company_id = request.company_name.lower().replace(" ", "_")
            logger.warning(f"   ⚠️  Company not found in seed file, using derived company_id: '{company_id}'")
        
        logger.info(f"   📌 Using company_id='{company_id}' for vector DB lookup")
        logger.info(f"   📌 Using company_name='{request.company_name}' for LLM display")
        
        dashboard = generate_dashboard(company_id, company_display_name=request.company_name)
        
        logger.info(f"   ✅ Dashboard generated successfully ({len(dashboard)} characters)")
        print(dashboard)
        return DashboardResponse(
            company_name=request.company_name,
            dashboard=dashboard,
            pipeline_type="rag"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate RAG dashboard: {str(e)}"
        )


# Structured dashboard generation endpoint
@app.post("/dashboard/structured", response_model=DashboardResponse, tags=["Dashboard"])
async def generate_structured_dashboard(request: CompanyRequest):
    """
    Generate an investor-facing diligence dashboard using structured extraction pipeline.
    
    This endpoint:
    - Loads pre-generated payload from data/payloads/<company_id>.json (or GCS)
    - If payload exists: Calls LLM with structured payload to generate dashboard
    - If payload doesn't exist: Returns "Not disclosed" dashboard without LLM call
    - Returns markdown dashboard with all 8 required sections
    """
    try:
        print(f"Generating structured dashboard for {request.company_name}")
        
        # Step 1: Get company_id from company_name
        company_id = get_company_id_from_name(request.company_name)
        print(f"Company ID: {company_id}")
        
        # Step 2: Try to load payload from file/GCS
        payload = None
        bucket_name = os.getenv("GCS_BUCKET_NAME")
        use_gcs = bucket_name is not None and get_storage_client() is not None
        
        if use_gcs:
            # Try to load from GCS
            payload_path = f"version2/payloads/{company_id}.json"
            print(f"Loading payload from GCS: gs://{bucket_name}/{payload_path}")
            
            client = get_storage_client()
            if client:
                try:
                    bucket = client.bucket(bucket_name)
                    blob = bucket.blob(payload_path)
                    
                    if blob.exists():
                        content = blob.download_as_text()
                        payload_data = json.loads(content)
                        # Convert dict to Payload object
                        from models import Payload
                        payload = Payload(**payload_data)
                        print(f"✅ Loaded payload from GCS")
                    else:
                        print(f"⚠️  Payload not found in GCS: {payload_path}")
                except Exception as e:
                    print(f"⚠️  Failed to load payload from GCS: {e}")
        else:
            # Try to load from local filesystem
            payload_path = PROJECT_ROOT / "data" / "version2" / "payloads" / f"{company_id}.json"
            print(f"Loading payload from local: {payload_path}")
            
            if payload_path.exists():
                try:
                    with open(payload_path, 'r') as f:
                        payload_data = json.load(f)
                    from models import Payload
                    payload = Payload(**payload_data)
                    print(f"✅ Loaded payload from local file")
                except Exception as e:
                    print(f"⚠️  Failed to load payload from local file: {e}")
            else:
                print(f"⚠️  Payload file not found: {payload_path}")
        
        # Step 3: If no payload found, return "Not disclosed" dashboard
        if payload is None:
            print(f"⚠️  No payload found for {request.company_name}")
            print(f"   Returning 'Not disclosed' dashboard without LLM call")
            expected_path = f"gs://{bucket_name}/payloads/{company_id}.json" if use_gcs else str(PAYLOADS_DIR / f"{company_id}.json")
            # Build minimal dashboard with company name only
            dashboard = f"""## Company Overview

Legal Name: Not disclosed
Website: Not disclosed
Headquarters: Not disclosed
Categories: Not disclosed
Total Raised: Not disclosed
Last Round Name: Not disclosed
Last Round Date: Not disclosed
Founded Year: Not disclosed

## Business Model and GTM

Not disclosed.

## Funding & Investor Profile

Not disclosed.

## Growth Momentum

Not disclosed.

## Visibility & Market Sentiment

Not disclosed.

## Risks and Challenges

Not disclosed.

## Outlook

Not disclosed.

## Disclosure Gaps

## Disclosure Gaps

No payload found. Expected payload at: {expected_path}
Please ensure the payload has been generated and stored."""
            
            return DashboardResponse(
                company_name=request.company_name,
                dashboard=dashboard,
                pipeline_type="structured"
            )
        
        # Step 4: Payload exists - check if it has scraped data
        has_scraped_data = (
            len(payload.events) > 0 or 
            len(payload.products) > 0 or 
            len(payload.leadership) > 0
        )
        
        if not has_scraped_data:
            # Payload exists but has no scraped data - return "Not disclosed" dashboard
            print(f"⚠️  Payload found but no scraped data for {request.company_name}")
            print(f"   Returning 'Not disclosed' dashboard without LLM call to prevent hallucination")
            
            company = payload.company_record
            dashboard = f"""## Company Overview

Legal Name: {company.legal_name or 'Not disclosed'}
Website: {company.website or 'Not disclosed'}
Headquarters: {company.hq_city or 'Not disclosed'}, {company.hq_state or ''} {company.hq_country or 'Not disclosed'}
Categories: {', '.join(company.categories) if company.categories else 'Not disclosed'}
Total Raised: {f"${company.total_raised_usd:,.0f}" if company.total_raised_usd else "Not disclosed"}
Last Round Name: {company.last_round_name or 'Not disclosed'}
Last Round Date: {company.last_round_date or 'Not disclosed'}
Founded Year: {company.founded_year or 'Not disclosed'}


No scraped data found in payload. Expected scraped data at: gs://{os.getenv('GCS_BUCKET_NAME', 'bucket')}/raw/{company_id}/initial_pull/
Please ensure the scheduler has scraped and uploaded data to GCS bucket."""
            
            return DashboardResponse(
                company_name=request.company_name,
                dashboard=dashboard,
                pipeline_type="structured"
            )
        
        # Step 5: Payload exists and has scraped data - generate dashboard with LLM
        print(f"✅ Payload found with scraped data - generating dashboard with LLM")
        
        # Convert payload to JSON for LLM
        payload_json = json.dumps(payload.model_dump(), indent=2, default=str)
        
        # Load system prompt (same as RAG)
        system_prompt = load_system_prompt()
        
        # Create user prompt with structured payload
        user_prompt = f"""Generate a comprehensive investor-facing diligence dashboard for {request.company_name}.

Use ONLY the information provided in the Payload below. If something is unknown or not disclosed, literally say "Not disclosed."

If a claim is marketing, attribute it: "The company states ..."

Never include personal emails or phone numbers.

Always include the final section "## Disclosure Gaps".
Payload:
{payload_json}

IMPORTANT: You MUST include all 8 sections in this exact order:
1. ## Company Overview
2. ## Business Model and GTM
3. ## Funding & Investor Profile
4. ## Growth Momentum
5. ## Visibility & Market Sentiment
6. ## Risks and Challenges
7. ## Outlook
8. ## Disclosure Gaps

Do not include any sections beyond these 8. If you cannot find information for a section, write "Not disclosed." for that section."""
        # Call LLM with retry logic (same as RAG)
        max_retries = 3
        dashboard = None
        
        for attempt in range(max_retries):
            try:
                response = openai_client.chat.completions.create(
                    model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,
                    max_tokens=4000
                )
                
                dashboard = response.choices[0].message.content
                
                # Validate that all required sections are present
                required_sections = [
                    "## Company Overview",
                    "## Business Model and GTM",
                    "## Funding & Investor Profile",
                    "## Growth Momentum",
                    "## Visibility & Market Sentiment",
                    "## Risks and Challenges",
                    "## Outlook",
                    "## Disclosure Gaps"
                ]
                
                missing_sections = []
                for section in required_sections:
                    if section not in dashboard:
                        missing_sections.append(section)
                
                if missing_sections:
                    # If sections are missing, add them with "Not disclosed."
                    dashboard += "\n\n"
                    for section in missing_sections:
                        dashboard += f"\n{section}\n\nNot disclosed.\n"
                
                break  # Success, exit retry loop
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"Failed to generate dashboard after {max_retries} attempts: {str(e)}")
                continue
        
        if not dashboard:
            raise Exception("Failed to generate dashboard")
        
        print(f"Dashboard generated successfully for {request.company_name}")
        
        return DashboardResponse(
            company_name=request.company_name,
            dashboard=dashboard,
            pipeline_type="structured"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate structured dashboard: {str(e)}"
        )
# ============================================================================
# HITL (Human-In-The-Loop) Approval Endpoints
# ============================================================================

HITL_APPROVALS_DIR = PROJECT_ROOT / "data" / "hitl_approvals"
HITL_APPROVALS_DIR.mkdir(parents=True, exist_ok=True)

class ApprovalRequest(BaseModel):
    """Model for approval request"""
    approval_id: str
    company_name: str
    risk_count: int
    risks: List[Dict]
    dashboard_preview: Optional[str] = None
    paused_at: str
    approved: Optional[bool] = None
    reviewed_at: Optional[str] = None
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None

class ApprovalResponse(BaseModel):
    """Response model for approval operations"""
    success: bool
    message: str
    approval_id: str
    approved: Optional[bool] = None

class ApprovalActionRequest(BaseModel):
    """Request model for approve/reject actions"""
    reviewer: Optional[str] = None
    review_notes: Optional[str] = None

@app.get("/hitl/approvals", tags=["HITL"], response_model=List[ApprovalRequest])
async def list_approvals(status: Optional[str] = None):
    """
    List all HITL approval requests.
    
    Args:
        status: Filter by status - "pending", "approved", "rejected"
    
    Returns:
        List of approval requests
    """
    approvals = []
    
    for approval_file in HITL_APPROVALS_DIR.glob("*.json"):
        try:
            with open(approval_file, 'r') as f:
                data = json.load(f)
            
            # Filter by status if provided
            if status:
                is_pending = data.get("approved") is None
                if status == "pending" and not is_pending:
                    continue
                elif status == "approved" and data.get("approved") != True:
                    continue
                elif status == "rejected" and data.get("approved") != False:
                    continue
            
            approvals.append(ApprovalRequest(**data))
        except Exception as e:
            continue
    
    # Sort by paused_at (most recent first)
    approvals.sort(key=lambda x: x.paused_at, reverse=True)
    return approvals

@app.get("/hitl/approvals/{approval_id}", tags=["HITL"], response_model=ApprovalRequest)
async def get_approval(approval_id: str):
    """
    Get details of a specific approval request.
    
    Args:
        approval_id: Unique approval ID
    
    Returns:
        Approval request details
    """
    approval_file = HITL_APPROVALS_DIR / f"{approval_id}.json"
    
    if not approval_file.exists():
        raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")
    
    try:
        with open(approval_file, 'r') as f:
            data = json.load(f)
        return ApprovalRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read approval request: {str(e)}")

@app.post("/hitl/approvals/{approval_id}/approve", tags=["HITL"], response_model=ApprovalResponse)
async def approve_request(approval_id: str, request: ApprovalActionRequest):
    """
    Approve an HITL approval request.
    
    Args:
        approval_id: Unique approval ID
        request: Approval action details (reviewer, notes)
    
    Returns:
        Approval response
    """
    approval_file = HITL_APPROVALS_DIR / f"{approval_id}.json"
    
    if not approval_file.exists():
        raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")
    
    try:
        with open(approval_file, 'r') as f:
            data = json.load(f)
        
        # Check if already reviewed
        if data.get("approved") is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Approval request {approval_id} has already been reviewed"
            )
        
        # Update approval
        data["approved"] = True
        data["reviewed_at"] = datetime.now().isoformat()
        data["reviewer"] = request.reviewer or "system"
        data["review_notes"] = request.review_notes
        
        with open(approval_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        return ApprovalResponse(
            success=True,
            message="Approval request approved successfully",
            approval_id=approval_id,
            approved=True
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to approve request: {str(e)}")

@app.post("/hitl/approvals/{approval_id}/reject", tags=["HITL"], response_model=ApprovalResponse)
async def reject_request(approval_id: str, request: ApprovalActionRequest):
    """
    Reject an HITL approval request.
    
    Args:
        approval_id: Unique approval ID
        request: Rejection action details (reviewer, notes)
    
    Returns:
        Approval response
    """
    approval_file = HITL_APPROVALS_DIR / f"{approval_id}.json"
    
    if not approval_file.exists():
        raise HTTPException(status_code=404, detail=f"Approval request {approval_id} not found")
    
    try:
        with open(approval_file, 'r') as f:
            data = json.load(f)
        
        # Check if already reviewed
        if data.get("approved") is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Approval request {approval_id} has already been reviewed"
            )
        
        # Update rejection
        data["approved"] = False
        data["reviewed_at"] = datetime.now().isoformat()
        data["reviewer"] = request.reviewer or "system"
        data["review_notes"] = request.review_notes
        
        with open(approval_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        return ApprovalResponse(
            success=True,
            message="Approval request rejected successfully",
            approval_id=approval_id,
            approved=False
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to reject request: {str(e)}")

@app.post("/dashboard/workflow", tags=["Dashboard"], response_model=Dict)
async def generate_dashboard_with_workflow(request: CompanyRequest):
    """
    Generate dashboard using graph-based workflow with HITL support.
    
    This endpoint executes the full workflow including risk detection and HITL pause.
    If risks are detected, the workflow will pause and wait for approval via the
    HITL approval endpoints.
    
    Args:
        request: Company request with company_name
    
    Returns:
        Workflow execution result with dashboard and execution path
    """
    try:
        workflow = WorkflowGraph()
        state = await workflow.execute(request.company_name)
        
        # Get execution path
        execution_path = workflow.get_execution_path(state)
        
        # Build response
        response = {
            "company_name": state.company_name,
            "company_id": state.company_id,
            "status": state.status.value,
            "dashboard": state.dashboard,
            "execution_path": execution_path,
            "risk_detected": state.risk_detected,
            "risk_count": len(state.risk_signals),
            "hitl_approval_id": state.hitl_approval_id,
            "hitl_approved": state.hitl_approved,
            "started_at": state.started_at.isoformat(),
            "completed_at": state.completed_at.isoformat() if state.completed_at else None,
            "node_results": {
                node_name: {
                    "status": result.status.value,
                    "output": result.output,
                    "error": result.error,
                    "timestamp": result.timestamp.isoformat()
                }
                for node_name, result in state.node_results.items()
            }
        }
        
        # If workflow is paused for approval, include approval details
        if state.status == WorkflowStatus.PAUSED_FOR_APPROVAL:
            response["approval_required"] = True
            response["approval_url"] = f"/hitl/approvals/{state.hitl_approval_id}"
        else:
            response["approval_required"] = False
        
        return response
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to execute workflow: {str(e)}"
        )

# ============================================================================
# Health Check
# ============================================================================

@app.post("/dashboard/agent", tags=["Dashboard"], response_model=AgentDashboardResponse)
async def generate_dashboard_with_agent(request: AgentDashboardRequest):
    """
    Generate dashboard using Supervisor Agent + WorkflowGraph integration.
    
    This endpoint:
    1. Calls Agent Service via HTTP to execute SupervisorAgent with ReAct workflow
    2. Executes WorkflowGraph to generate the dashboard through the graph-based workflow
    3. Returns both the agent trace and the generated dashboard
    
    The Agent Service first gathers information about the company using its tools,
    then the WorkflowGraph executes the full dashboard generation workflow with risk
    detection and HITL support.
    
    Args:
        request: Agent dashboard request with company_name, optional query and company_id
    
    Returns:
        Combined response with agent trace, workflow execution, and dashboard
    """
    try:
        start_time = datetime.now()
        
        # Step 1: Get or extract company_id
        logger.info(f"📋 Dashboard Generation Request Received")
        logger.info(f"   Requested Company Name: '{request.company_name}'")
        logger.info(f"   Requested Company ID: '{request.company_id}'")
        logger.info(f"   Query: '{request.query}'")
        
        company_id = request.company_id
        if not company_id:
            try:
                logger.info(f"   🔍 Looking up company_id from company_name...")
                company_id = get_company_id_from_name(request.company_name)
                logger.info(f"   ✅ Found company_id: '{company_id}'")
            except HTTPException:
                # If company not found, try to extract from name
                company_id = request.company_name.lower().replace(" ", "_")
                logger.warning(f"   ⚠️  Company not found in seed file, using derived company_id: '{company_id}'")
        else:
            logger.info(f"   ✅ Using provided company_id: '{company_id}'")
        
        logger.info(f"   📌 Final company_id for workflow: '{company_id}'")
        logger.info(f"   📌 Final company_name for workflow: '{request.company_name}'")
        
        # Step 2: Call Agent Service via HTTP
        query = request.query or f"Generate a comprehensive dashboard for {request.company_name}"
        
        agent_base_url = os.getenv("AGENT_BASE", "http://localhost:8002")
        logger.info(f"🤖 Calling Agent Service at {agent_base_url} for query: '{query}' (company_id={company_id})")
        
        try:
            agent_response = requests.post(
                f"{agent_base_url}/execute",
                json={
                    "query": query,
                    "company_id": company_id
                },
                timeout=300  # 5 minute timeout for agent execution
            )
            agent_response.raise_for_status()
            agent_data = agent_response.json()
            
            # Convert agent service response to agent_trace dict format
            agent_trace = {
                "query": agent_data["query"],
                "company_id": agent_data["company_id"],
                "final_answer": agent_data["final_answer"],
                "success": agent_data["success"],
                "total_steps": agent_data["total_steps"],
                "started_at": agent_data["started_at"],
                "completed_at": agent_data["completed_at"],
                "steps": agent_data["steps"]
            }
            
            logger.info(f"Supervisor Agent completed: {agent_data['total_steps']} steps, success={agent_data['success']}")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling agent service: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Agent service unavailable: {str(e)}"
            )
        
        # Step 4: Execute WorkflowGraph to generate dashboard
        logger.info(f"🔄 Starting WorkflowGraph execution")
        logger.info(f"   Company Name: '{request.company_name}'")
        logger.info(f"   Company ID: '{company_id}'")
        workflow = WorkflowGraph()
        workflow_state = await workflow.execute(request.company_name, company_id)
        
        logger.info(f"   ✅ WorkflowGraph completed with status: {workflow_state.status.value}")
        logger.info(f"   📊 Dashboard generated: {len(workflow_state.dashboard) if workflow_state.dashboard else 0} characters")
        
        # Get execution path
        execution_path = workflow.get_execution_path(workflow_state)
        
        # Build workflow execution details
        workflow_execution = {
            "status": workflow_state.status.value,
            "execution_path": execution_path,
            "node_results": {
                node_name: {
                    "status": result.status.value,
                    "output": result.output,
                    "error": result.error,
                    "timestamp": result.timestamp.isoformat()
                }
                for node_name, result in workflow_state.node_results.items()
            },
            "risk_detected": workflow_state.risk_detected,
            "risk_count": len(workflow_state.risk_signals),
            "hitl_approval_id": workflow_state.hitl_approval_id,
            "hitl_approved": workflow_state.hitl_approved
        }
        
        # Step 5: Build combined response
        end_time = datetime.now()
        
        response = AgentDashboardResponse(
            company_name=request.company_name,
            company_id=company_id,
            query=query,
            dashboard=workflow_state.dashboard,
            status=workflow_state.status.value,
            agent_trace=agent_trace,
            workflow_execution=workflow_execution,
            execution_path=execution_path,
            risk_detected=workflow_state.risk_detected,
            risk_count=len(workflow_state.risk_signals),
            hitl_approval_id=workflow_state.hitl_approval_id,
            hitl_approved=workflow_state.hitl_approved,
            started_at=start_time.isoformat(),
            completed_at=end_time.isoformat()
        )
        
        logger.info(f"Agent + Workflow completed for {request.company_name}")
        
        return response
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in agent-driven dashboard generation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate dashboard with agent: {str(e)}"
        )

@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Project Orbit API"
    }